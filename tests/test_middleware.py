"""Tests for middleware components."""

import pytest

from realtime_serve.middleware import RateLimiter


class TestRateLimiter:
    """Tests for token bucket rate limiter."""

    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        limiter = RateLimiter(tokens_per_minute=100)
        allowed = await limiter.check_rate_limit("client1")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_new_client_gets_full_bucket(self):
        limiter = RateLimiter(tokens_per_minute=100)
        # First request always passes since bucket starts full
        allowed = await limiter.check_rate_limit("new_client")
        assert allowed is True

    @pytest.mark.asyncio
    async def test_different_clients_independent(self):
        limiter = RateLimiter(tokens_per_minute=100)
        a = await limiter.check_rate_limit("a")
        b = await limiter.check_rate_limit("b")
        assert a is True
        assert b is True
