# orchestrator/security/rate_limiter.py
from datetime import datetime, timedelta
import asyncio
from typing import Dict, Tuple

class RateLimiter:
    """Implements rate limiting for API endpoints and connections"""

    def __init__(self):
        self._requests: Dict[str, list] = {}  # IP/ID -> list of timestamps
        self._lock = asyncio.Lock()

        # Configure limits
        self.api_limits = {
            "default": (100, 60),  # 100 requests per minute
            "registration": (10, 60),  # 10 registrations per minute
            "connection": (5, 60),  # 5 connection attempts per minute
        }

    async def is_rate_limited(
        self,
        identifier: str,
        limit_type: str = "default"
    ) -> Tuple[bool, int]:
        """
        Check if the identifier is rate limited
        Returns (is_limited, retry_after_seconds)
        """
        max_requests, window = self.api_limits.get(limit_type, self.api_limits["default"])

        async with self._lock:
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=window)

            # Initialize or update request history
            if identifier not in self._requests:
                self._requests[identifier] = []

            # Clean old requests
            self._requests[identifier] = [
                ts for ts in self._requests[identifier]
                if ts > window_start
            ]

            # Check limit
            if len(self._requests[identifier]) >= max_requests:
                oldest = min(self._requests[identifier])
                retry_after = int((oldest + timedelta(seconds=window) - now).total_seconds())
                return True, retry_after

            # Add new request
            self._requests[identifier].append(now)
            return False, 0

    async def cleanup(self):
        """Remove old entries to prevent memory growth"""
        async with self._lock:
            now = datetime.utcnow()
            for identifier in list(self._requests.keys()):
                window_start = now - timedelta(seconds=max(w for _, w in self.api_limits.values()))
                self._requests[identifier] = [
                    ts for ts in self._requests[identifier]
                    if ts > window_start
                ]
                if not self._requests[identifier]:
                    del self._requests[identifier]