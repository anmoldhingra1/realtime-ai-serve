"""Tests for Model and ModelRegistry."""

import time

from realtime_serve.models import Model, ModelRegistry
from realtime_serve.types import ModelConfig


class TestModel:
    """Tests for Model wrapper."""

    def test_basic_creation(self):
        config = ModelConfig(name="gpt2", version="1.0", device="cpu")
        model = Model(config=config, model_obj="mock_model")
        assert model.config.name == "gpt2"
        assert model.inference_count == 0
        assert model.health_check_passed is True

    def test_record_inference(self):
        config = ModelConfig(name="gpt2", device="cpu")
        model = Model(config=config, model_obj="mock")
        model.record_inference(tokens_generated=50)
        model.record_inference(tokens_generated=30)
        assert model.inference_count == 2
        assert model.total_tokens_generated == 80

    def test_uptime(self):
        config = ModelConfig(name="gpt2", device="cpu")
        model = Model(config=config, model_obj="mock")
        assert model.uptime_seconds() >= 0

    def test_last_used_updated(self):
        config = ModelConfig(name="gpt2", device="cpu")
        model = Model(config=config, model_obj="mock")
        before = model.last_used_at
        time.sleep(0.01)
        model.record_inference(10)
        assert model.last_used_at >= before


class TestModelRegistry:
    """Tests for ModelRegistry."""

    def test_init_empty(self):
        registry = ModelRegistry()
        assert registry._models == {}
        assert registry._active_versions == {}

    def test_register_loader(self):
        registry = ModelRegistry()
        registry.register_loader("gpt2", lambda cfg: "loaded_model")
        assert "gpt2" in registry._model_loaders
