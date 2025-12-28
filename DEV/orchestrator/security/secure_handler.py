"""
FilePath: "/DEV/orchestrator/security/secure_handler.py"
Project: Unified Bot Protocol (UBP)
Component: Secure Request Orchestrator
Description: Orchestrates security checks (Threats, Compliance, Encryption) for requests.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "27/12/2025"
Version: "1.1.0"
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

# Internal imports
from .compliance_manager import ComplianceManager
from .secure_communication import SecureCommunication
from .threat_protection import ThreatProtection


class SecureRequestHandler:
    """
    Central security handler that pipes requests through the security stack:
    1. Threat Protection (IP/Payload analysis)
    2. Compliance (GDPR/PII checks)
    3. Audit Logging
    4. Secure Communication (Encryption)
    """

    def __init__(self):
        self.threat_protection = ThreatProtection()
        self.secure_comm = SecureCommunication()
        self.compliance_manager = ComplianceManager()
        self.logger = logging.getLogger("ubp.security.handler")

    async def handle_secure_request(
        self,
        request_id: str,
        ip_address: str,
        headers: Dict,
        payload: Dict,
        compliance_rules: Optional[Dict] = None,
    ) -> Dict:
        """
        Handle incoming request with full security stack.
        Returns a dictionary with status and data (or error details).
        """

        try:
            # 1. Threat Analysis
            threat_analysis = await self.threat_protection.analyze_request(
                ip_address, payload, headers
            )

            if threat_analysis["blocked"]:
                await self._log_security_event(
                    "THREAT_DETECTED", request_id, ip_address, threat_analysis
                )
                return {
                    "status": "BLOCKED",
                    "reason": threat_analysis["reason"],
                }

            # 2. Compliance Check
            if compliance_rules:
                violations = self.compliance_manager.validate_compliance(
                    payload, compliance_rules
                )

                if violations:
                    await self._log_security_event(
                        "COMPLIANCE_VIOLATION",
                        request_id,
                        ip_address,
                        {"violations": violations},
                    )
                    return {
                        "status": "REJECTED",
                        "reason": "Compliance violations",
                        "violations": violations,
                    }

            # 3. Sanitize PII
            # We sanitize the payload before processing/logging to prevent PII leaks in logs
            sanitized_payload = self.compliance_manager.sanitize_pii(payload)

            # 4. Create Audit Trail
            audit_entry = self.compliance_manager.create_audit_trail(
                "SECURE_REQUEST",
                request_id,
                "process_request",
                sanitized_payload,
                {
                    "ip_address": ip_address,
                    "risk_level": threat_analysis["risk_level"],
                },
            )

            # 5. Secure Communication (Encryption for high/medium risk)
            if threat_analysis["risk_level"] == "medium":
                # Establish secure session for medium-risk requests
                session_key, iv = self.secure_comm.generate_session_key()

                encrypted_response = self.secure_comm.encrypt_message(
                    json.dumps(sanitized_payload), session_key, iv
                )

                return {
                    "status": "SUCCESS",
                    "encrypted_data": encrypted_response,
                    "session_key": self.secure_comm.encrypt_session_key(
                        session_key, self.secure_comm.get_public_key()
                    ),
                }

            # Default: Return sanitized data
            return {
                "status": "SUCCESS",
                "data": sanitized_payload,
                "audit_id": audit_entry.get("id"),
            }

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Security handler error: %s", str(e), exc_info=True)
            return {"status": "ERROR", "reason": "Internal security error"}

    async def _log_security_event(
        self, event_type: str, request_id: str, ip_address: str, details: Dict
    ):
        """Log security events with proper JSON formatting for ingestion tools."""
        self.logger.info(
            json.dumps(
                {
                    "event_type": event_type,
                    "request_id": request_id,
                    "ip_address": ip_address,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "details": details,
                }
            )
        )
