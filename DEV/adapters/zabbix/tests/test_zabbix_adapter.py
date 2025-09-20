import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from zabbix_adapter import ZabbixAdapter, ZabbixConfig, ZabbixSeverity


@pytest.fixture
def config():
    return ZabbixConfig(
        zabbix_url="https://test-zabbix.example.com",
        username="test_user",
        password="test_password",
        encryption_key="test_encryption_key_32_characters",
        jwt_secret="test_jwt_secret",
        webhook_secret="test_webhook_secret",
        poll_interval=10,
    )


@pytest.fixture
async def adapter(config):
    adapter = ZabbixAdapter(config)
    adapter.session = AsyncMock()
    adapter.cache = AsyncMock()
    yield adapter
    await adapter.close()


@pytest.mark.asyncio
async def test_authentication_with_credentials(adapter):
    """Test authentication using username/password"""
    mock_response = {"result": "test_auth_token"}
    adapter._make_raw_api_request = AsyncMock(return_value="test_auth_token")

    await adapter._authenticate()

    assert adapter.auth_token == "test_auth_token"
    assert adapter.token_expires_at is not None


@pytest.mark.asyncio
async def test_authentication_with_api_token(config):
    """Test authentication using API token"""
    config.api_token = "test_api_token"
    config.username = None
    config.password = None

    adapter = ZabbixAdapter(config)
    await adapter._authenticate()

    assert adapter.auth_token == "test_api_token"
    assert adapter.token_expires_at is None


@pytest.mark.asyncio
async def test_api_request_with_retry(adapter):
    """Test API request with retry logic"""
    # First call fails, second succeeds
    adapter.session.post.side_effect = [
        AsyncMock(side_effect=aiohttp.ClientError("Connection failed")),
        AsyncMock(
            return_value=AsyncMock(
                status=200, json=AsyncMock(return_value={"result": {"hostid": "123"}})
            )
        ),
    ]

    result = await adapter._make_api_request("host.get", {"limit": 1})
    assert result == {"hostid": "123"}


@pytest.mark.asyncio
async def test_problem_detection_and_enrichment(adapter):
    """Test new problem detection and data enrichment"""
    problem = {
        "eventid": "12345",
        "objectid": "67890",
        "name": "High CPU usage",
        "severity": "4",
        "clock": "1634567890",
        "acknowledged": "0",
        "tags": [{"tag": "service", "value": "web"}],
    }

    # Mock enrichment data
    adapter._make_api_request = AsyncMock(
        return_value=[
            {
                "triggerid": "67890",
                "hosts": [{"hostid": "1", "host": "web-server-01"}],
                "items": [{"itemid": "1", "name": "CPU usage"}],
            }
        ]
    )

    adapter._get_item_history = AsyncMock(
        return_value=[
            {"clock": "1634567800", "value": "85.5"},
            {"clock": "1634567830", "value": "92.1"},
        ]
    )

    await adapter._handle_new_problem(problem)

    # Verify event was queued
    assert adapter.event_queue.qsize() == 1
    event = await adapter.event_queue.get()

    assert event["event_type"] == "zabbix.problem.new"
    assert event["data"]["problem_id"] == "12345"
    assert event["severity"] == "major"
    assert "enriched_data" in event["data"]


@pytest.mark.asyncio
async def test_webhook_processing(adapter):
    """Test webhook data processing"""
    from aiohttp import web

    webhook_data = {
        "alert": {
            "alertid": "123",
            "host": "web-server-01",
            "trigger": "High CPU usage",
            "severity": "4",
            "status": "PROBLEM",
            "message": "CPU usage is 95%",
        }
    }

    # Mock request
    request = MagicMock()
    request.headers = {"Authorization": "Bearer valid_token"}
    request.json = AsyncMock(return_value=webhook_data)
    request.remote = "192.168.1.100"

    # Mock signature verification
    adapter._verify_webhook_signature = MagicMock(return_value=True)

    response = await adapter._handle_webhook(request)

    assert response.status == 200
    response_data = json.loads(response.text)
    assert response_data["status"] == "success"


@pytest.mark.asyncio
async def test_host_monitoring_with_filters(adapter):
    """Test host monitoring with various filters"""
    mock_hosts = [
        {
            "hostid": "1",
            "host": "web-server-01",
            "status": "0",
            "available": "1",
            "groups": [{"groupid": "1", "name": "Web Servers"}],
        },
        {
            "hostid": "2",
            "host": "db-server-01",
            "status": "0",
            "available": "1",
            "groups": [{"groupid": "2", "name": "Database Servers"}],
        },
    ]

    adapter._make_api_request = AsyncMock(return_value=mock_hosts)

    params = {
        "host_names": ["web-server-01"],
        "include_metrics": True,
        "include_problems": True,
    }

    adapter._get_host_metrics = AsyncMock(return_value=[])
    adapter._get_host_problems = AsyncMock(return_value=[])

    result = await adapter._get_hosts(params)

    assert result["count"] == 2
    assert len(result["hosts"]) == 2
    assert "recent_metrics" in result["hosts"][0]
    assert "active_problems" in result["hosts"][0]


@pytest.mark.asyncio
async def test_circuit_breaker_functionality(adapter):
    """Test circuit breaker prevents cascade failures"""
    # Simulate multiple failures
    adapter.session.post = AsyncMock(
        side_effect=aiohttp.ClientError("Service unavailable")
    )

    # Circuit breaker should open after threshold failures
    with pytest.raises(Exception):
        for _ in range(adapter.config.circuit_breaker_threshold + 1):
            try:
                await adapter._make_api_request("host.get", {})
            except:
                pass

        # This should fail immediately due to open circuit
        await adapter._make_api_request("host.get", {})


@pytest.mark.asyncio
async def test_maintenance_window_detection(adapter):
    """Test maintenance window detection"""
    maintenance_data = [
        {
            "maintenanceid": "1",
            "name": "Weekly maintenance",
            "active_since": int(time.time() - 3600),
            "active_till": int(time.time() + 3600),
            "hosts": [{"hostid": "1"}],
        }
    ]

    adapter._make_api_request = AsyncMock(return_value=maintenance_data)
    await adapter._load_maintenance_windows()

    assert len(adapter.maintenance_windows) == 1
    assert "1" in adapter.maintenance_windows


@pytest.mark.asyncio
async def test_impact_analysis(adapter):
    """Test problem impact analysis"""
    problem = {"eventid": "123", "objectid": "456", "severity": "5"}  # Disaster

    # Mock host dependencies
    adapter.host_dependencies = {"456": {"host1", "host2", "host3"}}

    impact = await adapter._analyze_problem_impact(problem)

    assert impact["severity_score"] == 5
    assert impact["business_impact"] == "critical"
    assert len(impact["affected_hosts"]) == 3


@pytest.mark.asyncio
async def test_adaptive_rate_limiting(config):
    """Test adaptive rate limiting adjusts to load"""
    config.adaptive_rate_limiting = True
    adapter = ZabbixAdapter(config)

    # Simulate high load
    for _ in range(100):
        await adapter.rate_limiter.acquire()

    # Rate limiter should have adapted
    assert hasattr(adapter.rate_limiter, "current_rate")


@pytest.mark.asyncio
async def test_comprehensive_status_reporting(adapter):
    """Test comprehensive status reporting"""
    adapter.is_running = True
    adapter.stats["events_processed"] = 100
    adapter.stats["alerts_sent"] = 50

    status = await adapter.get_adapter_status()

    assert status["adapter_id"] == "zabbix"
    assert status["status"] == "running"
    assert status["statistics"]["events_processed"] == 100
    assert status["statistics"]["alerts_sent"] == 50
    assert "health_checks" in status
    assert "performance_metrics" in status


@pytest.mark.asyncio
async def test_security_audit_logging(adapter):
    """Test security audit logging"""
    # Mock audit logger
    adapter.audit_logger.log = MagicMock()

    # Simulate authentication
    await adapter._authenticate()

    # Verify audit log was called
    adapter.audit_logger.log.assert_called()

    # Check for security-related logs
    calls = adapter.audit_logger.log.call_args_list
    auth_calls = [call for call in calls if "auth" in str(call)]
    assert len(auth_calls) > 0


@pytest.mark.asyncio
async def test_performance_metrics_collection(adapter):
    """Test performance metrics are collected"""
    # Mock metrics collector
    adapter.metrics.increment = MagicMock()
    adapter.metrics.gauge = MagicMock()

    # Simulate some operations
    await adapter._poll_problems()

    # Verify metrics were recorded
    adapter.metrics.increment.assert_called()
    adapter.metrics.gauge.assert_called()


@pytest.mark.asyncio
async def test_graceful_shutdown(adapter):
    """Test graceful shutdown process"""
    # Start adapter components
    adapter.is_running = True
    adapter.polling_task = AsyncMock()
    adapter.health_check_task = AsyncMock()
    adapter.cleanup_task = AsyncMock()
    adapter.processing_tasks = [AsyncMock(), AsyncMock()]

    # Mock webhook components
    adapter.webhook_site = AsyncMock()
    adapter.webhook_runner = AsyncMock()

    await adapter.stop()

    # Verify all components were stopped
    assert not adapter.is_running
    adapter.webhook_site.stop.assert_called_once()
    adapter.webhook_runner.cleanup.assert_called_once()
