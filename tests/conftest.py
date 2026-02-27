"""Shared fixtures for realtime-ai-serve tests."""

import pytest

from realtime_serve.types import (
    BatchConfig,
    ModelConfig,
    ServerConfig,
    InferenceRequest,
    RequestPriority,
)


@pytest.fixture
def batch_config():
    return BatchConfig(max_batch_size=8, max_wait_ms=20)


@pytest.fixture
def model_config():
    return ModelConfig(name="test_model", version="1.0", device="cpu")


@pytest.fixture
def server_config():
    return ServerConfig(port=9000, max_connections=64, request_timeout=10.0)


@pytest.fixture
def sample_request():
    return InferenceRequest(
        request_id="test_r1",
        model="test_model",
        prompt="Hello world",
        max_tokens=50,
        priority=RequestPriority.NORMAL,
    )
