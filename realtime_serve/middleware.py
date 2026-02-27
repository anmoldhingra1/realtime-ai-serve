"""Middleware for request handling, rate limiting, logging, and metrics."""

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional

from realtime_serve.types import InferenceRequest


logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter per client.

    Implements token bucket algorithm for fair rate limiting.
    """

    def __init__(self, tokens_per_minute: int = 1000, tokens_per_request: float = 1.0):
        """Initialize RateLimiter.

        Args:
            tokens_per_minute: Tokens refilled per minute per client
            tokens_per_request: Tokens consumed per request
        """
        self.tokens_per_minute = tokens_per_minute
        self.tokens_per_request = tokens_per_request
        self.tokens_per_second = tokens_per_minute / 60.0

        self._client_buckets: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, client_id: str) -> bool:
        """Check if a client can make a request.

        Args:
            client_id: Client identifier

        Returns:
            True if request is allowed, False if rate limited
        """
        async with self._lock:
            current_time = time.time()

            if client_id not in self._client_buckets:
                self._client_buckets[client_id] = {
                    "tokens": self.tokens_per_minute,
                    "last_refill": current_time,
                }

            bucket = self._client_buckets[client_id]

            # Refill tokens based on elapsed time
            elapsed = current_time - bucket["last_refill"]
            refill = elapsed * self.tokens_per_second
            bucket["tokens"] = min(
                self.tokens_per_minute,
                bucket["tokens"] + refill
            )
            bucket["last_refill"] = current_time

            # Check if we have enough tokens
            if bucket["tokens"] >= self.tokens_per_request:
                bucket["tokens"] -= self.tokens_per_request
                return True

            return False

    def get_client_stats(self, client_id: str) -> Dict:
        """Get rate limit stats for a client.

        Args:
            client_id: Client identifier

        Returns:
            Dictionary of stats
        """
        if client_id not in self._client_buckets:
            return {"available_tokens": self.tokens_per_minute}

        return {
            "available_tokens": self._client_buckets[client_id]["tokens"],
            "tokens_per_minute": self.tokens_per_minute,
        }


class RequestLogger:
    """Structured logging for inference requests."""

    def __init__(self, log_level: str = "INFO"):
        """Initialize RequestLogger.

        Args:
            log_level: Logging level for request logs
        """
        self.log_level = getattr(logging, log_level, logging.INFO)
        self._request_log = logging.getLogger("realtime_serve.requests")
        self._request_log.setLevel(self.log_level)

    def log_request(
        self,
        request: InferenceRequest,
        client_addr: Optional[str] = None,
    ) -> None:
        """Log an incoming request.

        Args:
            request: The inference request
            client_addr: Client IP address
        """
        log_data = {
            "event": "request_received",
            "request_id": request.request_id,
            "model": request.model,
            "client_id": request.client_id or client_addr,
            "priority": request.priority.name,
            "prompt_length": len(request.prompt),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        self._request_log.info(json.dumps(log_data))

    def log_completion(
        self,
        request_id: str,
        model: str,
        tokens_generated: int,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Log request completion.

        Args:
            request_id: Request identifier
            model: Model used
            tokens_generated: Number of tokens generated
            latency_ms: Total latency in milliseconds
            error: Error message if failed
        """
        log_data = {
            "event": "request_completed",
            "request_id": request_id,
            "model": model,
            "tokens_generated": tokens_generated,
            "latency_ms": latency_ms,
            "error": error,
        }

        level = logging.ERROR if error else logging.INFO
        self._request_log.log(level, json.dumps(log_data))


class MetricsCollector:
    """Collects performance metrics: latency, throughput, error rates."""

    def __init__(self, window_size: int = 1000):
        """Initialize MetricsCollector.

        Args:
            window_size: Number of recent requests to track
        """
        self.window_size = window_size
        self._latencies: Dict[str, list] = defaultdict(list)
        self._request_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._token_counts: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._collection_start = time.time()

    async def record_request(
        self,
        model: str,
        latency_ms: float,
        tokens_generated: int,
        error: Optional[str] = None,
    ) -> None:
        """Record metrics for a request.

        Args:
            model: Model name
            latency_ms: Request latency in milliseconds
            tokens_generated: Number of tokens generated
            error: Error message if request failed
        """
        async with self._lock:
            self._latencies[model].append(latency_ms)
            if len(self._latencies[model]) > self.window_size:
                self._latencies[model].pop(0)

            self._request_counts[model] += 1
            self._token_counts[model] += tokens_generated

            if error:
                self._error_counts[model] += 1

    async def get_metrics(self, model: str) -> Dict:
        """Get metrics for a model.

        Args:
            model: Model name

        Returns:
            Dictionary of metrics
        """
        async with self._lock:
            latencies = self._latencies.get(model, [])

            if not latencies:
                return {
                    "model": model,
                    "request_count": 0,
                    "error_count": 0,
                    "error_rate": 0.0,
                }

            latencies_sorted = sorted(latencies)
            n = len(latencies_sorted)

            return {
                "model": model,
                "request_count": self._request_counts[model],
                "error_count": self._error_counts[model],
                "error_rate": (
                    self._error_counts[model] / self._request_counts[model]
                    if self._request_counts[model] > 0 else 0
                ),
                "total_tokens": self._token_counts[model],
                "latency_ms": {
                    "p50": latencies_sorted[n // 2],
                    "p95": latencies_sorted[int(n * 0.95)],
                    "p99": latencies_sorted[int(n * 0.99)],
                    "min": latencies_sorted[0],
                    "max": latencies_sorted[-1],
                    "mean": sum(latencies) / n,
                },
                "throughput_tokens_per_sec": (
                    self._token_counts[model] / ((time.time() - self._collection_start) / 1000)
                    if time.time() > self._collection_start else 0
                ),
            }

    async def get_all_metrics(self) -> Dict[str, Dict]:
        """Get metrics for all models.

        Returns:
            Dictionary mapping model names to metrics
        """
        async with self._lock:
            models = set(self._latencies.keys()) | set(self._request_counts.keys())

        return {
            model: await self.get_metrics(model)
            for model in models
        }


class MiddlewareChain:
    """Manages a chain of middleware processors."""

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        request_logger: Optional[RequestLogger] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        """Initialize MiddlewareChain.

        Args:
            rate_limiter: RateLimiter instance
            request_logger: RequestLogger instance
            metrics_collector: MetricsCollector instance
        """
        self.rate_limiter = rate_limiter
        self.request_logger = request_logger
        self.metrics_collector = metrics_collector

    async def process_request(
        self,
        request: InferenceRequest,
        client_addr: Optional[str] = None,
    ) -> bool:
        """Process request through middleware chain.

        Args:
            request: The inference request
            client_addr: Client IP address

        Returns:
            True if request should proceed, False if rejected
        """
        # Check rate limit
        if self.rate_limiter:
            if not await self.rate_limiter.check_rate_limit(request.client_id or "unknown"):
                logger.warning(f"Rate limit exceeded for client {request.client_id}")
                return False

        # Log request
        if self.request_logger:
            self.request_logger.log_request(request, client_addr)

        return True

    async def record_response(
        self,
        request_id: str,
        model: str,
        latency_ms: float,
        tokens_generated: int,
        error: Optional[str] = None,
    ) -> None:
        """Record response metrics.

        Args:
            request_id: Request identifier
            model: Model used
            latency_ms: Request latency
            tokens_generated: Number of tokens generated
            error: Error message if failed
        """
        if self.request_logger:
            self.request_logger.log_completion(
                request_id, model, tokens_generated, latency_ms, error
            )

        if self.metrics_collector:
            await self.metrics_collector.record_request(
                model, latency_ms, tokens_generated, error
            )
