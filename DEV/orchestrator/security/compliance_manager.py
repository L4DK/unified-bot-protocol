# FilePath: "/DEV/orchestrator/security/compliance_manager.py"
# Project: Unified Bot Protocol (UBP)
# Description: Manages compliance checks, audit trails (HMAC-signed), and PII sanitization.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, List, Optional, Any
import json
from datetime import datetime
import hashlib
import hmac
import os

class ComplianceManager:
    """
    Ensures regulatory compliance by:
    1. Creating tamper-evident audit trails (using HMAC).
    2. Sanitizing PII (Personally Identifiable Information) from logs.
    3. Validating requests against defined compliance rules (retention, geo-fencing).
    """

    def __init__(self):
        # In production, load this from a secure key manager (Vault/Secrets)
        self.secret_key = os.urandom(32)

    def create_audit_trail(
        self,
        event_type: str,
        user_id: str,
        action: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a tamper-evident audit trail entry."""
        timestamp = datetime.utcnow().isoformat()

        audit_entry = {
            'event_type': event_type,
            'user_id': user_id,
            'action': action,
            'timestamp': timestamp,
            'data': data,
            'metadata': metadata or {}
        }

        # Create HMAC for tamper detection
        # We serialize with sort_keys=True to ensure consistent hashing
        audit_entry['hmac'] = self._create_hmac(
            json.dumps(audit_entry, sort_keys=True)
        )

        return audit_entry

    def verify_audit_trail(self, audit_entry: Dict[str, Any]) -> bool:
        """Verify that an audit trail entry hasn't been tampered with."""
        # Create a copy to avoid modifying the original dictionary
        entry_copy = audit_entry.copy()

        stored_hmac = entry_copy.pop('hmac', None)
        if not stored_hmac:
            return False

        # Recalculate HMAC based on the data
        calculated_hmac = self._create_hmac(
            json.dumps(entry_copy, sort_keys=True)
        )

        return hmac.compare_digest(stored_hmac, calculated_hmac)

    def _create_hmac(self, data: str) -> str:
        """Create HMAC-SHA256 for data integrity."""
        h = hmac.new(self.secret_key, data.encode(), hashlib.sha256)
        return h.hexdigest()

    def sanitize_pii(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitize Personally Identifiable Information (PII).
        Replaces sensitive fields with their SHA-256 hash (truncated).
        """
        pii_fields = {'email', 'phone', 'address', 'name', 'ip_address', 'password', 'token'}

        def _hash_pii(value: str) -> str:
            return hashlib.sha256(str(value).encode()).hexdigest()[:8]

        sanitized = {}
        for key, value in data.items():
            if key.lower() in pii_fields:
                sanitized[key] = f"REDACTED-{_hash_pii(str(value))}"
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_pii(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_pii(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def validate_compliance(
        self,
        request_data: Dict[str, Any],
        compliance_rules: Dict[str, Any]
    ) -> List[str]:
        """Validate a request against a set of compliance rules."""
        violations = []

        # Check data retention rules
        if 'retention' in compliance_rules:
            retention_period = compliance_rules['retention'].get('period_days', 30)
            if not self._check_retention_compliance(request_data, retention_period):
                violations.append('retention_period_exceeded')

        # Check data classification
        if 'classification' in compliance_rules:
            required_classification = compliance_rules['classification'].get('level', 'public')
            if not self._check_classification_compliance(request_data, required_classification):
                violations.append('invalid_data_classification')

        # Check geographic restrictions
        if 'geo_restrictions' in compliance_rules:
            allowed_regions = compliance_rules['geo_restrictions'].get('allowed_regions', [])
            if not self._check_geo_compliance(request_data, allowed_regions):
                violations.append('geographic_restriction_violation')

        return violations

    def _check_retention_compliance(
        self,
        data: Dict[str, Any],
        retention_period: int
    ) -> bool:
        """Check if data falls within the allowed retention period."""
        if 'timestamp' not in data:
            # If no timestamp, we assume compliance (or handle policy otherwise)
            return True

        try:
            creation_date = datetime.fromisoformat(data['timestamp'])
            age_days = (datetime.utcnow() - creation_date).days
            return age_days <= retention_period
        except (ValueError, TypeError):
            return False

    def _check_classification_compliance(
        self,
        data: Dict[str, Any],
        required_level: str
    ) -> bool:
        """
        Check if data meets classification requirements.
        Hierarchy: public < internal < confidential < restricted
        """
        classification_levels = {
            'public': 0,
            'internal': 1,
            'confidential': 2,
            'restricted': 3
        }

        data_classification = data.get('classification', 'public').lower()
        required_level = required_level.lower()

        # Ensure valid levels
        data_level_score = classification_levels.get(data_classification, 0)
        req_level_score = classification_levels.get(required_level, 0)

        # Logic: If data is 'restricted' (3), it meets requirement for 'public' (0).
        # But if we require 'internal' (1) and data is 'public' (0), it might fail depending on context.
        # Here we assume: Does the data's classification label meet the required MINIMUM security level?
        return data_level_score >= req_level_score

    def _check_geo_compliance(
        self,
        data: Dict[str, Any],
        allowed_regions: List[str]
    ) -> bool:
        """Check if data origin meets geographic restrictions."""
        if not allowed_regions:
            return True

        region = data.get('region', '').upper()
        return region in [r.upper() for r in allowed_regions]
