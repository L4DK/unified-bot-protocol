# FilePath: "/DEV/orchestrator/security/rate_limiter.py"
# Project: Unified Bot Protocol (UBP)
# Description: Implements in-memory rate limiting (Sliding Window) for API protection.
# Author: "Michael Landbo"
# Date created: "21/12/2025"
# Date Modified: "21/12/2025"
# Version: "v.1.0.0"

from datetime import datetime, timedelta
import asyncio
from typing import Dict, Tuple

class RateLimiter:
    """
    Implements rate limiting for API endpoints and connections using a sliding window algorithm.
    Current Implementation: In-Memory (Not distributed).
    Future Roadmap: Move to Redis for distributed rate limiting.
    """

    def __init__(self):
        self._requests: Dict[str, list] = {}  # Map: IP/ID -> list of timestamps
        self._lock = asyncio.Lock()

        # Configure limits (requests, seconds)
        self.api_limits = {
            "default": (100, 60),      # 100 requests per minute
            "registration": (10, 60),  # 10 bot registrations per minute
            "connection": (5, 60),     # 5 connection attempts per minute
            "auth": (5, 300),          # 5 auth attempts per 5 minutes
        }

    async def is_rate_limited(
        self,
        identifier: str,
        limit_type: str = "default"
    ) -> Tuple[bool, int]:
        """
        Check if the identifier is rate limited.
        Returns: (is_limited: bool, retry_after_seconds: int)
        """
        max_requests, window = self.api_limits.get(limit_type, self.api_limits["default"])

        async with self._lock:
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=window)

            # Initialize request history if new identifier
            if identifier not in self._requests:
                self._requests[identifier] = []

            # Clean old requests (Sliding Window cleanup)
            # Filter keeps only timestamps within the current window
            self._requests[identifier] = [
                ts for ts in self._requests[identifier]
                if ts > window_start
            ]

            # Check if limit is exceeded
            if len(self._requests[identifier]) >= max_requests:
                # Calculate time to wait until the oldest request expires
                oldest = min(self._requests[identifier])
                retry_after = int((oldest + timedelta(seconds=window) - now).total_seconds())
                # Ensure retry_after is at least 1 second
                return True, max(1, retry_after)

            # Add new request timestamp
            self._requests[identifier].append(now)
            return False, 0

    async def cleanup(self):
        """
        Periodic cleanup task to remove stale entries and prevent memory leaks.
        Should be called by a background task loop.
        """
        async with self._lock:
            now = datetime.utcnow()
            # Find the maximum window size across all limits
            max_window = max(w for _, w in self.api_limits.values())
            global_window_start = now - timedelta(seconds=max_window)

            # Iterate over a copy of keys to allow deletion during iteration
            for identifier in list(self._requests.keys()):
                # Filter valid timestamps
                self._requests[identifier] = [
                    ts for ts in self._requests[identifier]
                    if ts > global_window_start
                ]

                # Remove identifier if no requests remain
                if not self._requests[identifier]:
                    del self._requests[identifier]
