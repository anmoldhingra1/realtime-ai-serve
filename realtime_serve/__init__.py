"""Realtime AI Serve - Low-latency streaming inference server."""

from realtime_serve.server import InferenceServer, run_server
from realtime_serve.batch import BatchScheduler
from realtime_serve.models import ModelRegistry, Model
from realtime_serve.stream import StreamManager
from realtime_serve.types import (
    InferenceRequest,
    InferenceResponse,
    StreamToken,
    ModelConfig,
    ServerConfig,
    BatchConfig,
    RequestPriority,
)
from realtime_serve.middleware import (
    RateLimiter,
    RequestLogger,
    MetricsCollector,
    MiddlewareChain,
)


__version__ = "0.1.0"
__author__ = "Anmol Dhingra"

__all__ = [
    # Server
    "InferenceServer",
    "run_server",
    # Components
    "BatchScheduler",
    "ModelRegistry",
    "Model",
    "StreamManager",
    # Types
    "InferenceRequest",
    "InferenceResponse",
    "StreamToken",
    "ModelConfig",
    "ServerConfig",
    "BatchConfig",
    "RequestPriority",
    # Middleware
    "RateLimiter",
    "RequestLogger",
    "MetricsCollector",
    "MiddlewareChain",
]
