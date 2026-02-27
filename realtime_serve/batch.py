"""Batch scheduling for efficient model inference."""

import asyncio
import logging
import time
from typing import Dict, List

from realtime_serve.types import BatchConfig, InferenceRequest, RequestPriority


logger = logging.getLogger(__name__)


class BatchScheduler:
    """Collects requests into batches for efficient GPU processing.

    Dynamically sizes batches based on load and latency constraints.
    Supports priority queues for urgent requests.
    """

    def __init__(self, model: str, config: BatchConfig):
        """Initialize BatchScheduler.

        Args:
            model: Model name this scheduler processes
            config: Batch configuration parameters
        """
        self.model = model
        self.config = config

        # Priority queues: HIGH, NORMAL, LOW
        self._queues: Dict[RequestPriority, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in RequestPriority
        }

        self._batch_counter = 0
        self._total_requests = 0
        self._total_batches = 0
        self._total_wait_ms = 0.0

    async def enqueue(self, request: InferenceRequest) -> None:
        """Enqueue a request for batching.

        Args:
            request: The inference request
        """
        await self._queues[request.priority].put(request)
        self._total_requests += 1
        logger.debug(
            f"Enqueued request {request.request_id} "
            f"(priority={request.priority.name})"
        )

    async def get_batch(self) -> List[InferenceRequest]:
        """Get the next batch of requests.

        Implements prioritization: HIGH priority requests are always included.
        NORMAL and LOW priority requests fill remaining slots.

        Returns:
            List of requests to process (1 to max_batch_size)
        """
        batch: List[InferenceRequest] = []
        batch_start = time.time()

        # Collect HIGH priority requests first
        while len(batch) < self.config.max_batch_size and not self._queues[RequestPriority.HIGH].empty():
            try:
                request = self._queues[RequestPriority.HIGH].get_nowait()
                batch.append(request)
            except asyncio.QueueEmpty:
                break

        # If we have space, add NORMAL priority
        if len(batch) < self.config.max_batch_size:
            while len(batch) < self.config.max_batch_size and not self._queues[RequestPriority.NORMAL].empty():
                try:
                    request = self._queues[RequestPriority.NORMAL].get_nowait()
                    batch.append(request)
                except asyncio.QueueEmpty:
                    break

        # If we still have space, add LOW priority
        if len(batch) < self.config.max_batch_size:
            while len(batch) < self.config.max_batch_size and not self._queues[RequestPriority.LOW].empty():
                try:
                    request = self._queues[RequestPriority.LOW].get_nowait()
                    batch.append(request)
                except asyncio.QueueEmpty:
                    break

        # If batch is too small, wait for more requests
        if len(batch) < self.config.min_batch_size:
            logger.debug(
                f"Batch undersized ({len(batch)} < {self.config.min_batch_size}), waiting..."
            )

            timeout = self.config.max_wait_ms / 1000.0
            deadline = time.time() + timeout

            while len(batch) < self.config.min_batch_size and time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break

                # Wait for any request from any priority queue
                wait_futures = [
                    asyncio.wait_for(self._queues[p].get(), timeout=remaining / 3)
                    for p in RequestPriority
                ]

                done, _ = await asyncio.wait(
                    wait_futures,
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED
                )

                for future in done:
                    try:
                        request = future.result()
                        batch.append(request)
                        break
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        pass

        # Ensure we have at least one request
        if not batch:
            high_queue = self._queues[RequestPriority.HIGH]
            normal_queue = self._queues[RequestPriority.NORMAL]
            low_queue = self._queues[RequestPriority.LOW]

            # Block until we get a request
            request = await asyncio.wait_for(
                self._get_from_any_queue(high_queue, normal_queue, low_queue),
                timeout=self.config.max_wait_ms / 1000.0 + 1.0
            )
            batch.append(request)

        # Record metrics
        wait_time_ms = (time.time() - batch_start) * 1000
        self._total_wait_ms += wait_time_ms
        self._total_batches += 1
        self._batch_counter += 1

        logger.info(
            f"Created batch #{self._batch_counter} with {len(batch)} requests "
            f"(waited {wait_time_ms:.1f}ms)"
        )

        return batch

    async def _get_from_any_queue(self, *queues: asyncio.Queue) -> InferenceRequest:
        """Wait for a request from any of the given queues.

        Args:
            *queues: Queue objects to wait on

        Returns:
            First request received from any queue
        """
        futures = [queue.get() for queue in queues]
        done, _ = await asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)
        return done.pop().result()

    def queue_length(self) -> int:
        """Get total requests waiting in all priority queues.

        Returns:
            Number of queued requests
        """
        return sum(q.qsize() for q in self._queues.values())

    def queue_depth(self) -> Dict[str, int]:
        """Get queue depth by priority level.

        Returns:
            Dictionary with queue sizes per priority
        """
        return {
            priority.name: self._queues[priority].qsize()
            for priority in RequestPriority
        }

    def stats(self) -> Dict:
        """Get scheduler statistics.

        Returns:
            Dictionary of performance metrics
        """
        avg_wait_ms = self._total_wait_ms / self._total_batches if self._total_batches > 0 else 0
        avg_batch_size = self._total_requests / self._total_batches if self._total_batches > 0 else 0

        return {
            "model": self.model,
            "total_requests": self._total_requests,
            "total_batches": self._total_batches,
            "avg_batch_size": avg_batch_size,
            "avg_wait_ms": avg_wait_ms,
            "current_queue_length": self.queue_length(),
            "queue_depth": self.queue_depth(),
        }
