# orchestrator/security/secure_handler.py
import datetime
import json
from .threat_protection import ThreatProtection
from .secure_communication import SecureCommunication
from .compliance_manager import ComplianceManager
from typing import Dict, Optional
import logging

class SecureRequestHandler:
    def __init__(self):
        self.threat_protection = ThreatProtection()
        self.secure_comm = SecureCommunication()
        self.compliance_manager = ComplianceManager()
        self.logger = logging.getLogger("security")

    async def handle_secure_request(
        self,
        request_id: str,
        ip_address: str,
        headers: Dict,
        payload: Dict,
        compliance_rules: Optional[Dict] = None
    ) -> Dict:
        """Handle incoming request with full security stack"""

        try:
            # 1. Threat Analysis
            threat_analysis = await self.threat_protection.analyze_request(
                ip_address,
                payload,
                headers
            )

            if threat_analysis['blocked']:
                await self._log_security_event(
                    'THREAT_DETECTED',
                    request_id,
                    ip_address,
                    threat_analysis
                )
                return {
                    'status': 'BLOCKED',
                    'reason': threat_analysis['reason']
                }

            # 2. Compliance Check
            if compliance_rules:
                violations = self.compliance_manager.validate_compliance(
                    payload,
                    compliance_rules
                )

                if violations:
                    await self._log_security_event(
                        'COMPLIANCE_VIOLATION',
                        request_id,
                        ip_address,
                        {'violations': violations}
                    )
                    return {
                        'status': 'REJECTED',
                        'reason': 'Compliance violations',
                        'violations': violations
                    }

            # 3. Sanitize PII
            sanitized_payload = self.compliance_manager.sanitize_pii(payload)

            # 4. Create Audit Trail
            audit_entry = self.compliance_manager.create_audit_trail(
                'SECURE_REQUEST',
                request_id,
                'process_request',
                sanitized_payload,
                {
                    'ip_address': ip_address,
                    'risk_level': threat_analysis['risk_level']
                }
            )

            # 5. Secure Communication
            if threat_analysis['risk_level'] == 'medium':
                # Establish secure session for medium-risk requests
                session_key, iv = self.secure_comm.generate_session_key()
                encrypted_response = self.secure_comm.encrypt_message(
                    json.dumps(sanitized_payload),
                    session_key,
                    iv
                )

                return {
                    'status': 'SUCCESS',
                    'encrypted_data': encrypted_response,
                    'session_key': self.secure_comm.encrypt_session_key(
                        session_key,
                        self.secure_comm.get_public_key()
                    )
                }

            return {
                'status': 'SUCCESS',
                'data': sanitized_payload,
                'audit_id': audit_entry.get('id')
            }

        except Exception as e:
            self.logger.error(f"Security handler error: {str(e)}", exc_info=True)
            return {
                'status': 'ERROR',
                'reason': 'Internal security error'
            }

    async def _log_security_event(
        self,
        event_type: str,
        request_id: str,
        ip_address: str,
        details: Dict
    ):
        """Log security events with proper formatting"""
        self.logger.info(
            json.dumps(
                {
                    "event_type": event_type,
                    "request_id": request_id,
                    "ip_address": ip_address,
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "details": details,
                }
            )
        )
