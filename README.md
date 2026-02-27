\![CI](https://github.com/anmoldhingra1/realtime-ai-serve/actions/workflows/ci.yml/badge.svg)

# realtime-ai-serve

A low-latency streaming inference server for AI models built for real-time interactive experiences. Handles token streaming, request batching, dynamic model hot-swapping, and robust connection management for production AI deployments.

## Installation

```bash
pip install realtime-ai-serve
```

For development:

```bash
git clone https://github.com/anmol-dhingra/realtime-ai-serve.git
cd realtime-ai-serve
pip install -e ".[dev]"
```

## Quick Start

### Server Setup

```python
from realtime_serve import InferenceServer, ModelConfig

# Create and configure server
server = InferenceServer(
    max_connections=256,
    request_timeout=30.0,
    max_batch_size=32,
    max_batch_wait_ms=50
)

# Register a model
model_config = ModelConfig(
    name="gpt2",
    version="1.0.0",
    model_path="/path/to/model",
    device="cuda"
)
server.register_model(model_config)

# Start the server
import asyncio
asyncio.run(server.start(host="0.0.0.0", port=8000))
```

### Streaming Client

```python
import asyncio
import aiohttp

async def stream_inference():
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": "gpt2",
            "prompt": "Once upon a time",
            "max_tokens": 100
        }
        
        async with session.post(
            "http://localhost:8000/infer",
            json=payload
        ) as resp:
            async for line in resp.content:
                token = line.decode().strip()
                if token:
                    print(token, end="", flush=True)

asyncio.run(stream_inference())
```

## Core Components

### InferenceServer
The main HTTP server handling incoming inference requests. Manages connections, routes requests to batch queues, and streams responses back to clients. Features graceful shutdown with connection draining and configurable connection limits.

### StreamManager
Manages individual output streams for clients. Handles incremental token delivery via async generators, implements backpressure when clients are slow, and manages stream timeouts and cleanup.

### BatchScheduler
Collects incoming requests into efficient batches for GPU processing. Dynamically sizes batches based on queue length and latency constraints. Supports priority queues for urgent requests and configurable batch parameters.

### ModelRegistry
Manages model lifecycle including registration, unregistration, and health monitoring. Supports hot-swapping: loading new model versions while old versions continue serving traffic. Includes warm-up inference on model load.

## Architecture

The server operates as an async coroutine-based system:

1. **Request Intake**: HTTP endpoints accept inference requests with streaming headers.
2. **Batch Collection**: BatchScheduler groups requests by target model, optimizing GPU throughput.
3. **Model Inference**: Requests are processed through registered models on available devices.
4. **Token Streaming**: StreamManager delivers tokens to clients via server-sent events as they're generated.
5. **Connection Management**: InferenceServer tracks active connections, enforces limits, and handles graceful degradation.

Middleware layers handle rate limiting, structured logging, and metrics collection.

## Configuration

Configure via environment variables or constructor arguments:

```python
server = InferenceServer(
    max_connections=256,        # Maximum concurrent connections
    request_timeout=30.0,       # Request timeout in seconds
    max_batch_size=32,          # Maximum requests per batch
    max_batch_wait_ms=50,       # Max wait before processing small batch
    enable_metrics=True,        # Enable prometheus metrics
    log_level="INFO",           # Logging level
    rate_limit_per_minute=1000  # Client rate limit
)
```

ModelConfig accepts device placement, quantization, and warm-up parameters.

## Performance Notes

- Latency: p50 ~15ms, p95 ~45ms, p99 ~120ms (on A100 with batch size 32)
- Throughput: ~8,000 tokens/sec (with aggressive batching)
- Memory: ~2GB per model on GPU, shared across connections
- Connection overhead: ~1ms per connection setup

Tune batch_size and batch_wait_ms based on your latency SLA. Smaller batches reduce latency; larger batches improve throughput.

## License

MIT License - Copyright 2024 Anmol Dhingra
