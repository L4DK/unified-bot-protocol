# filepath: core/routing/message_router.py
# project: Unified Bot Protocol (UBP)
# component: Message Router (Intelligent Multi-Platform Routing Engine)
# license: Apache-2.0
# author: Michael Landbo (Founder & BDFL of UBP)
# description:
#   Intelligent message routing system integrating AdapterRegistry, PolicyEngine,
#   LoadBalancer, CircuitBreaker, retry logic, idempotency, and comprehensive
#   observability. Routes messages across platforms using AI-optimized strategies,
#   content-based routing, and advanced load balancing algorithms.
# version: 1.4.0
# last_edit: 2025-09-16
#
# CHANGELOG:
# - 1.4.0: Complete merger of advanced load balancing, routing strategies, caching,
#          with policy engine, circuit breaker, and idempotency features
# - 1.3.0: Added AI-optimized routing and content-based selection
# - 1.2.0: Added comprehensive load balancing strategies and health monitoring
# - 1.1.0: Added circuit breaker and retry logic with exponential backoff
# - 1.0.0: Initial routing engine with basic adapter selection

from __future__ import annotations
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import logging
import json
import hashlib
import time
import random
import uuid
from contextlib import asynccontextmanager

# Import UBP components (these would be actual imports in production)
try:
    from .policy_engine import PolicyEngine, PolicyDecision
    from .circuit_breaker import CircuitBreaker
    from ..adapters.base import AdapterRegistry, AdapterContext, PlatformAdapter, AdapterStatus
except ImportError:
    # Fallback for standalone testing
    PolicyEngine = None
    PolicyDecision = None
    CircuitBreaker = None
    AdapterRegistry = None
    AdapterContext = None
    PlatformAdapter = None
    AdapterStatus = None

# =========================
# Core Enums & Data Models
# =========================

class RoutingStrategy(Enum):
    """Advanced routing strategies for message distribution"""
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LEAST_CONNECTIONS = "least_connections"
    RESPONSE_TIME = "response_time"
    GEOGRAPHIC = "geographic"
    CONTENT_BASED = "content_based"
    AI_OPTIMIZED = "ai_optimized"
    CAPABILITY_BASED = "capability_based"
    LOAD_BALANCED = "load_balanced"
    FAILOVER = "failover"

class RouteHealth(Enum):
    """Route health status for monitoring and selection"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"

class MessagePriority(Enum):
    """Message priority levels for routing decisions"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5

@dataclass
class RouteDecision:
    """Result of route selection process"""
    adapter_id: str
    platform_key: str
    route_id: str
    score: float
    strategy_used: RoutingStrategy
    health_status: RouteHealth
    estimated_latency: float = 0.0
    confidence: float = 1.0
    fallback_available: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RoutingMetrics:
    """Comprehensive routing metrics"""
    total_routed: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    fallback_routes: int = 0
    policy_denials: int = 0
    circuit_breaker_trips: int = 0
    idempotent_hits: int = 0
    cache_hits: int = 0
    avg_response_time: float = 0.0
    routes_by_strategy: Dict[str, int] = field(default_factory=dict)
    routes_by_platform: Dict[str, int] = field(default_factory=dict)

@dataclass
class RouteConfiguration:
    """Configuration for a specific route"""
    route_id: str
    platforms: List[str]
    conditions: Dict[str, Any]
    priority: int = 1
    weight: int = 1
    max_connections: int = 100
    fallback: Optional[str] = None
    strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
    health_check_interval: int = 30
    timeout_seconds: float = 30.0
    retry_config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    usage_count: int = 0

# ===================
# Advanced Load Balancer
# ===================

class LoadBalancer:
    """
    Advanced load balancer for intelligent message routing.

    Design Philosophy:
    - Interoperability: Works with any platform adapter through standard interface
    - Scalability: Efficient route selection with minimal overhead
    - Security: Health monitoring prevents routing to compromised endpoints
    - Observability: Comprehensive metrics and performance tracking

    Technical Implementation:
    - Multiple load balancing algorithms (round-robin, weighted, response-time based)
    - Real-time health monitoring and automatic failover
    - Connection tracking and capacity management
    - Performance metrics collection and analysis
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger("ubp.routing.load_balancer")

        # Route management
        self.routes: Dict[str, RouteConfiguration] = {}
        self.health_status: Dict[str, RouteHealth] = {}
        self.connection_counts: Dict[str, int] = defaultdict(int)
        self.response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.weights: Dict[str, int] = {}
        self.last_used: Dict[str, datetime] = {}

        # Strategy state
        self._round_robin_indices: Dict[str, int] = defaultdict(int)
        self._performance_cache: Dict[str, Dict[str, float]] = {}
        self._cache_ttl = timedelta(seconds=30)

        # Metrics
        self.metrics = RoutingMetrics()

    def add_route(
        self,
        route_config: RouteConfiguration
    ) -> None:
        """Add a route configuration to the load balancer"""
        route_id = route_config.route_id

        self.routes[route_id] = route_config
        self.weights[route_id] = route_config.weight
        self.health_status[route_id] = RouteHealth.HEALTHY
        self.last_used[route_id] = datetime.utcnow()

        self.logger.info(
            f"Added route: {route_id}",
            extra={
                "route_id": route_id,
                "platforms": route_config.platforms,
                "strategy": route_config.strategy.value
            }
        )

    def remove_route(self, route_id: str) -> bool:
        """Remove a route from the load balancer"""
        if route_id not in self.routes:
            return False

        # Clean up all associated data
        self.routes.pop(route_id, None)
        self.weights.pop(route_id, None)
        self.health_status.pop(route_id, None)
        self.connection_counts.pop(route_id, None)
        self.response_times.pop(route_id, None)
        self.last_used.pop(route_id, None)
        self._performance_cache.pop(route_id, None)

        self.logger.info(f"Removed route: {route_id}")
        return True

    async def select_route(
        self,
        strategy: RoutingStrategy,
        available_routes: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Select the best route based on strategy and context.

        Technical Implementation:
        - Filters routes by health status and capacity
        - Applies strategy-specific selection algorithm
        - Considers context for intelligent routing decisions
        - Updates usage statistics and performance metrics
        """
        if not available_routes:
            return None

        context = context or {}

        # Filter healthy routes with available capacity
        healthy_routes = []
        for route_id in available_routes:
            if route_id not in self.routes:
                continue

            health = self.health_status.get(route_id, RouteHealth.OFFLINE)
            if health in [RouteHealth.HEALTHY, RouteHealth.DEGRADED]:
                route_config = self.routes[route_id]
                current_connections = self.connection_counts.get(route_id, 0)

                if current_connections < route_config.max_connections:
                    healthy_routes.append(route_id)

        if not healthy_routes:
            self.logger.warning("No healthy routes available for selection")
            return None

        # Apply strategy-specific selection
        try:
            if strategy == RoutingStrategy.ROUND_ROBIN:
                selected = self._round_robin_select(healthy_routes, context)
            elif strategy == RoutingStrategy.WEIGHTED:
                selected = self._weighted_select(healthy_routes, context)
            elif strategy == RoutingStrategy.LEAST_CONNECTIONS:
                selected = self._least_connections_select(healthy_routes, context)
            elif strategy == RoutingStrategy.RESPONSE_TIME:
                selected = self._response_time_select(healthy_routes, context)
            elif strategy == RoutingStrategy.CONTENT_BASED:
                selected = await self._content_based_select(healthy_routes, context)
            elif strategy == RoutingStrategy.AI_OPTIMIZED:
                selected = await self._ai_optimized_select(healthy_routes, context)
            elif strategy == RoutingStrategy.CAPABILITY_BASED:
                selected = await self._capability_based_select(healthy_routes, context)
            elif strategy == RoutingStrategy.GEOGRAPHIC:
                selected = self._geographic_select(healthy_routes, context)
            else:
                selected = random.choice(healthy_routes)

            if selected:
                self.last_used[selected] = datetime.utcnow()
                self.metrics.routes_by_strategy[strategy.value] = \
                    self.metrics.routes_by_strategy.get(strategy.value, 0) + 1

            return selected

        except Exception as e:
            self.logger.error(f"Error in route selection: {str(e)}", exc_info=True)
            return random.choice(healthy_routes) if healthy_routes else None

    def _round_robin_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Round-robin selection with per-platform state"""
        platform = context.get("platform", "default")
        index_key = f"rr_{platform}"

        current_index = self._round_robin_indices[index_key]
        selected = routes[current_index % len(routes)]
        self._round_robin_indices[index_key] = (current_index + 1) % len(routes)

        return selected

    def _weighted_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Weighted random selection based on route weights"""
        total_weight = sum(self.weights.get(route_id, 1) for route_id in routes)
        if total_weight == 0:
            return random.choice(routes)

        rand_val = random.uniform(0, total_weight)
        current_weight = 0

        for route_id in routes:
            current_weight += self.weights.get(route_id, 1)
            if rand_val <= current_weight:
                return route_id

        return routes[-1]

    def _least_connections_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Select route with least active connections"""
        return min(routes, key=lambda r: self.connection_counts.get(r, 0))

    def _response_time_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Select route with best average response time"""
        def avg_response_time(route_id: str) -> float:
            times = self.response_times.get(route_id, deque())
            if not times:
                return 0.1  # Default low latency for new routes
            return sum(times) / len(times)

        return min(routes, key=avg_response_time)

    async def _content_based_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Select route based on content analysis and platform capabilities"""
        message = context.get("message", {})
        content_type = message.get("type", "text")
        content_length = len(message.get("content", ""))
        has_media = bool(message.get("media") or message.get("attachments"))

        # Score routes based on content compatibility
        route_scores = {}
        for route_id in routes:
            score = 0.0
            route_config = self.routes.get(route_id)
            if not route_config:
                continue

            # Content type compatibility
            supported_types = route_config.metadata.get("supported_content_types", ["text"])
            if content_type in supported_types:
                score += 10.0

            # Content length optimization
            max_length = route_config.metadata.get("max_content_length", 4096)
            if content_length <= max_length:
                score += 5.0
            else:
                score -= 5.0  # Penalize routes that can't handle content length

            # Media support
            if has_media:
                supports_media = route_config.metadata.get("supports_media", False)
                if supports_media:
                    score += 8.0
                else:
                    score -= 10.0  # Heavy penalty for media on text-only routes

            # Platform-specific optimizations
            platform = context.get("platform")
            if platform in route_config.platforms:
                score += 15.0

            route_scores[route_id] = score

        # Select route with highest score
        if route_scores:
            return max(route_scores.keys(), key=lambda r: route_scores[r])

        return random.choice(routes)

    async def _ai_optimized_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """AI-optimized route selection using multiple factors"""
        # This would integrate with ML models in production
        # For now, implement a sophisticated heuristic approach

        route_scores = {}
        current_time = datetime.utcnow()

        for route_id in routes:
            score = 0.0

            # Base weight
            score += self.weights.get(route_id, 1) * 2

            # Response time factor (lower is better)
            avg_rt = self._get_avg_response_time(route_id)
            if avg_rt > 0:
                score += max(0, 10 - avg_rt * 10)  # Penalize slow routes
            else:
                score += 5  # Neutral score for new routes

            # Connection load factor
            connections = self.connection_counts.get(route_id, 0)
            max_connections = self.routes[route_id].max_connections
            load_ratio = connections / max_connections if max_connections > 0 else 0
            score += max(0, 10 - load_ratio * 15)  # Penalize high load

            # Health factor
            health = self.health_status.get(route_id, RouteHealth.OFFLINE)
            if health == RouteHealth.HEALTHY:
                score += 10
            elif health == RouteHealth.DEGRADED:
                score += 3
            else:
                score -= 5

            # Recency factor (prefer recently successful routes)
            last_used = self.last_used.get(route_id, current_time - timedelta(hours=1))
            recency_minutes = (current_time - last_used).total_seconds() / 60
            if recency_minutes < 30:
                score += 5
            elif recency_minutes > 120:
                score -= 2

            # Platform affinity
            platform = context.get("platform")
            if platform in self.routes[route_id].platforms:
                score += 8

            route_scores[route_id] = score

        # Add some randomness to prevent always selecting the same route
        if route_scores:
            # Weighted random selection based on scores
            total_score = sum(max(0, score) for score in route_scores.values())
            if total_score > 0:
                rand_val = random.uniform(0, total_score)
                current_score = 0
                for route_id, score in route_scores.items():
                    current_score += max(0, score)
                    if rand_val <= current_score:
                        return route_id

        return random.choice(routes)

    async def _capability_based_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Select route based on required capabilities"""
        required_capabilities = context.get("required_capabilities", set())
        if not required_capabilities:
            return self._response_time_select(routes, context)

        # Filter routes by capability support
        capable_routes = []
        for route_id in routes:
            route_config = self.routes.get(route_id)
            if not route_config:
                continue

            supported_capabilities = set(route_config.metadata.get("capabilities", []))
            if required_capabilities.issubset(supported_capabilities):
                capable_routes.append(route_id)

        if capable_routes:
            return self._response_time_select(capable_routes, context)
        else:
            # Fallback to best available route
            self.logger.warning(f"No routes support required capabilities: {required_capabilities}")
            return self._response_time_select(routes, context)

    def _geographic_select(self, routes: List[str], context: Dict[str, Any]) -> str:
        """Select route based on geographic proximity"""
        user_region = context.get("user_region", "unknown")

        # Score routes by geographic proximity
        route_scores = {}
        for route_id in routes:
            route_config = self.routes.get(route_id)
            if not route_config:
                continue

            route_regions = route_config.metadata.get("regions", ["global"])
            if user_region in route_regions or "global" in route_regions:
                route_scores[route_id] = 10.0
            else:
                route_scores[route_id] = 1.0

        if route_scores:
            return max(route_scores.keys(), key=lambda r: route_scores[r])

        return random.choice(routes)

    def update_health(self, route_id: str, health: RouteHealth) -> None:
        """Update route health status"""
        if route_id in self.health_status:
            old_health = self.health_status[route_id]
            self.health_status[route_id] = health

            if old_health != health:
                self.logger.info(
                    f"Route health changed: {route_id}",
                    extra={
                        "route_id": route_id,
                        "old_health": old_health.value,
                        "new_health": health.value
                    }
                )

    def record_response_time(self, route_id: str, response_time: float) -> None:
        """Record response time for performance tracking"""
        if route_id in self.routes:
            times = self.response_times[route_id]
            times.append(response_time)

            # Update performance cache
            self._performance_cache[route_id] = {
                "avg_response_time": sum(times) / len(times),
                "last_updated": datetime.utcnow()
            }

    def increment_connections(self, route_id: str) -> None:
        """Increment active connection count"""
        self.connection_counts[route_id] += 1

    def decrement_connections(self, route_id: str) -> None:
        """Decrement active connection count"""
        self.connection_counts[route_id] = max(0, self.connection_counts[route_id] - 1)

    def _get_avg_response_time(self, route_id: str) -> float:
        """Get average response time for a route"""
        # Check cache first
        cached = self._performance_cache.get(route_id)
        if cached and datetime.utcnow() - cached["last_updated"] < self._cache_ttl:
            return cached["avg_response_time"]

        # Calculate from raw data
        times = self.response_times.get(route_id, deque())
        if not times:
            return 0.0

        avg_time = sum(times) / len(times)

        # Update cache
        self._performance_cache[route_id] = {
            "avg_response_time": avg_time,
            "last_updated": datetime.utcnow()
        }

        return avg_time

    def get_route_stats(self, route_id: str) -> Dict[str, Any]:
        """Get comprehensive statistics for a route"""
        if route_id not in self.routes:
            return {}

        route_config = self.routes[route_id]
        return {
            "route_id": route_id,
            "platforms": route_config.platforms,
            "health": self.health_status.get(route_id, RouteHealth.OFFLINE).value,
            "active_connections": self.connection_counts.get(route_id, 0),
            "max_connections": route_config.max_connections,
            "avg_response_time": self._get_avg_response_time(route_id),
            "weight": self.weights.get(route_id, 1),
            "usage_count": route_config.usage_count,
            "last_used": self.last_used.get(route_id, datetime.min).isoformat(),
            "created_at": route_config.created_at.isoformat()
        }

# =====================
# Circuit Breaker (Fallback Implementation)
# =====================

class SimpleCircuitBreaker:
    """Simple circuit breaker implementation if not imported"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def allow(self) -> bool:
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if self.last_failure_time and \
               time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        else:  # HALF_OPEN
            return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

# Use imported CircuitBreaker or fallback
if CircuitBreaker is None:
    CircuitBreaker = SimpleCircuitBreaker

# ===================
# Main Message Router
# ===================

class MessageRouter:
    """
    Intelligent message routing system for UBP.

    Design Philosophy:
    - Interoperability: Routes messages across any platform adapter uniformly
    - Scalability: Efficient routing with caching, load balancing, and connection pooling
    - Security: Policy enforcement, circuit breakers, and secure credential handling
    - Observability: Comprehensive metrics, tracing, and performance monitoring

    Technical Implementation:
    - Multi-strategy load balancing with AI optimization
    - Policy-based routing with security enforcement
    - Circuit breaker pattern for fault tolerance
    - Idempotency support for reliable message delivery
    - Comprehensive caching and performance optimization
    """

    def __init__(
        self,
        adapter_registry: Optional[AdapterRegistry] = None,
        policy_engine: Optional[PolicyEngine] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.config = config or {}
        self.logger = logging.getLogger("ubp.routing.message_router")

        # Core components
        self.adapter_registry = adapter_registry
        self.policy_engine = policy_engine
        self.load_balancer = LoadBalancer(config.get("load_balancer", {}))

        # Routing state
        self.routes: Dict[str, RouteConfiguration] = {}
        self.fallback_routes: Dict[str, str] = {}
        self.routing_rules: List[Dict[str, Any]] = []

        # Circuit breakers per adapter
        self.circuit_breakers: Dict[str, CircuitBreaker] = defaultdict(
            lambda: CircuitBreaker(
                failure_threshold=self.config.get("circuit_breaker_threshold", 5),
                recovery_timeout=self.config.get("circuit_breaker_timeout", 60)
            )
        )

        # Caching
        self.route_cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = timedelta(minutes=self.config.get("cache_ttl_minutes", 5))

        # Idempotency (would use Redis in production)
        self._idempotency_cache: Dict[str, Dict[str, Any]] = {}
        self._idempotency_ttl = timedelta(minutes=self.config.get("idempotency_ttl_minutes", 10))

        # Metrics and monitoring
        self.metrics = RoutingMetrics()
        self.response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_background_tasks()

        self.logger.info("MessageRouter initialized")

    def _start_background_tasks(self) -> None:
        """Start background maintenance tasks"""
        self._cleanup_task = asyncio.create_task(self._cleanup_caches())

    async def _cleanup_caches(self) -> None:
        """Background task to clean up expired cache entries"""
        while True:
            try:
                current_time = datetime.utcnow()

                # Clean route cache
                expired_routes = [
                    key for key, data in self.route_cache.items()
                    if current_time - data["timestamp"] > self.cache_ttl
                ]
                for key in expired_routes:
                    self.route_cache.pop(key, None)

                # Clean idempotency cache
                expired_idem = [
                    key for key, data in self._idempotency_cache.items()
                    if current_time - data["timestamp"] > self._idempotency_ttl
                ]
                for key in expired_idem:
                    self._idempotency_cache.pop(key, None)

                if expired_routes or expired_idem:
                    self.logger.debug(
                        f"Cleaned up {len(expired_routes)} route cache entries "
                        f"and {len(expired_idem)} idempotency entries"
                    )

                await asyncio.sleep(300)  # Clean every 5 minutes

            except Exception as e:
                self.logger.error(f"Error in cache cleanup: {str(e)}", exc_info=True)
                await asyncio.sleep(60)  # Retry in 1 minute on error

    # ==================
    # Route Management
    # ==================

    def add_route(
        self,
        route_id: str,
        platforms: List[str],
        conditions: Dict[str, Any],
        priority: int = 1,
        weight: int = 1,
        strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
        fallback: Optional[str] = None,
        **kwargs
    ) -> None:
        """Add a routing configuration"""
        route_config = RouteConfiguration(
            route_id=route_id,
            platforms=platforms,
            conditions=conditions,
            priority=priority,
            weight=weight,
            strategy=strategy,
            fallback=fallback,
            **kwargs
        )

        self.routes[route_id] = route_config
        self.load_balancer.add_route(route_config)

        if fallback:
            self.fallback_routes[route_id] = fallback

        self.logger.info(
            f"Added route: {route_id}",
            extra={
                "route_id": route_id,
                "platforms": platforms,
                "strategy": strategy.value,
                "priority": priority
            }
        )

    def remove_route(self, route_id: str) -> bool:
        """Remove a routing configuration"""
        if route_id not in self.routes:
            return False

        self.routes.pop(route_id, None)
        self.fallback_routes.pop(route_id, None)
        self.load_balancer.remove_route(route_id)

        # Clear related cache entries
        cache_keys_to_remove = [
            key for key in self.route_cache.keys()
            if route_id in key
        ]
        for key in cache_keys_to_remove:
            self.route_cache.pop(key, None)

        self.logger.info(f"Removed route: {route_id}")
        return True

    def add_fallback_route(self, primary_route: str, fallback_route: str) -> None:
        """Add fallback route mapping"""
        self.fallback_routes[primary_route] = fallback_route
        self.logger.info(f"Added fallback: {primary_route} -> {fallback_route}")

    # ==================
    # Main Routing Logic
    # ==================

    async def route_message(
        self,
        message: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Route message to appropriate platform with comprehensive error handling.

        Technical Implementation:
        - Idempotency check to prevent duplicate processing
        - Route selection using configured strategy
        - Policy evaluation for security and compliance
        - Circuit breaker protection against failing adapters
        - Retry logic with exponential backoff
        - Comprehensive metrics and observability
        """
        start_time = time.time()
        correlation_id = context.get("correlation_id") or self._generate_correlation_id(message, context)

        try:
            # Idempotency check
            idempotency_key = self._compute_idempotency_key(message, context)
            cached_result = self._get_cached_idempotent(idempotency_key)
            if cached_result:
                self.metrics.idempotent_hits += 1
                return {**cached_result, "idempotent": True, "correlation_id": correlation_id}

            # Generate cache key and check route cache
            cache_key = self._generate_cache_key(message, context)
            cached_route = self.route_cache.get(cache_key)

            if cached_route and self._is_cache_valid(cached_route):
                self.metrics.cache_hits += 1
                route_decision = cached_route["route_decision"]
            else:
                # Determine best route
                route_decision = await self._determine_best_route(message, context)
                if not route_decision:
                    self.metrics.failed_routes += 1
                    return {
                        "status": "no_route",
                        "reason": "No suitable route found",
                        "correlation_id": correlation_id
                    }

                # Cache the route decision
                self.route_cache[cache_key] = {
                    "route_decision": route_decision,
                    "timestamp": datetime.utcnow()
                }

            # Execute the route
            result = await self._execute_route(route_decision, message, context, correlation_id)

            # Store result for idempotency
            if result.get("status") == "success":
                self._store_idempotent(idempotency_key, result)

            # Update metrics
            elapsed_time = time.time() - start_time
            self.metrics.avg_response_time = (
                (self.metrics.avg_response_time * self.metrics.total_routed + elapsed_time) /
                (self.metrics.total_routed + 1)
            )
            self.metrics.total_routed += 1

            if result.get("status") == "success":
                self.metrics.successful_routes += 1
            else:
                self.metrics.failed_routes += 1

            return result

        except Exception as e:
            self.logger.error(
                f"Routing error: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            self.metrics.failed_routes += 1

            # Try fallback routing
            return await self._execute_fallback(message, context, correlation_id, str(e))

    async def _determine_best_route(
        self,
        message: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[RouteDecision]:
        """
        Determine the best route for a message using intelligent selection.

        Technical Implementation:
        - Matches message against routing conditions
        - Scores routes based on multiple factors
        - Selects optimal route using configured strategy
        - Considers adapter health and capacity
        """
        # Find matching routes
        matching_routes = []
        for route_id, route_config in self.routes.items():
            if await self._matches_conditions(message, context, route_config.conditions):
                score = await self._calculate_route_score(route_id, message, context)
                matching_routes.append({
                    "route_id": route_id,
                    "config": route_config,
                    "score": score
                })

        if not matching_routes:
            # Try default route
            default_route = await self._get_default_route(message, context)
            if default_route:
                return default_route
            return None

        # Sort by score (highest first)
        matching_routes.sort(key=lambda x: x["score"], reverse=True)

        # Get available adapters for top routes
        for route_info in matching_routes:
            route_config = route_info["config"]

            # Get healthy adapters for this route's platforms
            available_adapters = []
            if self.adapter_registry:
                for platform in route_config.platforms:
                    platform_adapters = self.adapter_registry.get_healthy_adapters(platform)
                    available_adapters.extend([
                        adapter.adapter_id for adapter in platform_adapters
                        if adapter.status == AdapterStatus.CONNECTED
                    ])

            if not available_adapters:
                continue

            # Use load balancer to select specific adapter
            selected_adapter = await self.load_balancer.select_route(
                route_config.strategy,
                available_adapters,
                {**context, "message": message, "platform": route_config.platforms[0]}
            )

            if selected_adapter:
                return RouteDecision(
                    adapter_id=selected_adapter,
                    platform_key=route_config.platforms[0],
                    route_id=route_info["route_id"],
                    score=route_info["score"],
                    strategy_used=route_config.strategy,
                    health_status=self.load_balancer.health_status.get(
                        selected_adapter, RouteHealth.HEALTHY
                    ),
                    estimated_latency=self.load_balancer._get_avg_response_time(selected_adapter),
                    fallback_available=bool(route_config.fallback)
                )

        return None

    async def _matches_conditions(
        self,
        message: Dict[str, Any],
        context: Dict[str, Any],
        conditions: Dict[str, Any]
    ) -> bool:
        """Check if message matches route conditions"""
        try:
            for condition_type, condition_value in conditions.items():
                if condition_type == "platform":
                    platforms = condition_value if isinstance(condition_value, list) else [condition_value]
                    if context.get("source_platform") not in platforms:
                        return False

                elif condition_type == "message_type":
                    types = condition_value if isinstance(condition_value, list) else [condition_value]
                    if message.get("type") not in types:
                        return False

                elif condition_type == "user_type":
                    user_types = condition_value if isinstance(condition_value, list) else [condition_value]
                    if context.get("user_type") not in user_types:
                        return False

                elif condition_type == "content_length":
                    content_length = len(message.get("content", ""))
                    if isinstance(condition_value, dict):
                        min_len = condition_value.get("min", 0)
                        max_len = condition_value.get("max", float('inf'))
                    else:
                        min_len, max_len = condition_value
                    if not (min_len <= content_length <= max_len):
                        return False

                elif condition_type == "time_range":
                    current_hour = datetime.utcnow().hour
                    if isinstance(condition_value, dict):
                        start_hour = condition_value.get("start", 0)
                        end_hour = condition_value.get("end", 23)
                    else:
                        start_hour, end_hour = condition_value
                    if not (start_hour <= current_hour <= end_hour):
                        return False

                elif condition_type == "priority":
                    msg_priority = message.get("priority", MessagePriority.NORMAL.value)
                    required_priority = condition_value
                    if isinstance(msg_priority, str):
                        msg_priority = MessagePriority[msg_priority.upper()].value
                    if isinstance(required_priority, str):
                        required_priority = MessagePriority[required_priority.upper()].value
                    if msg_priority < required_priority:
                        return False

                elif condition_type == "has_media":
                    has_media = bool(message.get("media") or message.get("attachments"))
                    if has_media != condition_value:
                        return False

                elif condition_type == "user_region":
                    regions = condition_value if isinstance(condition_value, list) else [condition_value]
                    if context.get("user_region") not in regions:
                        return False

            return True

        except Exception as e:
            self.logger.error(f"Error matching conditions: {str(e)}", exc_info=True)
            return False

    async def _calculate_route_score(
        self,
        route_id: str,
        message: Dict[str, Any],
        context: Dict[str, Any]
    ) -> float:
        """Calculate comprehensive route score"""
        try:
            score = 0.0
            route_config = self.routes[route_id]

            # Base priority score
            score += route_config.priority * 10

            # Usage balancing (prefer less used routes)
            usage_penalty = min(route_config.usage_count * 0.1, 5.0)
            score -= usage_penalty

            # Platform compatibility
            source_platform = context.get("source_platform")
            target_platform = context.get("target_platform")

            if source_platform in route_config.platforms:
                score += 20
            if target_platform and target_platform in route_config.platforms:
                score += 25

            # Content compatibility
            content_type = message.get("type", "text")
            supported_types = route_config.metadata.get("supported_content_types", ["text"])
            if content_type in supported_types:
                score += 15

            # Performance history
            if self.adapter_registry:
                platform_adapters = []
                for platform in route_config.platforms:
                    platform_adapters.extend(
                        self.adapter_registry.get_healthy_adapters(platform)
                    )

                if platform_adapters:
                    avg_response_times = [
                        self.load_balancer._get_avg_response_time(adapter.adapter_id)
                        for adapter in platform_adapters
                    ]
                    if avg_response_times:
                        avg_rt = sum(avg_response_times) / len(avg_response_times)
                        score += max(0, 10 - avg_rt * 5)  # Prefer faster routes

            # Health factor
            health_scores = []
            for platform in route_config.platforms:
                if self.adapter_registry:
                    adapters = self.adapter_registry.get_healthy_adapters(platform)
                    for adapter in adapters:
                        health = self.load_balancer.health_status.get(
                            adapter.adapter_id, RouteHealth.OFFLINE
                        )
                        if health == RouteHealth.HEALTHY:
                            health_scores.append(10)
                        elif health == RouteHealth.DEGRADED:
                            health_scores.append(5)
                        else:
                            health_scores.append(-5)

            if health_scores:
                score += sum(health_scores) / len(health_scores)

            # Message priority alignment
            msg_priority = message.get("priority", MessagePriority.NORMAL.value)
            if isinstance(msg_priority, str):
                msg_priority = MessagePriority[msg_priority.upper()].value

            route_priority_bonus = route_config.metadata.get("priority_bonus", {})
            if msg_priority in route_priority_bonus:
                score += route_priority_bonus[msg_priority]

            return max(0.0, score)

        except Exception as e:
            self.logger.error(f"Error calculating route score: {str(e)}", exc_info=True)
            return 0.0

    async def _execute_route(
        self,
        route_decision: RouteDecision,
        message: Dict[str, Any],
        context: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Execute the selected route with comprehensive error handling.

        Technical Implementation:
        - Policy evaluation for security compliance
        - Circuit breaker protection
        - Retry logic with exponential backoff
        - Performance monitoring and metrics collection
        """
        route_id = route_decision.route_id
        adapter_id = route_decision.adapter_id
        platform = route_decision.platform_key

        start_time = time.time()

        try:
            # Get adapter
            if not self.adapter_registry:
                raise RuntimeError("No adapter registry configured")

            adapter = self.adapter_registry.get(adapter_id)
            if not adapter:
                raise RuntimeError(f"Adapter {adapter_id} not found")

            # Policy evaluation
            if self.policy_engine:
                adapter_capabilities = {
                    "supports_text": adapter.capabilities.supports(
                        getattr(adapter.capabilities, "SEND_MESSAGE", None)
                    ) if hasattr(adapter.capabilities, "supports") else True,
                    "supports_media": adapter.capabilities.supports(
                        getattr(adapter.capabilities, "SEND_MEDIA", None)
                    ) if hasattr(adapter.capabilities, "supports") else False,
                    "supports_buttons": adapter.capabilities.supports(
                        getattr(adapter.capabilities, "SEND_BUTTONS", None)
                    ) if hasattr(adapter.capabilities, "supports") else False,
                    "supports_threads": adapter.capabilities.supports(
                        getattr(adapter.capabilities, "CREATE_THREAD", None)
                    ) if hasattr(adapter.capabilities, "supports") else False,
                }

                policy_decision = self.policy_engine.evaluate(message, context, adapter_capabilities)
                if not policy_decision.allowed:
                    self.metrics.policy_denials += 1
                    return {
                        "status": "denied",
                        "reason": "Policy violation",
                        "details": policy_decision.reasons,
                        "correlation_id": correlation_id
                    }

            # Circuit breaker check
            circuit_breaker = self.circuit_breakers[adapter_id]
            if not circuit_breaker.allow():
                self.metrics.circuit_breaker_trips += 1
                return {
                    "status": "unavailable",
                    "reason": "Circuit breaker open",
                    "adapter_id": adapter_id,
                    "correlation_id": correlation_id
                }

            # Prepare adapter context
            tenant_id = context.get("tenant_id", "default")
            user_id = context.get("user_id")
            channel_id = context.get("channel_id")

            adapter_context = AdapterContext(
                tenant_id=tenant_id,
                correlation_id=correlation_id,
                user_id=user_id,
                channel_id=channel_id,
                tracing_ctx=context.get("tracing_ctx"),
                extras={
                    "platform_key": platform,
                    "route_id": route_id,
                    "strategy": route_decision.strategy_used.value
                }
            )

            # Execute with retry logic
            max_retries = int(context.get("retry_max", 2))
            base_backoff = float(context.get("retry_backoff_sec", 0.3))

            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    # Track connection
                    self.load_balancer.increment_connections(adapter_id)

                    # Send message
                    result = await adapter.send_message(adapter_context, message)

                    if result.success:
                        # Success path
                        circuit_breaker.record_success()
                        elapsed_time = time.time() - start_time

                        # Record metrics
                        self.load_balancer.record_response_time(adapter_id, elapsed_time)
                        self.response_times[adapter_id].append(elapsed_time)

                        # Update route usage
                        self.routes[route_id].usage_count += 1

                        # Update platform metrics
                        self.metrics.routes_by_platform[platform] = \
                            self.metrics.routes_by_platform.get(platform, 0) + 1

                        return {
                            "status": "success",
                            "platform": platform,
                            "adapter_id": adapter_id,
                            "route_id": route_id,
                            "result": {
                                "platform_message_id": getattr(result, "platform_message_id", None),
                                "details": getattr(result, "details", {}),
                            },
                            "attempts": attempt + 1,
                            "response_time_sec": elapsed_time,
                            "strategy_used": route_decision.strategy_used.value,
                            "correlation_id": correlation_id
                        }
                    else:
                        # Adapter returned failure
                        error_msg = getattr(result, "error_message", "Unknown error")
                        last_error = RuntimeError(f"Adapter send failed: {error_msg}")

                        if attempt < max_retries:
                            # Retry with backoff
                            backoff_time = base_backoff * (2 ** attempt) * (1 + random.random() * 0.2)
                            await asyncio.sleep(backoff_time)
                            continue
                        else:
                            raise last_error

                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        # Retry with backoff
                        backoff_time = base_backoff * (2 ** attempt) * (1 + random.random() * 0.2)
                        self.logger.warning(
                            f"Route execution attempt {attempt + 1} failed, retrying in {backoff_time:.2f}s: {str(e)}",
                            extra={"correlation_id": correlation_id}
                        )
                        await asyncio.sleep(backoff_time)
                    else:
                        raise

                finally:
                    # Always decrement connection count
                    self.load_balancer.decrement_connections(adapter_id)

            # All retries exhausted
            circuit_breaker.record_failure()
            raise last_error or RuntimeError("All retry attempts failed")

        except Exception as e:
            self.logger.error(
                f"Route execution failed: {str(e)}",
                extra={
                    "correlation_id": correlation_id,
                    "route_id": route_id,
                    "adapter_id": adapter_id
                },
                exc_info=True
            )

            return {
                "status": "error",
                "reason": "Route execution failed",
                "error": str(e),
                "route_id": route_id,
                "adapter_id": adapter_id,
                "correlation_id": correlation_id
            }

    async def _execute_fallback(
        self,
        message: Dict[str, Any],
        context: Dict[str, Any],
        correlation_id: str,
        original_error: str
    ) -> Dict[str, Any]:
        """Execute fallback routing when primary route fails"""
        try:
            self.logger.info(
                f"Executing fallback routing due to: {original_error}",
                extra={"correlation_id": correlation_id}
            )

            # Try to find a fallback route
            fallback_route = await self._get_fallback_route(message, context)
            if fallback_route:
                result = await self._execute_route(fallback_route, message, context, correlation_id)
                result["fallback"] = True
                result["original_error"] = original_error
                self.metrics.fallback_routes += 1
                return result

            # No fallback available
            return {
                "status": "failed",
                "reason": "No fallback route available",
                "original_error": original_error,
                "correlation_id": correlation_id
            }

        except Exception as e:
            self.logger.error(
                f"Fallback routing failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )

            return {
                "status": "failed",
                "reason": "Fallback routing failed",
                "original_error": original_error,
                "fallback_error": str(e),
                "correlation_id": correlation_id
            }

    async def _get_fallback_route(
        self,
        message: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[RouteDecision]:
        """Get fallback route for failed primary route"""
        # This could be enhanced to select fallback based on various criteria
        # For now, return a simple default route if available
        return await self._get_default_route(message, context)

    async def _get_default_route(
        self,
        message: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Optional[RouteDecision]:
        """Get default route when no specific route matches"""
        # Look for a route marked as default
        default_routes = [
            route_id for route_id, config in self.routes.items()
            if config.metadata.get("is_default", False)
        ]

        if default_routes:
            route_id = default_routes[0]  # Use first default route
            route_config = self.routes[route_id]

            # Get available adapters
            if self.adapter_registry:
                available_adapters = []
                for platform in route_config.platforms:
                    platform_adapters = self.adapter_registry.get_healthy_adapters(platform)
                    available_adapters.extend([
                        adapter.adapter_id for adapter in platform_adapters
                    ])

                if available_adapters:
                    selected_adapter = await self.load_balancer.select_route(
                        route_config.strategy,
                        available_adapters,
                        {**context, "message": message}
                    )

                    if selected_adapter:
                        return RouteDecision(
                            adapter_id=selected_adapter,
                            platform_key=route_config.platforms[0],
                            route_id=route_id,
                            score=1.0,
                            strategy_used=route_config.strategy,
                            health_status=RouteHealth.HEALTHY,
                            fallback_available=False
                        )

        return None

    # ==================
    # Caching & Idempotency
    # ==================

    def _generate_cache_key(self, message: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Generate cache key for route decisions"""
        key_data = {
            "message_type": message.get("type"),
            "source_platform": context.get("source_platform"),
            "target_platform": context.get("target_platform"),
            "user_type": context.get("user_type"),
            "priority": message.get("priority"),
            "has_media": bool(message.get("media") or message.get("attachments")),
            "content_hash": hashlib.md5(
                str(message.get("content", "")).encode()
            ).hexdigest()[:8]
        }
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def _is_cache_valid(self, cached_data: Dict[str, Any]) -> bool:
        """Check if cached route decision is still valid"""
        return datetime.utcnow() - cached_data["timestamp"] < self.cache_ttl

    def _compute_idempotency_key(self, message: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Compute idempotency key for message deduplication"""
        key_data = {
            "content": message.get("content"),
            "to": message.get("to"),
            "topic": message.get("topic"),
            "payload_hash": hashlib.md5(
                json.dumps(message.get("payload", {}), sort_keys=True).encode()
            ).hexdigest() if "payload" in message else None,
            "platform": context.get("target_platform") or context.get("source_platform"),
            "tenant": context.get("tenant_id", "default"),
            "user": context.get("user_id"),
            "channel": context.get("channel_id")
        }
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def _store_idempotent(self, key: str, value: Dict[str, Any]) -> None:
        """Store result for idempotency checking"""
        self._idempotency_cache[key] = {
            "value": value,
            "timestamp": datetime.utcnow()
        }

    def _get_cached_idempotent(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached idempotent result"""
        data = self._idempotency_cache.get(key)
        if not data:
            return None

        if datetime.utcnow() - data["timestamp"] > self._idempotency_ttl:
            self._idempotency_cache.pop(key, None)
            return None

        return data["value"]

    def _generate_correlation_id(self, message: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Generate correlation ID for request tracing"""
        seed = json.dumps({
            "message_type": message.get("type"),
            "user_id": context.get("user_id"),
            "timestamp": time.time(),
            "random": random.random()
        }, sort_keys=True)
        return hashlib.md5(seed.encode()).hexdigest()[:16]

    # ==================
    # Monitoring & Metrics
    # ==================

    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive routing metrics"""
        return {
            "total_routed": self.metrics.total_routed,
            "successful_routes": self.metrics.successful_routes,
            "failed_routes": self.metrics.failed_routes,
            "fallback_routes": self.metrics.fallback_routes,
            "policy_denials": self.metrics.policy_denials,
            "circuit_breaker_trips": self.metrics.circuit_breaker_trips,
            "idempotent_hits": self.metrics.idempotent_hits,
            "cache_hits": self.metrics.cache_hits,
            "avg_response_time": self.metrics.avg_response_time,
            "routes_by_strategy": dict(self.metrics.routes_by_strategy),
            "routes_by_platform": dict(self.metrics.routes_by_platform),
            "active_routes": len(self.routes),
            "cache_size": len(self.route_cache),
            "idempotency_cache_size": len(self._idempotency_cache)
        }

    def get_route_health(self) -> Dict[str, Any]:
        """Get health status of all routes"""
        health_data = {}

        for route_id, route_config in self.routes.items():
            route_health = {
                "route_id": route_id,
                "platforms": route_config.platforms,
                "strategy": route_config.strategy.value,
                "usage_count": route_config.usage_count,
                "adapters": []
            }

            if self.adapter_registry:
                for platform in route_config.platforms:
                    adapters = self.adapter_registry.list_by_platform(platform)
                    for adapter in adapters:
                        adapter_health = {
                            "adapter_id": adapter.adapter_id,
                            "status": adapter.status.value if hasattr(adapter, 'status') else "unknown",
                            "health": self.load_balancer.health_status.get(
                                adapter.adapter_id, RouteHealth.OFFLINE
                            ).value,
                            "connections": self.load_balancer.connection_counts.get(adapter.adapter_id, 0),
                            "avg_response_time": self.load_balancer._get_avg_response_time(adapter.adapter_id)
                        }
                        route_health["adapters"].append(adapter_health)

            health_data[route_id] = route_health

        return health_data

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        healthy_routes = 0
        total_adapters = 0
        healthy_adapters = 0

        if self.adapter_registry:
            all_adapters = self.adapter_registry.all()
            total_adapters = len(all_adapters)
            healthy_adapters = len([
                adapter for adapter in all_adapters
                if hasattr(adapter, 'status') and adapter.status == AdapterStatus.CONNECTED
            ])

        for route_id in self.routes:
            if self.load_balancer.health_status.get(route_id, RouteHealth.OFFLINE) == RouteHealth.HEALTHY:
                healthy_routes += 1

        return {
            "status": "healthy" if healthy_routes > 0 and healthy_adapters > 0 else "degraded",
            "routes": {
                "total": len(self.routes),
                "healthy": healthy_routes
            },
            "adapters": {
                "total": total_adapters,
                "healthy": healthy_adapters
            },
            "cache": {
                "route_cache_size": len(self.route_cache),
                "idempotency_cache_size": len(self._idempotency_cache)
            },
            "metrics": self.get_metrics()
        }

    # ==================
    # Cleanup
    # ==================

    async def shutdown(self) -> None:
        """Gracefully shutdown the message router"""
        self.logger.info("Shutting down MessageRouter...")

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Clear caches
        self.route_cache.clear()
        self._idempotency_cache.clear()

        self.logger.info("MessageRouter shutdown complete")

# =================
# Factory Functions
# =================

def create_message_router(
    adapter_registry: Optional[AdapterRegistry] = None,
    policy_engine: Optional[PolicyEngine] = None,
    config: Optional[Dict[str, Any]] = None
) -> MessageRouter:
    """Factory function to create a MessageRouter instance"""
    return MessageRouter(adapter_registry, policy_engine, config)

# ===============
# Module Exports
# ===============

__all__ = [
    # Main classes
    "MessageRouter",
    "LoadBalancer",

    # Data models
    "RouteDecision",
    "RouteConfiguration",
    "RoutingMetrics",

    # Enums
    "RoutingStrategy",
    "RouteHealth",
    "MessagePriority",

    # Factory functions
    "create_message_router"
]