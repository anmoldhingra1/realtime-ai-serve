"""Type definitions for the realtime inference server."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RequestPriority(Enum):
    """Priority levels for inference requests."""
    LOW = 0
    NORMAL = 1
    HIGH = 2


@dataclass
class InferenceRequest:
    """Represents an inference request from a client."""
    request_id: str
    model: str
    prompt: str
    max_tokens: int = 100
    temperature: float = 1.0
    top_p: float = 0.95
    priority: RequestPriority = RequestPriority.NORMAL
    timeout: float = 30.0
    client_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate request parameters."""
        if self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("temperature must be in [0, 2.0]")
        if not (0.0 <= self.top_p <= 1.0):
            raise ValueError("top_p must be in [0, 1.0]")


@dataclass
class StreamToken:
    """A single token streamed to the client."""
    token: str
    token_id: int
    logprob: Optional[float] = None
    is_special: bool = False


@dataclass
class InferenceResponse:
    """Complete inference response."""
    request_id: str
    model: str
    tokens: List[StreamToken]
    total_tokens: int
    latency_ms: float
    error: Optional[str] = None


@dataclass
class BatchConfig:
    """Configuration for batch scheduling."""
    max_batch_size: int = 32
    max_wait_ms: int = 50
    min_batch_size: int = 1
    dynamic_batching: bool = True
    
    def __post_init__(self) -> None:
        """Validate batch configuration."""
        if self.max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        if self.max_wait_ms < 0:
            raise ValueError("max_wait_ms must be non-negative")
        if self.min_batch_size > self.max_batch_size:
            raise ValueError("min_batch_size must be <= max_batch_size")


@dataclass
class ModelConfig:
    """Configuration for a model."""
    name: str
    version: str = "1.0.0"
    model_path: str = ""
    device: str = "cuda"
    dtype: str = "float32"
    quantized: bool = False
    max_seq_length: int = 2048
    warmup_tokens: int = 100
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate model configuration."""
        if not self.name:
            raise ValueError("model name must not be empty")
        if self.device not in ("cuda", "cpu", "mps"):
            raise ValueError(f"device must be 'cuda', 'cpu', or 'mps', got {self.device}")


@dataclass
class ServerConfig:
    """Configuration for the inference server."""
    host: str = "0.0.0.0"
    port: int = 8000
    max_connections: int = 256
    request_timeout: float = 30.0
    max_batch_size: int = 32
    max_batch_wait_ms: int = 50
    enable_metrics: bool = True
    log_level: str = "INFO"
    rate_limit_per_minute: int = 10000
    graceful_shutdown_timeout: float = 30.0
    
    def __post_init__(self) -> None:
        """Validate server configuration."""
        if self.port <= 0 or self.port > 65535:
            raise ValueError("port must be in range [1, 65535]")
        if self.max_connections <= 0:
            raise ValueError("max_connections must be positive")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
