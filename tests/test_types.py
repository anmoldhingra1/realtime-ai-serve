"""Tests for type definitions and validation."""

import pytest

from realtime_serve.types import (
    InferenceRequest,
    InferenceResponse,
    StreamToken,
    BatchConfig,
    ModelConfig,
    ServerConfig,
    RequestPriority,
)


class TestInferenceRequest:
    """Tests for InferenceRequest validation."""

    def test_valid_request(self):
        req = InferenceRequest(
            request_id="r1",
            model="gpt2",
            prompt="Hello",
        )
        assert req.max_tokens == 100
        assert req.temperature == 1.0
        assert req.priority == RequestPriority.NORMAL

    def test_custom_params(self):
        req = InferenceRequest(
            request_id="r2",
            model="llama",
            prompt="Hi",
            max_tokens=512,
            temperature=0.5,
            top_p=0.9,
            priority=RequestPriority.HIGH,
            timeout=60.0,
            client_id="client_1",
        )
        assert req.max_tokens == 512
        assert req.temperature == 0.5
        assert req.priority == RequestPriority.HIGH

    def test_invalid_max_tokens(self):
        with pytest.raises(ValueError, match="max_tokens"):
            InferenceRequest(request_id="r", model="m", prompt="p", max_tokens=0)

    def test_invalid_temperature_high(self):
        with pytest.raises(ValueError, match="temperature"):
            InferenceRequest(request_id="r", model="m", prompt="p", temperature=3.0)

    def test_invalid_temperature_low(self):
        with pytest.raises(ValueError, match="temperature"):
            InferenceRequest(request_id="r", model="m", prompt="p", temperature=-0.1)

    def test_invalid_top_p(self):
        with pytest.raises(ValueError, match="top_p"):
            InferenceRequest(request_id="r", model="m", prompt="p", top_p=1.5)

    def test_metadata_defaults_empty(self):
        req = InferenceRequest(request_id="r", model="m", prompt="p")
        assert req.metadata == {}


class TestStreamToken:
    """Tests for StreamToken."""

    def test_basic_token(self):
        t = StreamToken(token="hello", token_id=42)
        assert t.token == "hello"
        assert t.logprob is None
        assert t.is_special is False

    def test_special_token(self):
        t = StreamToken(token="<eos>", token_id=0, logprob=-0.5, is_special=True)
        assert t.is_special is True
        assert t.logprob == -0.5


class TestInferenceResponse:
    """Tests for InferenceResponse."""

    def test_success_response(self):
        tokens = [StreamToken(token="hi", token_id=1)]
        resp = InferenceResponse(
            request_id="r1",
            model="gpt2",
            tokens=tokens,
            total_tokens=1,
            latency_ms=15.0,
        )
        assert resp.error is None
        assert resp.total_tokens == 1

    def test_error_response(self):
        resp = InferenceResponse(
            request_id="r1",
            model="gpt2",
            tokens=[],
            total_tokens=0,
            latency_ms=0.0,
            error="model not found",
        )
        assert resp.error == "model not found"


class TestBatchConfig:
    """Tests for BatchConfig validation."""

    def test_defaults(self):
        cfg = BatchConfig()
        assert cfg.max_batch_size == 32
        assert cfg.max_wait_ms == 50
        assert cfg.dynamic_batching is True

    def test_invalid_batch_size(self):
        with pytest.raises(ValueError, match="max_batch_size"):
            BatchConfig(max_batch_size=0)

    def test_invalid_wait(self):
        with pytest.raises(ValueError, match="max_wait_ms"):
            BatchConfig(max_wait_ms=-1)

    def test_min_exceeds_max(self):
        with pytest.raises(ValueError, match="min_batch_size"):
            BatchConfig(max_batch_size=4, min_batch_size=8)


class TestModelConfig:
    """Tests for ModelConfig validation."""

    def test_valid_config(self):
        cfg = ModelConfig(name="gpt2", version="2.0", device="cuda")
        assert cfg.name == "gpt2"
        assert cfg.dtype == "float32"

    def test_empty_name(self):
        with pytest.raises(ValueError, match="name"):
            ModelConfig(name="")

    def test_invalid_device(self):
        with pytest.raises(ValueError, match="device"):
            ModelConfig(name="m", device="tpu")

    def test_cpu_device(self):
        cfg = ModelConfig(name="m", device="cpu")
        assert cfg.device == "cpu"

    def test_mps_device(self):
        cfg = ModelConfig(name="m", device="mps")
        assert cfg.device == "mps"


class TestServerConfig:
    """Tests for ServerConfig validation."""

    def test_defaults(self):
        cfg = ServerConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8000
        assert cfg.max_connections == 256

    def test_invalid_port_zero(self):
        with pytest.raises(ValueError, match="port"):
            ServerConfig(port=0)

    def test_invalid_port_high(self):
        with pytest.raises(ValueError, match="port"):
            ServerConfig(port=70000)

    def test_invalid_connections(self):
        with pytest.raises(ValueError, match="max_connections"):
            ServerConfig(max_connections=0)

    def test_invalid_timeout(self):
        with pytest.raises(ValueError, match="request_timeout"):
            ServerConfig(request_timeout=-1)


class TestRequestPriority:
    """Tests for RequestPriority enum."""

    def test_ordering(self):
        assert RequestPriority.LOW.value < RequestPriority.NORMAL.value
        assert RequestPriority.NORMAL.value < RequestPriority.HIGH.value

    def test_all_values(self):
        assert set(RequestPriority) == {
            RequestPriority.LOW,
            RequestPriority.NORMAL,
            RequestPriority.HIGH,
        }
