# orchestrator/security/zero_trust.py
from typing import Dict, Optional, Tuple
import jwt
import time
import hashlib
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.primitives import serialization
import base64
import os

class ZeroTrustManager:
    def __init__(self):
        self.session_store = {}
        self.device_fingerprints = {}
        self.trust_scores = {}
        self.jwt_secret = os.urandom(32)
        self.certificate_store = {}

    async def verify_identity(
        self,
        bot_id: str,
        credentials: Dict,
        context: Dict
    ) -> Tuple[bool, Dict]:
        """
        Implement Zero Trust verification using multiple factors
        Returns (is_verified, context)
        """
        trust_score = 0
        verification_results = {}

        # 1. Certificate-based authentication
        cert_valid = await self._verify_certificate(
            bot_id,
            credentials.get('certificate')
        )
        if cert_valid:
            trust_score += 30
            verification_results['cert_auth'] = True

        # 2. Device fingerprint verification
        device_verified = await self._verify_device_fingerprint(
            bot_id,
            context.get('device_fingerprint')
        )
        if device_verified:
            trust_score += 20
            verification_results['device_auth'] = True

        # 3. Behavioral analysis
        behavior_score = await self._analyze_behavior(bot_id, context)
        trust_score += behavior_score
        verification_results['behavior_score'] = behavior_score

        # 4. Context validation
        context_score = await self._validate_context(context)
        trust_score += context_score
        verification_results['context_score'] = context_score

        # Store trust score
        self.trust_scores[bot_id] = trust_score

        return trust_score >= 70, {
            'trust_score': trust_score,
            'verification_results': verification_results
        }

    async def _verify_certificate(
        self,
        bot_id: str,
        cert_data: Optional[str]
    ) -> bool:
        """Verify bot's certificate"""
        if not cert_data:
            return False

        try:
            cert = load_pem_x509_certificate(cert_data.encode())

            # Verify certificate is not expired
            if cert.not_valid_after < time.time():
                return False

            # Verify certificate is in our store
            cert_fingerprint = cert.fingerprint(hashlib.sha256())
            return cert_fingerprint in self.certificate_store

        except Exception:
            return False

    async def _verify_device_fingerprint(
        self,
        bot_id: str,
        fingerprint: Optional[Dict]
    ) -> bool:
        """Verify bot's device fingerprint"""
        if not fingerprint:
            return False

        stored_fingerprint = self.device_fingerprints.get(bot_id)
        if not stored_fingerprint:
            # First time seeing this device, store it
            self.device_fingerprints[bot_id] = fingerprint
            return True

        # Compare fingerprint components
        match_score = sum(
            1 for k, v in fingerprint.items()
            if stored_fingerprint.get(k) == v
        ) / len(fingerprint)

        return match_score >= 0.8

    async def _analyze_behavior(self, bot_id: str, context: Dict) -> int:
        """Analyze bot's behavior for anomalies"""
        score = 0

        # Check command patterns
        if self._is_normal_command_pattern(
            context.get('recent_commands', [])
        ):
            score += 10

        # Check timing patterns
        if self._is_normal_timing_pattern(
            context.get('command_timestamps', [])
        ):
            score += 10

        # Check resource usage
        if self._is_normal_resource_usage(
            context.get('resource_metrics', {})
        ):
            score += 10

        return score

    async def _validate_context(self, context: Dict) -> int:
        """Validate request context"""
        score = 0

        # Network context
        if self._is_valid_network_context(context.get('network', {})):
            score += 10

        # Time context
        if self._is_valid_time_context(context.get('time', {})):
            score += 10

        # Location context
        if self._is_valid_location_context(context.get('location', {})):
            score += 10

        return score

    def generate_session_token(
        self,
        bot_id: str,
        trust_score: int,
        context: Dict
    ) -> str:
        """Generate a short-lived session token"""
        payload = {
            'bot_id': bot_id,
            'trust_score': trust_score,
            'context_hash': self._hash_context(context),
            'exp': time.time() + 3600  # 1 hour expiration
        }

        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')

    def verify_session_token(
        self,
        token: str,
        context: Dict
    ) -> Tuple[bool, Optional[str]]:
        """Verify session token and context"""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=['HS256']
            )

            # Verify context hasn't changed significantly
            current_context_hash = self._hash_context(context)
            if payload['context_hash'] != current_context_hash:
                return False, 'Context mismatch'

            # Verify trust score hasn't decreased
            current_trust_score = self.trust_scores.get(
                payload['bot_id'],
                0
            )
            if current_trust_score < payload['trust_score'] * 0.8:
                return False, 'Trust score decreased'

            return True, None

        except jwt.ExpiredSignatureError:
            return False, 'Token expired'
        except jwt.InvalidTokenError:
            return False, 'Invalid token'

    def _hash_context(self, context: Dict) -> str:
        """Create a hash of context for comparison"""
        context_str = json.dumps(context, sort_keys=True)
        return hashlib.sha256(context_str.encode()).hexdigest()

    def _is_normal_command_pattern(self, commands: List[str]) -> bool:
        """Check if command sequence follows normal patterns"""
        if not commands:
            return True

        # Add pattern recognition logic here
        return True

    def _is_normal_timing_pattern(self, timestamps: List[float]) -> bool:
        """Check if command timing follows normal patterns"""
        if not timestamps:
            return True

        # Add timing analysis logic here
        return True

    def _is_normal_resource_usage(self, metrics: Dict) -> bool:
        """Check if resource usage is within normal ranges"""
        if not metrics:
            return True

        cpu_usage = metrics.get('cpu_usage', 0)
        memory_usage = metrics.get('memory_usage', 0)

        return cpu_usage < 80 and memory_usage < 80

    def _is_valid_network_context(self, network: Dict) -> bool:
        """Validate network context"""
        if not network:
            return False

        required_fields = {'ip', 'protocol', 'port'}
        return all(field in network for field in required_fields)

    def _is_valid_time_context(self, time_context: Dict) -> bool:
        """Validate time-based context"""
        if not time_context:
            return False

        current_hour = datetime.now().hour
        allowed_hours = time_context.get('allowed_hours', range(24))

        return current_hour in allowed_hours

    def _is_valid_location_context(self, location: Dict) -> bool:
        """Validate location context"""
        if not location:
            return False

        required_fields = {'country', 'region'}
        return all(field in location for field in required_fields)