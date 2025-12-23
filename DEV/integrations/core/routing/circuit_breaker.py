# FilePath: "/DEV/integrations/core/routing/circuit_breaker.py"
# Project: Unified Bot Protocol (UBP)
# Module: Circuit Breaker
# Version: 0.1.0
# Last_edited: 2025-12-22
# Author: "Michael Landbo"
# License: Apache-2.0
# Description:
#   Classic circuit breaker with open/half-open/closed states and probe requests.
#
# Changelog:
# - 0.1.0: Initial creation.

from __future__ import annotations
import time
import enum

class BreakerState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """
    Implements the Circuit Breaker pattern to prevent cascading failures.
    """
    def __init__(self, failure_threshold: int = 5, open_interval_sec: int = 30, half_open_max_concurrent: int = 1):
        self.state = BreakerState.CLOSED
        self.failure_threshold = failure_threshold
        self.open_interval_sec = open_interval_sec
        self.half_open_max_concurrent = half_open_max_concurrent

        self.fail_count = 0
        self.opened_at = 0.0
        self._half_open_in_flight = 0

    def allow(self) -> bool:
        """
        Determines if a request should be allowed to proceed based on the current state.
        """
        now = time.time()

        # Transition from OPEN to HALF_OPEN if timeout has passed
        if self.state == BreakerState.OPEN and (now - self.opened_at) >= self.open_interval_sec:
            self.state = BreakerState.HALF_OPEN
            self._half_open_in_flight = 0

        if self.state == BreakerState.CLOSED:
            return True

        if self.state == BreakerState.OPEN:
            return False

        if self.state == BreakerState.HALF_OPEN:
            # Allow limited number of probe requests
            if self._half_open_in_flight < self.half_open_max_concurrent:
                self._half_open_in_flight += 1
                return True
            return False

        return False

    def record_success(self):
        """
        Records a successful request. Resets failures and closes the circuit if half-open.
        """
        if self.state in (BreakerState.OPEN, BreakerState.HALF_OPEN):
            self.state = BreakerState.CLOSED
            self.fail_count = 0
            self._half_open_in_flight = 0
        else:
            self.fail_count = 0

    def record_failure(self):
        """
        Records a failed request. Trips the circuit if threshold is reached.
        """
        self.fail_count += 1

        if self.state == BreakerState.HALF_OPEN:
            # If a probe fails, immediately re-open
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
            self._half_open_in_flight = 0

        elif self.fail_count >= self.failure_threshold:
            # Trip circuit in CLOSED state if threshold reached
            self.state = BreakerState.OPEN
            self.opened_at = time.time()
