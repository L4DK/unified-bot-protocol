### 3\. Service Discovery and Registration

In a static environment with a few long-running services, it might be feasible to hardcode the network locations (IP addresses and ports) of each component. However, a modern, scalable microservices architecture is dynamic and ephemeral. Bot Agents are expected to be scaled up, down, or restarted frequently across a cluster of machines. This means their network locations are constantly changing. A robust, automated **Service Discovery** mechanism is therefore not an optional feature but a foundational requirement for the system to function.[1, 2, 3]

#### Design Philosophy

The core philosophy is to create a single, dynamic, and highly available "phone book" for our services, known as a **Service Registry**. No component should ever need to know the fixed IP address of another. Instead, when a bot needs to be contacted, the Orchestrator consults the registry to find its current, valid location.[4, 5] This decouples services from their physical locations, enabling resilience and scalability. If a bot instance fails, it is removed from the registry, and traffic is automatically routed to healthy instances. If we need more capacity, we can launch new instances, which automatically add themselves to the registry and start receiving traffic.

This design centralizes the responsibility of "finding" services, which simplifies the logic within the Bot Agents and aligns with our Command and Control (C2) model where the Orchestrator maintains maximum awareness of the fleet's state.[1, 3]

#### Technical Implementation & Features

The architecture employs a combination of two well-established patterns: the **Server-Side Discovery pattern** and the **Third-Party Registration pattern**.[4, 3]

  * **Service Registry:** This is the central database. It's not a standard relational database but a specialized, highly available, distributed key-value store designed for this purpose. Common technologies for this are **Consul** or **etcd**.[5] The registry stores not just the IP and port of each bot instance but also crucial metadata:

      * `bot_id`: The logical type of the bot.
      * `instance_id`: The unique ID for this specific running process.
      * `capabilities`: A list of commands the bot can execute.
      * `health_status`: The current health state (e.g., `PASSING`, `WARNING`, `CRITICAL`), which is updated by the health checking mechanism.

  * **Third-Party Registration Pattern:** The Bot Agent itself is not responsible for communicating with the Service Registry. This responsibility is offloaded to a separate, trusted process called a **Registrar**.[4, 3] In a modern containerized environment like Kubernetes, this registrar is typically implemented as a "sidecar" container that runs alongside the Bot Agent's container.

      * **Why?** This decouples the bot's application code from the infrastructure. The bot developer doesn't need to add any specific code or libraries for Consul, etcd, or any other registry. The bot simply runs, and the sidecar handles the platform-specific task of registration. This makes the Bot Agent more portable and simpler to maintain.[2]

  * **Server-Side Discovery Pattern:** When the Orchestrator needs to send a command, it is the one that queries the Service Registry. The Bot Agent clients remain simple and unaware of the broader network topology.[1, 2]

      * **Why?** This centralizes the routing and load-balancing logic within the Orchestrator. The Orchestrator can make intelligent decisions based on the health, load, or even geographic location of bot instances. This is more powerful and flexible than client-side discovery, where each client would need to implement its own complex load-balancing logic.[3, 6]

#### Information Flow: Step-by-Step

1.  **Startup:** A new Bot Agent instance is deployed (e.g., a Docker container starts).
2.  **Registration:** The Registrar sidecar detects the new agent. It gathers the agent's IP, port, and metadata.
3.  **API Call to Registry:** The Registrar makes an API call (typically a RESTful `PUT` or `POST`) to the Service Registry to register the new instance.
4.  **Health Checking Begins:** The Service Registry receives the registration and immediately begins monitoring the agent's health check endpoint (this is the topic of our next section).
5.  **Orchestrator Query:** The Orchestrator needs to send a `database.query` command. It makes a query to the Service Registry's API, asking for all healthy instances with the `database.query` capability.
6.  **Registry Response:** The registry returns a list of healthy instances that match the criteria.
7.  **Command Dispatch:** The Orchestrator's internal load balancer selects one instance from the list and dispatches the UBP command to its IP and port.
8.  **Shutdown/Failure:**
      * **Graceful Shutdown:** When the agent is shut down cleanly, the Registrar sidecar makes a `DELETE` API call to the registry to deregister the instance.
      * **Crash/Failure:** If the agent crashes, it will stop responding to health checks. After a configured number of failures, the Service Registry will automatically mark the instance as unhealthy and remove it from the list of available services.

#### Real-Life Code Examples

**Example 1: Data Structure in a Key-Value Registry (JSON format)**
This is what the data for a single bot instance might look like inside Consul or etcd. The key would be something like `upb/bots/bot-slack-adapter/instance-abc-123`.

```json
{
  "botId": "bot-slack-adapter",
  "instanceId": "instance-abc-123",
  "address": "10.1.2.34",
  "port": 8080,
  "capabilities": [
    "slack.message.send",
    "slack.reaction.add",
    "slack.user.get_profile"
  ],
  "registeredAt": "2025-09-15T22:10:00Z",
  "healthCheck": {
    "endpoint": "/health/ready",
    "status": "PASSING",
    "lastChecked": "2025-09-15T22:12:30Z"
  }
}
```

**Example 2: Registrar Sidecar Logic (Conceptual Python)**
This script simulates a registrar making an API call to register the agent.

```python
import os
import requests
import time
import atexit

# Assume these are passed to the sidecar via environment variables
REGISTRY_API_URL = os.getenv("REGISTRY_API_URL", "http://consul.service.local:8500/v1/agent/service/register")
BOT_ID = os.getenv("BOT_ID")
INSTANCE_ID = os.getenv("INSTANCE_ID")
BOT_IP = os.getenv("BOT_IP")
BOT_PORT = int(os.getenv("BOT_PORT"))

def register_service():
    """Registers the bot instance with the service registry."""
    registration_payload = {
        "ID": INSTANCE_ID,
        "Name": BOT_ID,
        "Address": BOT_IP,
        "Port": BOT_PORT,
        "Tags": ["ubp", "bot-agent"],
        "Meta": {
            "capabilities": "slack.message.send,slack.reaction.add"
        },
        "Check": {
            "HTTP": f"http://{BOT_IP}:{BOT_PORT}/health/ready",
            "Interval": "10s",
            "Timeout": "1s",
            "DeregisterCriticalServiceAfter": "1m"
        }
    }
    print(f"Registering instance {INSTANCE_ID} with registry...")
    response = requests.put(REGISTRY_API_URL, json=registration_payload)
    if response.status_code == 200:
        print("Registration successful.")
    else:
        print(f"Registration failed: {response.text}")
        exit(1)

def deregister_service():
    """Deregisters the bot instance upon shutdown."""
    deregister_url = f"http://consul.service.local:8500/v1/agent/service/deregister/{INSTANCE_ID}"
    print(f"Deregistering instance {INSTANCE_ID}...")
    requests.put(deregister_url)

if __name__ == "__main__":
    # Register on startup
    register_service()
    
    # Ensure deregistration happens on exit
    atexit.register(deregister_service)
    
    # Keep the sidecar running
    while True:
        time.sleep(60)
```

**Example 3: Orchestrator Query Logic (Conceptual Python)**
This shows how the Orchestrator would find a suitable bot.

```python
import requests

class ServiceLocator:
    def __init__(self, registry_url="http://consul.service.local:8500"):
        self.registry_url = registry_url

    def find_healthy_instances(self, capability: str):
        """Queries the registry for healthy bots with a specific capability."""
        # Consul API endpoint for healthy services
        query_url = f"{self.registry_url}/v1/health/service/{capability}"
        
        params = {"passing": "true"} # Filter for only healthy instances
        
        try:
            response = requests.get(query_url, params=params)
            response.raise_for_status()
            
            services = response.json()
            
            # Extract and return a clean list of addresses
            addresses =
            for service_entry in services:
                service_info = service_entry.get("Service", {})
                address = service_info.get("Address")
                port = service_info.get("Port")
                if address and port:
                    addresses.append(f"{address}:{port}")
            
            return addresses
            
        except requests.RequestException as e:
            print(f"Error querying service registry: {e}")
            return

# --- How the Orchestrator would use it ---
locator = ServiceLocator()
available_bots = locator.find_healthy_instances("bot-slack-adapter")

if available_bots:
    # A real load balancer would be used here
    target_bot_address = available_bots 
    print(f"Found healthy Slack bots at: {available_bots}")
    print(f"Dispatching command to {target_bot_address}")
else:
    print("No healthy Slack bots found.")
```

This robust discovery and registration system is the backbone of the framework's scalability and resilience. It allows the fleet of bots to be a dynamic, living system rather than a fragile, static one.
