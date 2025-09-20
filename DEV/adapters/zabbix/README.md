# Zabbix Adapter for Unified Bot Protocol (UBP)

## Overview

This is the **world-class, enterprise-grade Zabbix monitoring adapter** for the Unified Bot Protocol (UBP) framework.
It represents the pinnacle of monitoring integration technology, providing comprehensive, secure, and highly performant connectivity between Zabbix monitoring systems and the UBP ecosystem, now enhanced with AI/ML capabilities, automated remediation, and advanced analytics.

## 🌟 Features

### Core Monitoring Capabilities

- **Complete Zabbix API 7.0+ integration** with all monitoring features
- **Real-time problem detection** with intelligent filtering, enrichment, and suppression
- **Advanced metrics collection** with historical data and anomaly detection
- **Host management** with dependency tracking, impact analysis, and maintenance awareness
- **Trigger monitoring** with predictive alerting and correlation
- **Maintenance window awareness** with automatic alert suppression

### AI/ML Enhanced Monitoring

- **Anomaly detection** using Isolation Forest
- **Predictive maintenance** support
- **Automated remediation actions** triggered by alerts
- **Advanced analytics dashboards** with customizable widgets
- **Integration hooks for Grafana visualization**

### Enterprise-Grade Architecture

- **Multi-tenant support** with role-based access control
- **High-performance webhook server** with SSL/TLS and HMAC signature verification
- **Intelligent polling** with adaptive intervals and batch processing
- **Advanced caching** with in-memory and optional Redis support
- **Circuit breaker pattern** for resilience and fault tolerance
- **Comprehensive observability** with structured logging, distributed tracing, and metrics export

### Security & Compliance

- **Multi-factor authentication** with API tokens and credentials
- **End-to-end encryption** for all communications
- **Webhook signature verification** with HMAC validation
- **Comprehensive audit logging** for compliance requirements
- **Token management** with automatic rotation and expiration
- **SSL/TLS support** with certificate validation

### Performance & Scalability

- **Adaptive rate limiting** with intelligent backoff
- **Connection pooling** with configurable limits
- **Asynchronous processing** with worker queues
- **Batch operations** for efficient API usage
- **Intelligent caching** with TTL and invalidation
- **Performance monitoring** with detailed metrics

## 📋 Requirements

- Python 3.12.10+
- Zabbix 6.0+ (7.0+ recommended)
- Redis (optional, for distributed caching)
- SSL certificates (for secure webhook endpoints)
- Optional: scikit-learn, numpy, pandas for AI/ML features

## 🚀 Installation

```bash
# Install dependencies
pip install aiohttp aiofiles cryptography pyjwt redis structlog ujson tenacity scikit-learn numpy pandas

# Install UBP core libraries
pip install ubp-core

# Clone the adapter
git clone https://github.com/L4DK/Unified-Bot-Protocol.git
cd Unified-Bot-Protocol/adapters/zabbix
```

## ⚙️ Configuration

### Basic Configuration

```python
from zabbix_adapter import ZabbixAdapter, ZabbixConfig

config = ZabbixConfig(
    server_url="https://your-zabbix-server.com",
    username="monitoring_user",
    password="secure_password",

    # Security
    encryption_key="your_32_character_encryption_key",
    webhook_secret="your_webhook_secret",

    # Performance
    poll_interval=15,
    rate_limit_requests=100,
    cache_ttl=600,

    # AI/ML
    enable_anomaly_detection=True,
    anomaly_detection_threshold=0.05,

    # Advanced
    enable_auto_remediation=True,
    grafana_url="https://grafana.example.com",
    grafana_api_key="your_grafana_api_key"
)

adapter = ZabbixAdapter(config)
```

### Advanced Configuration

See `zabbix_config.yaml` for comprehensive configuration options including:

- SSL/TLS settings
- Monitoring filters
- Performance tuning
- Security options
- AI/ML and analytics features

## 🔧 Usage

### Basic Usage

```python
import asyncio
from zabbix_adapter import ZabbixAdapter, ZabbixConfig

async def main():
    config = ZabbixConfig(
        server_url="https://zabbix.example.com",
        username="admin",
        password="password"
    )

    async with ZabbixAdapter(config) as adapter:
        hosts = await adapter.get_hosts()
        print(f"Found {len(hosts)} hosts")

        alerts = await adapter.get_alerts()
        print(f"Found {len(alerts)} active alerts")

        health = await adapter.get_health_status()
        print(f"Adapter health: {health['connected']}")

        # Run indefinitely
        while True:
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
```

### Command Handling

The adapter supports comprehensive UBP commands:

```python
# Example: Get hosts with filtering
command = {
    "command_name": "zabbix.hosts.get",
    "parameters": {
        "host_names": ["web-server-01", "db-server-01"],
        "include_metrics": True,
        "include_problems": True
    }
}

result = await adapter.handle_command(command)
```

### Webhook Integration

Configure Zabbix to send webhooks to the adapter:

- Create Media Type in Zabbix:
  - Type: Webhook
  - URL: `https://your-server.com:8080/zabbix/webhook`
  - Script: Custom webhook script
- Configure Authentication:
  - Add Authorization: Bearer your_webhook_secret header
- Test Webhook:

```bash
curl -X POST https://your-server.com:8080/zabbix/webhook \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer your_webhook_secret" \\
  -d '{"alert": {"alertid": "123", "host": "test-host"}}'
```

## 📊 Supported Commands

| Command                   | Description               | Parameters                               |
| ------------------------- | ------------------------- | ---------------------------------------- |
| zabbix.hosts.get          | Get host information      | host_ids, group_ids, include_metrics     |
| zabbix.problems.get       | Get active problems       | severity_filter, host_filter, time_range |
| zabbix.metrics.get        | Get metrics data          | item_ids, time_from, time_till           |
| zabbix.triggers.get       | Get trigger information   | trigger_ids, host_ids, status            |
| zabbix.alerts.acknowledge | Acknowledge alerts        | event_ids, message, action               |
| zabbix.maintenance.create | Create maintenance window | host_ids, start_time, duration           |
| zabbix.dashboard.get      | Get dashboard data        | dashboard_id, time_range                 |

## 🔍 Monitoring & Observability

### Health Checks

```bash
# Check adapter health
curl http://localhost:8080/health

# Get detailed status
curl http://localhost:8080/status

# Get metrics
curl http://localhost:8080/metrics
```

### Logging

The adapter provides structured logging with multiple levels:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Metrics

Key metrics collected:

- zabbix.api.requests - API request count
- zabbix.problems.active - Active problem count
- zabbix.events.processed - Event processing rate
- zabbix.webhook.received - Webhook reception rate
- zabbix.commands.executed - Command execution count

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest -v

# Run specific test categories
pytest -v -k "test_authentication"
pytest -v -k "test_webhook"
pytest -v -k "test_performance"

# Run with coverage
pytest --cov=zabbix_adapter --cov-report=html
```

## 🔒 Security Best Practices

- Use API Tokens: Prefer API tokens over username/password
- Enable SSL/TLS: Always use HTTPS for webhooks
- Verify Signatures: Enable webhook signature verification
- Rotate Credentials: Regularly rotate API tokens and secrets
- Monitor Access: Enable audit logging for compliance
- Network Security: Use firewalls and VPNs for Zabbix access

## 🚀 Performance Tuning

### High-Load Environments

```yaml
# Increase connection limits
connection_pool_size: 50
concurrent_requests: 20

# Optimize polling
poll_interval: 15
batch_size: 200

# Enable caching
cache_enabled: true
redis_url: "redis://redis-cluster:6379/0"

# Adaptive rate limiting
adaptive_rate_limiting: true
rate_limit_per_second: 100
```

### Memory Optimization

```yaml
# Limit data retention
max_history_age: 1800  # 30 minutes

# Optimize caching
cache_ttl: 180  # 3 minutes

# Batch processing
batch_size: 50
```

## 🛠️ Troubleshooting

### Common Issues

#### Authentication Failures

```bash
# Check API token validity
curl -X POST https://zabbix.example.com/api_jsonrpc.php \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"auth":"your_token","id":1}'
```

#### Webhook Not Receiving Data

- Verify webhook URL is accessible
- Check firewall settings
- Validate SSL certificates
- Confirm webhook secret matches

#### High Memory Usage

- Reduce max_history_age
- Enable Redis caching
- Optimize polling intervals

#### Rate Limiting Issues

- Enable adaptive rate limiting
- Increase rate_limit_per_second
- Use connection pooling

## 📈 Roadmap

- Zabbix 7.0+ Support - Latest API features
- Machine Learning Integration - Anomaly detection
- Advanced Dashboards - Custom visualization
- Multi-Instance Support - Multiple Zabbix servers
- Enhanced Automation - Auto-remediation workflows
- Cloud Integration - AWS, Azure, GCP monitoring

## 📄 License

Apache License 2.0 - See LICENSE file for details.

## 🤝 Contributing

We welcome contributions! Please see CONTRIBUTING.md for guidelines.

## 📞 Support

- Documentation: UBP Documentation
- GitHub Issues: Report Issues
- Community: UBP Community Forum

## 👨‍💻 Author

Michael Landbo - UBP Founder & Principal Architect

GitHub: @L4DK
Website: Unified Bot Protocol

This Zabbix adapter represents the pinnacle of monitoring integration technology, designed to provide enterprise-grade reliability, security, and performance for mission-critical monitoring environments.
