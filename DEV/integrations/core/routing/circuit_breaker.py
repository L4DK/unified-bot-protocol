# filepath: core/routing/circuit_breaker.py
# project: Unified Bot Protocol (UBP)
# module: Circuit Breaker
# version: 0.1.0
# last_edited: 2025-09-16
# author: Michael Landbo (UBP BDFL)
# license: Apache-2.0
# description:
#   Classic circuit breaker with open/half-open/closed states and probe requests.
#
# changelog:
# - 0.1.0: Initial creation.
#
# TODO:
# - Expose breaker state via Management API
# - Add sliding window failure rate breaker variant

from __future__ import annotations
from typing import Dict
import asyncio
import time
import enum

class BreakerState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, open_interval_sec: int = 30, half_open_max_concurrent: int = 1):
        self.state = BreakerState.CLOSED
        self.failure_threshold = failure_threshold
        self.open_interval_sec = open_interval_sec
        self.half_open_max_concurrent = half_open_max_concurrent
        self.fail_count = 0
        self.opened_at = 0.0
        self._half_open_in_flight = 0

    def allow(self) -> bool:
        now = time.time()
        if self.state == BreakerState.OPEN and (now - self.opened_at) >= self.open_interval_sec:
            self.state = BreakerState.HALF_OPEN
            self._half_open_in_flight = 0

        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            return False
        if self.state == BreakerState.HALF_OPEN:
            if self._half_open_in_flight < self.half_open_max_concurrent:
                self._half_open_in_flight += 1
                return True
            return False
        return False

    def record_success(self):
        if self.state in (BreakerState.OPEN, BreakerState.HALF_OPEN):
            self.state = BreakerState.CLOSED
            self.fail_count = 0
            self._half_open_in_flight = 0
        else:
            self.fail_count = 0

    def record_failure(self):
        self.fail_count += 1
        if self.state == BreakerState.HALF_OPEN:
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
            self._half_open_in_flight = 0
        elif self.fail_count >= self.failure_threshold:
            self.state = BreakerState.OPEN
            self.opened_at = time.time()