"""
FilePath: "/DEV/orchestrator/security/rate_limiter.py"
Project: Unified Bot Protocol (UBP)
Component: Security Rate Limiter
Description: Implements in-memory rate limiting (Sliding Window) for API protection.
Author: "Michael Landbo"
Date created: "21/12/2025"
Date Modified: "27/12/2025"
Version: "1.1.1"
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

# Setup Logging
logger = logging.getLogger(__name__)


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
            "default": (100, 60),  # 100 requests per minute
            "registration": (10, 60),  # 10 bot registrations per minute
            "connection": (5, 60),  # 5 connection attempts per minute
            "auth": (5, 300),  # 5 auth attempts per 5 minutes
        }
        logger.info("RateLimiter initialized with limits: %s", self.api_limits)

    async def is_rate_limited(
        self, identifier: str, limit_type: str = "default"
    ) -> Tuple[bool, int]:
        """
        Check if the identifier is rate limited.
        Returns: (is_limited: bool, retry_after_seconds: int)
        """
        max_requests, window = self.api_limits.get(
            limit_type, self.api_limits["default"]
        )

        async with self._lock:
            # Use timezone-aware UTC datetime
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(seconds=window)

            # Initialize request history if new identifier
            if identifier not in self._requests:
                self._requests[identifier] = []

            # Clean old requests (Sliding Window cleanup)
            # Filter keeps only timestamps within the current window
            self._requests[identifier] = [
                ts for ts in self._requests[identifier] if ts > window_start
            ]

            # Check if limit is exceeded
            if len(self._requests[identifier]) >= max_requests:
                # Calculate time to wait until the oldest request expires
                oldest = min(self._requests[identifier])
                retry_after = int(
                    (oldest + timedelta(seconds=window) - now).total_seconds()
                )
                retry_after = max(1, retry_after)

                logger.warning(
                    "Rate limit hit: Identifier=%s, Type=%s, Blocked for %ds",
                    identifier,
                    limit_type,
                    retry_after,
                )
                return True, retry_after

            # Add new request timestamp
            self._requests[identifier].append(now)
            return False, 0

    async def cleanup(self):
        """
        Periodic cleanup task to remove stale entries and prevent memory leaks.
        Should be called by a background task loop.
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            # Find the maximum window size across all limits
            max_window = max(w for _, w in self.api_limits.values())
            global_window_start = now - timedelta(seconds=max_window)

            initial_count = len(self._requests)

            # Iterate over a copy of keys to allow deletion during iteration
            for identifier in list(self._requests.keys()):
                # Filter valid timestamps
                self._requests[identifier] = [
                    ts for ts in self._requests[identifier] if ts > global_window_start
                ]

                # Remove identifier if no requests remain
                if not self._requests[identifier]:
                    del self._requests[identifier]

            final_count = len(self._requests)
            if initial_count != final_count:
                logger.debug(
                    "RateLimiter cleanup: Removed %d stale identifiers. Active: %d",
                    initial_count - final_count,
                    final_count,
                )
