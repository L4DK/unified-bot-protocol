This Bot Agent implementation includes:

    1. Secure WebSocket client with automatic reconnection
    2. Full UBP handshake and heartbeat implementation
    3. Structured JSON logging with trace IDs
    4. Prometheus metrics for monitoring
    5. Health check endpoints via FastAPI
    6. Command handling with simulated work
    7. Error handling and recovery
    8. Thread-safe design with separate API server


Key features:

    * Maintains persistent connection to Orchestrator
    * Handles reconnection automatically
    * Provides health and metrics endpoints
    * Uses structured logging for better observability
    * Implements the full UBP message protocol
    * Includes proper error handling and recovery
    * Supports multiple command capabilities