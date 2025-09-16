# orchestrator/security/compliance.py
from typing import Dict, List, Optional
import json
from datetime import datetime
import hashlib
import hmac
import os

class ComplianceManager:
    def __init__(self):
        self.secret_key = os.urandom(32)

    def create_audit_trail(
        self,
        event_type: str,
        user_id: str,
        action: str,
        data: Dict,
        metadata: Optional[Dict] = None
    ) -> Dict:
        """Create tamper-evident audit trail"""
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
        audit_entry['hmac'] = self._create_hmac(
            json.dumps(audit_entry, sort_keys=True)
        )

        return audit_entry

    def verify_audit_trail(self, audit_entry: Dict) -> bool:
        """Verify audit trail hasn't been tampered with"""
        stored_hmac = audit_entry.pop('hmac', None)
        if not stored_hmac:
            return False

        calculated_hmac = self._create_hmac(
            json.dumps(audit_entry, sort_keys=True)
        )

        return hmac.compare_digest(stored_hmac, calculated_hmac)

    def _create_hmac(self, data: str) -> str:
        """Create HMAC for data integrity"""
        h = hmac.new(self.secret_key, data.encode(), hashlib.sha256)
        return h.hexdigest()

    def sanitize_pii(self, data: Dict) -> Dict:
        """Sanitize personally identifiable information"""
        pii_fields = {'email', 'phone', 'address', 'name', 'ip_address'}

        def _hash_pii(value: str) -> str:
            return hashlib.sha256(value.encode()).hexdigest()[:8]

        sanitized = {}
        for key, value in data.items():
            if key.lower() in pii_fields:
                sanitized[key] = _hash_pii(str(value))
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
        request_data: Dict,
        compliance_rules: Dict
    ) -> List[str]:
        """Validate request against compliance rules"""
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
        data: Dict,
        retention_period: int
    ) -> bool:
        """Check if data meets retention requirements"""
        if 'timestamp' not in data:
            return False

        creation_date = datetime.fromisoformat(data['timestamp'])
        age_days = (datetime.utcnow() - creation_date).days

        return age_days <= retention_period

    def _check_classification_compliance(
        self,
        data: Dict,
        required_level: str
    ) -> bool:
        """Check if data meets classification requirements"""
        classification_levels = {
            'public': 0,
            'internal': 1,
            'confidential': 2,
            'restricted': 3
        }

        data_classification = data.get('classification', 'public')
        return classification_levels[data_classification] >= classification_levels[required_level]

    def _check_geo_compliance(
        self,
        data: Dict,
        allowed_regions: List[str]
    ) -> bool:
        """Check if data meets geographic restrictions"""
        if not allowed_regions:
            return True

        region = data.get('region', '').upper()
        return region in [r.upper() for r in allowed_regions]