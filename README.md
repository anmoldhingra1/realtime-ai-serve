![CI](https://github.com/anmoldhingra1/realtime-ai-serve/actions/workflows/ci.yml/badge.svg)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

# realtime-ai-serve

A low-latency streaming inference server for AI models. Handles token streaming, request batching, dynamic model hot-swapping, and connection management for production deployments.

Built on asyncio and aiohttp — no heavy frameworks, just fast async I/O.

## Install

```bash
pip install realtime-ai-serve
```

## Quick Start

```python
import asyncio
from realtime_serve import InferenceServer, ModelConfig

server = InferenceServer(
    max_connections=256,
    request_timeout=30.0,
    max_batch_size=32,
)

server.register_model(ModelConfig(
    name="gpt2",
    version="1.0.0",
    model_path="/models/gpt2",
    device="cuda",
))

asyncio.run(server.start(host="0.0.0.0", port=8000))
```

### Streaming Client

```python
import aiohttp, asyncio

async def stream():
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:8000/infer", json={
            "model": "gpt2",
            "prompt": "Once upon a time",
            "max_tokens": 100,
        }) as resp:
            async for line in resp.content:
                print(line.decode().strip(), end="", flush=True)

asyncio.run(stream())
```

## Features

**Token streaming** — Responses stream token-by-token via server-sent events. StreamManager handles backpressure, buffering, and timeouts per connection.

**Request batching** — BatchScheduler groups requests by model for GPU-efficient processing. Dynamic batch sizing adapts to load. Priority queues ensure urgent requests aren't starved.

```python
from realtime_serve import BatchConfig

config = BatchConfig(
    max_batch_size=32,    # max requests per batch
    max_wait_ms=50,       # max wait before flushing a partial batch
    dynamic_batching=True,
)
```

**Model hot-swap** — Load new model versions while old ones continue serving. ModelRegistry manages versioning, health checks, and warm-up inference.

```python
# Register a loader, then load versions independently
server.model_registry.register_loader("gpt2", load_gpt2)
await server.model_registry.load_model(ModelConfig(name="gpt2", version="2.0"))
```

**Middleware** — Pluggable middleware chain with built-in rate limiting (token bucket), structured request logging, and metrics collection.

```python
from realtime_serve import RateLimiter

limiter = RateLimiter(tokens_per_minute=1000)
allowed = await limiter.check_rate_limit("client_42")
```

**Typed configuration** — All configs are dataclasses with validation. Invalid values raise immediately, not at runtime.

```python
from realtime_serve import ServerConfig

config = ServerConfig(
    port=8000,
    max_connections=256,
    request_timeout=30.0,
    rate_limit_per_minute=10000,
    graceful_shutdown_timeout=30.0,
)
```

## Architecture

```
Client ──HTTP──▶ InferenceServer ──▶ MiddlewareChain
                      │                    │
                      ▼                    ▼
               BatchScheduler       RateLimiter
              (priority queues)     RequestLogger
                      │             MetricsCollector
                      ▼
               ModelRegistry ──▶ Model (versioned)
                      │
                      ▼
               StreamManager ──SSE──▶ Client
              (per-connection buffer)
```

All I/O is async. No threads needed for the serving path.

## Performance

Benchmarked on A100 with batch size 32:

| Metric | Value |
|--------|-------|
| p50 latency | ~15ms |
| p95 latency | ~45ms |
| p99 latency | ~120ms |
| Throughput | ~8,000 tok/s |
| Memory per model | ~2GB GPU |

Tune `max_batch_size` and `max_batch_wait_ms` based on your latency SLA.

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

46 tests covering types, batching, streaming, models, and middleware.

## License

MIT
