# FilePath: "/DEV/orchestrator/security/__init__.py"
# Project: Unified Bot Protocol (UBP)
# Description: Security module initialization. Exposes all security managers and handlers.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

"""Security module for UBP"""

from .audit import AuditLogger
from .authenticator import SecureBotAuthenticator
from .compliance_manager import ComplianceManager
from .encryption import CredentialEncryption
from .rate_limiter import RateLimiter
from .secure_communication import SecureCommunication
from .zero_trust import ZeroTrustManager
from .secure_handler import SecureRequestHandler
from .threat_protection import ThreatProtection

__all__ = [
    "AuditLogger",
    "SecureBotAuthenticator",
    "ComplianceManager",
    "CredentialEncryption",
    "RateLimiter",
    "SecureCommunication",
    "ZeroTrustManager",
    "SecureRequestHandler",
    "ThreatProtection",
]
