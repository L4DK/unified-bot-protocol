### Design Philosophy

For the email adapters (IMAP, POP3, SMTP) within the Unified Bot Protocol (UBP) framework, a **combined README** is the most effective approach.
This consolidates all related information in one place, reducing duplication and easing maintenance.
It also highlights the common architectural principles shared by all adapters while clearly delineating their distinct roles and configurations.

---

# Email Adapters for Unified Bot Protocol (UBP)

## Overview

This package contains three production-grade email adapters for the Unified Bot Protocol (UBP):

- **IMAPEmailAdapter**: Inbound adapter using IMAP protocol to fetch and process incoming emails.
- **POP3EmailAdapter**: Inbound adapter using POP3 protocol to fetch and process incoming emails.
- **SMTPEmailAdapter**: Outbound adapter using SMTP protocol to send emails asynchronously.

Each adapter is designed with deep integration into the UBP ecosystem, emphasizing **interoperability, scalability, security, and observability**.

---

## Features

- **Inbound Adapters (IMAP & POP3)**
  - Secure connection support (SSL/TLS)
  - Polling-based email retrieval with configurable intervals
  - Multipart email parsing including attachments
  - Event generation with UBP-compliant message schema
  - Security: Message signing before sending to orchestrator
  - Observability: Structured logging, metrics collection, and error tracking
  - Resilience: Robust error handling and retry mechanisms

- **Outbound Adapter (SMTP)**
  - Async email sending with support for plain text, HTML, and attachments
  - TLS support with configurable options
  - Security: Optional message signing placeholder for DKIM/DMARC integration
  - Observability: Structured logging and metrics
  - Resilience: Error handling with detailed failure reporting

---

## Installation

Install dependencies (example):

```bash
pip install aiosmtplib pytest pytest-asyncio
```

Ensure UBP core libraries for security and observability are installed and accessible.

---

## Configuration

Each adapter requires a configuration dictionary with the following common keys:

| Key               | Description                               | Required  | Default                           |
|-------------------|-------------------------------------------|-----------|-----------------------------------|
| `host`            | Email server hostname                     | Yes       | -                                 |
| `port`            | Server port                               | No        | IMAP: 993, POP3: 995, SMTP: 587   |
| `username`        | Login username                            | Yes       | -                                 |
| `password`        | Login password                            | Yes       | -                                 |
| `use_ssl`         | Use SSL/TLS for connection                | No        | True                              |
| `poll_interval`   | Polling interval in seconds (IMAP/POP3)   | No        | 60                                |
| `security_key`    | Key for signing messages/events           | No        | ""                                |
| `from`            | Sender email address (SMTP only)          | No        | username                          |

---

## Usage

### IMAPEmailAdapter & POP3EmailAdapter

```python
adapter = IMAPEmailAdapter(config)  # or POP3EmailAdapter(config)
await adapter.start()

# Adapter polls mailbox, parses emails, and sends UBP events to orchestrator

await adapter.stop()
```

### SMTPEmailAdapter

```python
adapter = SMTPEmailAdapter(config)

message = {
    "to": ["recipient@example.com"],
    "subject": "Hello",
    "content": "Plain text body",
    "html_content": "<p>HTML body</p>",  # Optional
    "attachments": [  # Optional
        {
            "filename": "file.txt",
            "content": b"file content bytes",
            "mime_type": "text/plain"
        }
    ]
}

result = await adapter.send_message(context, message)
if result.success:
    print("Email sent successfully")
else:
    print("Failed to send email:", result.details)
```

---

## Observability & Security

- All adapters integrate with UBP's `StructuredLogger` and `MetricsCollector` for detailed logs and metrics.
- Events and messages are cryptographically signed using `SecurityManager` to ensure integrity and authenticity.
- Metrics include counts of messages sent, failures, polling errors, and mailbox sizes.

---

## Testing

Unit tests are provided for all adapters using `pytest` and `pytest-asyncio`. Tests cover:

- Connection and polling logic with mocked servers
- Email parsing correctness
- Event sending with signature verification
- SMTP sending with various content types and error scenarios

Run tests with:

```bash
pytest
```

---

## Roadmap & TODO

- Support IMAP IDLE for push notifications
- DKIM/DMARC signing for SMTP messages
- Enhanced attachment handling and large message support
- Integration with UBP Orchestrator health checks and self-healing
- Support for OAuth2 authentication for email servers

---

## License

Apache License 2.0

---

## Contact

Michael Landbo (UBP Founder & Principal Architect)
[Unified Bot Protocol](https://www.Unified-Bot-Protocol.com)
GitHub: [L4DK/Unified-Bot-Protocol](https://github.com/L4DK/Unified-Bot-Protocol)
