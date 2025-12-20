### 17\. Observability: Metrics and KPIs

While structured logging and distributed tracing provide detailed, event-specific information about *what happened* during a request, metrics provide aggregated, numerical data about *how the system is behaving* over time. Metrics are the foundation of performance monitoring, trend analysis, capacity planning, and automated alerting. They answer questions like: "What is our average command latency?", "Is our error rate increasing?", and "Are we approaching our connection capacity?"

#### Design Philosophy

The philosophy is to enable **quantitative, proactive monitoring**. We must move beyond reactively debugging failures with logs and proactively identify performance degradation and potential issues before they become outages. This is achieved by treating key performance indicators (KPIs) as a core feature of every component.

  * **Standardization:** Every component in the ecosystem must expose metrics in a consistent, standardized format. This allows a single, centralized monitoring system to collect and analyze data from the entire fleet without custom integrations for each service.
  * **Actionable Data:** We don't collect metrics for the sake of data collection. Every metric is chosen because it provides an actionable insight into the health, performance, or scalability of the system.
  * **Separation of Concerns:** The components are responsible for *exposing* their metrics, but they are not responsible for storing or analyzing them. That is the job of a dedicated, centralized monitoring system (like Prometheus), which periodically "scrapes" the metrics endpoints of all services.

#### Technical Implementation & Features

  * **Monitoring Stack:** The architecture assumes a standard monitoring stack consisting of:
      * **Prometheus:** A powerful, open-source time-series database and monitoring system. It operates on a pull model, where it periodically scrapes HTTP endpoints on services to collect metrics.[1]
      * **Grafana:** A leading open-source platform for visualizing and dashboarding data. It connects to Prometheus as a data source to create real-time dashboards that display the health and performance of the UBP ecosystem.[1]
  * **Exposition Format:** Every UBP component (Orchestrator, Agent, Adapter) **MUST** expose a `/metrics` HTTP endpoint. This endpoint serves data in the **Prometheus exposition format**, a simple text-based format that is easy for both humans and machines to parse.
  * **Metric Types:** The implementation uses standard metric types to accurately represent different kinds of data:
      * **Counter:** A cumulative metric that only ever increases (e.g., `http_requests_total`). Used for tracking the total number of events.
      * **Gauge:** A metric that represents a single numerical value that can arbitrarily go up and down (e.g., `active_connections`, `queue_depth`).
      * **Histogram:** A more complex metric that samples observations (e.g., request latencies) and counts them in configurable buckets. This is essential for calculating quantiles (e.g., the 99th percentile latency).

-----

### Key Performance Indicators (KPIs) and Metrics to Track

The following essential metrics **MUST** be tracked by each component to provide a comprehensive view of system health.[2]

#### 1\. Orchestrator Metrics

  * `ubp_active_connections`: (Gauge) The total number of currently connected Bot Agents.
  * `ubp_command_throughput_total`: (Counter) The total number of processed commands, labeled by `command_name` and `status` (`success`/`failure`).
  * `ubp_command_latency_seconds`: (Histogram) The time taken to process commands from receipt to response, labeled by `command_name`.
  * `http_api_requests_total`: (Counter) The total number of Management API requests, labeled by `endpoint`, `method`, and `status_code`.
  * `task_queue_depth`: (Gauge) The number of pending items in the asynchronous task queue.

#### 2\. Bot Agent Metrics

  * `ubp_connection_status`: (Gauge) The agent's connection state to the Orchestrator (1 for connected, 0 for disconnected).
  * `ubp_time_since_last_heartbeat_seconds`: (Gauge) The time since the last successful heartbeat was sent.
  * `ubp_commands_processed_total`: (Counter) The total number of commands executed, labeled by `command_name` and `status`.
  * `process_cpu_usage_percent`: (Gauge) The agent's CPU resource consumption.
  * `process_memory_usage_bytes`: (Gauge) The agent's memory consumption.

#### 3\. Platform Adapter Metrics

  * `external_api_latency_seconds`: (Histogram) The response times from the third-party platform's API, labeled by `external_endpoint`.
  * `external_api_errors_total`: (Counter) The total number of failed requests to the third-party API, labeled by `external_endpoint` and `error_code`.
  * `ubp_translation_queue_depth`: (Gauge) The number of incoming platform events waiting to be translated into UBP messages.

-----

### Real-Life Code Examples

#### 1\. Prometheus Exposition Format Example

This is what the raw text output of a `/metrics` endpoint might look like.

```
# HELP http_requests_total The total number of HTTP requests.
# TYPE http_requests_total counter
http_requests_total{method="post",endpoint="/v1/bots"} 20
http_requests_total{method="get",endpoint="/v1/bots"} 105

# HELP ubp_active_connections The current number of active UBP connections.
# TYPE ubp_active_connections gauge
ubp_active_connections 54

# HELP ubp_command_latency_seconds Latency of UBP commands in seconds.
# TYPE ubp_command_latency_seconds histogram
ubp_command_latency_seconds_bucket{le="0.005",command_name="message.send"} 120
ubp_command_latency_seconds_bucket{le="0.01",command_name="message.send"} 250
ubp_command_latency_seconds_bucket{le="0.025",command_name="message.send"} 300
ubp_command_latency_seconds_bucket{le="+Inf",command_name="message.send"} 302
ubp_command_latency_seconds_sum{command_name="message.send"} 2.87
ubp_command_latency_seconds_count{command_name="message.send"} 302
```

#### 2\. Exposing Metrics from a Python Application

This example uses the `prometheus-client` library to create and expose metrics from a FastAPI application.

```python
from fastapi import FastAPI, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
import random

app = FastAPI()

# --- 1. Define the metrics ---
# Use labels to add dimensions to your metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint"]
)
UBP_ACTIVE_CONNECTIONS = Gauge(
    "ubp_active_connections",
    "Current number of active UBP connections"
)
UBP_COMMAND_LATENCY = Histogram(
    "ubp_command_latency_seconds",
    "Latency of UBP commands in seconds",
    ["command_name"]
)

# --- 2. Instrument the application code to update metrics ---
@app.post("/v1/bots")
async def create_bot():
    # Increment the counter for this specific endpoint
    HTTP_REQUESTS_TOTAL.labels(method="post", endpoint="/v1/bots").inc()
    
    # Simulate processing a command
    start_time = time.time()
    time.sleep(random.uniform(0.01, 0.05)) # Simulate work
    latency = time.time() - start_time
    
    # Observe the latency for the histogram
    UBP_COMMAND_LATENCY.labels(command_name="create_bot_definition").observe(latency)
    
    return {"status": "created"}

@app.get("/v1/bots")
async def get_bots():
    HTTP_REQUESTS_TOTAL.labels(method="get", endpoint="/v1/bots").inc()
    # Simulate a fluctuating number of connections
    UBP_ACTIVE_CONNECTIONS.set(random.randint(50, 100))
    return {"bots":}

# --- 3. Expose the /metrics endpoint ---
@app.get("/metrics")
async def metrics():
    """
    This endpoint is scraped by Prometheus to collect the metrics.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

```

This comprehensive metrics strategy, combined with structured logging and distributed tracing, completes the observability triad. It provides the deep, quantitative insights necessary to operate the UBP framework reliably, optimize its performance, and automate responses to emerging issues.
