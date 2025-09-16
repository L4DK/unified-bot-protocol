# orchestrator/security/threat_protection.py
from typing import Dict, Set, Optional
import ipaddress
import re
import asyncio
from datetime import datetime, timedelta
import aiohttp
import json

class ThreatProtection:
    def __init__(self):
        self.suspicious_patterns = {
            'sql_injection': r'(?i)(union|select|insert|delete|update|drop|;|--)',
            'xss': r'(?i)<script|javascript:|data:text/html|base64',
            'path_traversal': r'\.{2}[/\\]',
            'command_injection': r'[;&|`]|\/bin\/(?:ba)?sh'
        }

        self.blocked_ips: Set[str] = set()
        self.suspicious_ips: Dict[str, int] = {}
        self.ip_whitelist: Set[str] = set()
        self.ip_blacklist: Set[str] = set()

        # Threat intelligence cache
        self.threat_intel_cache: Dict[str, Dict] = {}
        self.cache_ttl = timedelta(hours=24)

        # Load IP reputation lists
        self._load_ip_lists()

    def _load_ip_lists(self):
        """Load IP whitelist and blacklist from configuration"""
        try:
            with open('config/ip_whitelist.txt', 'r') as f:
                self.ip_whitelist = set(line.strip() for line in f)
            with open('config/ip_blacklist.txt', 'r') as f:
                self.ip_blacklist = set(line.strip() for line in f)
        except FileNotFoundError:
            pass

    async def check_ip_reputation(self, ip: str) -> Dict:
        """Check IP reputation using threat intelligence APIs"""
        if ip in self.threat_intel_cache:
            if datetime.now() - self.threat_intel_cache[ip]['timestamp'] < self.cache_ttl:
                return self.threat_intel_cache[ip]['data']

        try:
            async with aiohttp.ClientSession() as session:
                # Example using AbuseIPDB API (you would need an API key)
                async with session.get(
                    f'https://api.abuseipdb.com/api/v2/check',
                    params={'ipAddress': ip},
                    headers={'Key': 'your_api_key'}
                ) as response:
                    data = await response.json()

                    self.threat_intel_cache[ip] = {
                        'timestamp': datetime.now(),
                        'data': data
                    }
                    return data
        except Exception:
            return {'error': 'Failed to check IP reputation'}

    def is_ip_suspicious(self, ip: str) -> bool:
        """Check if IP is suspicious based on behavior patterns"""
        if ip in self.ip_whitelist:
            return False
        if ip in self.ip_blacklist:
            return True
        return self.suspicious_ips.get(ip, 0) >= 5

    def detect_threats(self, payload: Dict) -> Optional[str]:
        """Detect potential threats in the request payload"""
        payload_str = json.dumps(payload)

        for threat_type, pattern in self.suspicious_patterns.items():
            if re.search(pattern, payload_str):
                return threat_type
        return None

    async def analyze_request(
        self,
        ip: str,
        payload: Dict,
        headers: Dict
    ) -> Dict[str, any]:
        """Comprehensive request analysis"""
        results = {
            'blocked': False,
            'reason': None,
            'risk_level': 'low',
            'actions': []
        }

        # Check IP reputation
        if ip in self.blocked_ips:
            results.update({
                'blocked': True,
                'reason': 'IP previously blocked',
                'risk_level': 'high'
            })
            return results

        # Check for threats in payload
        threat_type = self.detect_threats(payload)
        if threat_type:
            self.suspicious_ips[ip] = self.suspicious_ips.get(ip, 0) + 1
            results.update({
                'blocked': True,
                'reason': f'Detected {threat_type}',
                'risk_level': 'high',
                'actions': ['increment_suspicious_count', 'log_threat']
            })
            return results

        # Analyze headers for suspicious patterns
        if self._analyze_headers(headers):
            results['risk_level'] = 'medium'
            results['actions'].append('enhanced_monitoring')

        return results

    def _analyze_headers(self, headers: Dict) -> bool:
        """Analyze request headers for suspicious patterns"""
        suspicious_headers = {
            'x-forwarded-for': r'^.*,.*,.*',  # Multiple proxy hops
            'user-agent': r'(?i)(curl|wget|python-requests|postman)',
            'accept': r'^$',  # Empty accept header
        }

        for header, pattern in suspicious_headers.items():
            if header in headers and re.match(pattern, headers[header]):
                return True
        return False