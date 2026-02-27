"""Tests for BatchScheduler."""

import pytest

from realtime_serve.batch import BatchScheduler
from realtime_serve.types import BatchConfig, InferenceRequest, RequestPriority


def _req(rid: str = "r1", priority: RequestPriority = RequestPriority.NORMAL) -> InferenceRequest:
    return InferenceRequest(
        request_id=rid,
        model="test_model",
        prompt="test",
        priority=priority,
    )


class TestBatchScheduler:
    """Tests for batch scheduling logic."""

    @pytest.fixture
    def scheduler(self):
        return BatchScheduler(
            model="test_model",
            config=BatchConfig(max_batch_size=4, max_wait_ms=10),
        )

    @pytest.mark.asyncio
    async def test_enqueue_single(self, scheduler):
        await scheduler.enqueue(_req("r1"))
        assert scheduler._total_requests == 1

    @pytest.mark.asyncio
    async def test_enqueue_multiple(self, scheduler):
        for i in range(5):
            await scheduler.enqueue(_req(f"r{i}"))
        assert scheduler._total_requests == 5

    @pytest.mark.asyncio
    async def test_priority_queuing(self, scheduler):
        await scheduler.enqueue(_req("low", RequestPriority.LOW))
        await scheduler.enqueue(_req("high", RequestPriority.HIGH))
        await scheduler.enqueue(_req("normal", RequestPriority.NORMAL))

        assert scheduler._total_requests == 3
        # HIGH queue should have 1 item
        assert scheduler._queues[RequestPriority.HIGH].qsize() == 1

    @pytest.mark.asyncio
    async def test_get_batch_returns_requests(self, scheduler):
        await scheduler.enqueue(_req("r1"))
        await scheduler.enqueue(_req("r2"))
        batch = await scheduler.get_batch()
        assert len(batch) >= 1

    @pytest.mark.asyncio
    async def test_batch_respects_max_size(self, scheduler):
        for i in range(10):
            await scheduler.enqueue(_req(f"r{i}"))
        batch = await scheduler.get_batch()
        assert len(batch) <= scheduler.config.max_batch_size
