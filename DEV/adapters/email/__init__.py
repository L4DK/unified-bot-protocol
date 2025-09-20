# adapters/email/__init__.py
"""
Email Adapters Package for Unified Bot Protocol (UBP)

Includes:
- SMTPEmailAdapter: Async outbound SMTP email sending
- IMAPEmailAdapter: Inbound email fetching via IMAP
- POP3EmailAdapter: Inbound email fetching via POP3

Author: Michael Landbo (UBP BDFL)
License: Apache-2.0
"""

from .email_smtp import SMTPEmailAdapter
from .email_imap import IMAPEmailAdapter
from .email_pop3 import POP3EmailAdapter

__all__ = [
    "SMTPEmailAdapter",
    "IMAPEmailAdapter",
    "POP3EmailAdapter",
]
