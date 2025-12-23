# FilePath: "/DEV/orchestrator/security/threat_protection.py"
# Project: Unified Bot Protocol (UBP)
# Description: Active threat protection module (SQLi, XSS, IP Reputation).
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from typing import Dict, Set, Optional, Any
import ipaddress
import re
import asyncio
from datetime import datetime, timedelta
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

class ThreatProtection:
    """
    Security layer for detecting and blocking malicious requests.
    Features:
    - Pattern matching for SQL Injection, XSS, Path Traversal.
    - IP Reputation checking (Local blacklist + AbuseIPDB).
    - Request header analysis.
    """

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

        # Threat intelligence cache to reduce API calls
        self.threat_intel_cache: Dict[str, Dict] = {}
        self.cache_ttl = timedelta(hours=24)

        # Load IP reputation lists
        self._load_ip_lists()

    def _load_ip_lists(self):
        """Load IP whitelist and blacklist from configuration files."""
        # Note: Paths are relative to where the orchestrator is run
        try:
            with open('config/ip_whitelist.txt', 'r') as f:
                self.ip_whitelist = set(line.strip() for line in f if line.strip())
            with open('config/ip_blacklist.txt', 'r') as f:
                self.ip_blacklist = set(line.strip() for line in f if line.strip())
        except FileNotFoundError:
            logger.warning("IP list configuration files not found. Starting with empty lists.")

    async def check_ip_reputation(self, ip: str) -> Dict[str, Any]:
        """Check IP reputation using threat intelligence APIs (e.g., AbuseIPDB)."""
        # 1. Check Cache
        if ip in self.threat_intel_cache:
            if datetime.now() - self.threat_intel_cache[ip]['timestamp'] < self.cache_ttl:
                return self.threat_intel_cache[ip]['data']

        # 2. Check API
        # TODO: Move API Key to settings.py
        try:
            async with aiohttp.ClientSession() as session:
                # Example using AbuseIPDB API
                async with session.get(
                    f'https://api.abuseipdb.com/api/v2/check',
                    params={'ipAddress': ip},
                    headers={'Key': 'your_api_key', 'Accept': 'application/json'}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.threat_intel_cache[ip] = {
                            'timestamp': datetime.now(),
                            'data': data
                        }
                        return data
                    else:
                        logger.warning(f"AbuseIPDB returned status {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Failed to check IP reputation: {e}")
            return {'error': 'Failed to check IP reputation'}

    def is_ip_suspicious(self, ip: str) -> bool:
        """Check if IP is suspicious based on local behavior patterns."""
        if ip in self.ip_whitelist:
            return False
        if ip in self.ip_blacklist:
            return True
        # Block if suspicious count exceeds threshold (5)
        return self.suspicious_ips.get(ip, 0) >= 5

    def detect_threats(self, payload: Dict) -> Optional[str]:
        """Scan request payload for known attack patterns."""
        try:
            payload_str = json.dumps(payload)
        except (TypeError, ValueError):
            return None

        for threat_type, pattern in self.suspicious_patterns.items():
            if re.search(pattern, payload_str):
                return threat_type
        return None

    async def analyze_request(
        self,
        ip: str,
        payload: Dict,
        headers: Dict
    ) -> Dict[str, Any]:
        """
        Comprehensive request analysis.
        Returns a decision dictionary.
        """
        results = {
            'blocked': False,
            'reason': None,
            'risk_level': 'low',
            'actions': []
        }

        # 1. Check IP Reputation (Local)
        if ip in self.blocked_ips or self.is_ip_suspicious(ip):
            results.update({
                'blocked': True,
                'reason': 'IP previously blocked or suspicious',
                'risk_level': 'high'
            })
            return results

        # 2. Check for threats in payload (Injection attacks)
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

        # 3. Analyze headers for suspicious patterns (Bots/Scrapers)
        if self._analyze_headers(headers):
            results['risk_level'] = 'medium'
            results['actions'].append('enhanced_monitoring')

        return results

    def _analyze_headers(self, headers: Dict) -> bool:
        """Analyze request headers for suspicious user agents or proxy chains."""
        suspicious_headers = {
            'x-forwarded-for': r'^.*,.*,.*',  # Multiple proxy hops often indicate masking
            'user-agent': r'(?i)(curl|wget|python-requests|postman|scrappy)',
            'accept': r'^$',  # Empty accept header is rare for real browsers
        }

        for header, pattern in suspicious_headers.items():
            # Header keys are usually case-insensitive, but here we assume lowercase dict if pre-processed
            header_val = headers.get(header) or headers.get(header.title())
            if header_val and re.match(pattern, header_val):
                return True
        return False
