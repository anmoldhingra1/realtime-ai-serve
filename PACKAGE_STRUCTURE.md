# Package Structure

## Directory Organization

```
realtime-ai-serve/
├── README.md                 # Comprehensive documentation
├── pyproject.toml           # Modern Python packaging configuration
├── LICENSE                  # MIT License
├── .gitignore              # Git ignore rules
├── PACKAGE_STRUCTURE.md    # This file
├── realtime_serve/         # Main package directory
│   ├── __init__.py         # Package initialization, public API
│   ├── types.py            # Type definitions and dataclasses
│   ├── server.py           # InferenceServer main class
│   ├── batch.py            # BatchScheduler for request batching
│   ├── stream.py           # StreamManager for token streaming
│   ├── models.py           # ModelRegistry for model lifecycle
│   └── middleware.py       # Middleware: RateLimiter, RequestLogger, MetricsCollector
└── examples/               # Example scripts
    ├── serve_model.py      # Example: Run server with mock model
    └── benchmark_client.py # Example: Load testing client
```

## Core Components

### Types (realtime_serve/types.py)
- `InferenceRequest`: Dataclass for inference requests with validation
- `StreamToken`: Token with metadata (logprob, special flags)
- `InferenceResponse`: Complete response wrapper
- `BatchConfig`: Batch scheduling configuration
- `ModelConfig`: Model configuration and metadata
- `ServerConfig`: Server runtime configuration
- `RequestPriority`: Enum for request prioritization

### Server (realtime_serve/server.py)
- `InferenceServer`: Main HTTP server class
  - Async request handling
  - Health check endpoints
  - Model registration and management
  - Connection tracking and graceful shutdown
  - Streaming and non-streaming response modes

### Stream Manager (realtime_serve/stream.py)
- `StreamManager`: Manages individual output streams
  - Async generator-based token delivery
  - Backpressure handling
  - Stream timeouts and cleanup
  - Per-stream statistics tracking
  - Idle stream detection

### Batch Scheduler (realtime_serve/batch.py)
- `BatchScheduler`: Groups requests into efficient batches
  - Priority queue support (HIGH, NORMAL, LOW)
  - Dynamic batch sizing
  - Configurable max batch size and wait time
  - Per-model scheduling
  - Batch statistics

### Model Registry (realtime_serve/models.py)
- `Model`: Wrapper around loaded models
  - Metadata tracking
  - Health monitoring
  - Usage statistics
- `ModelRegistry`: Model lifecycle management
  - Register/unregister models
  - Hot-swapping support
  - Warm-up inference
  - Model versioning
  - Health checking

### Middleware (realtime_serve/middleware.py)
- `RateLimiter`: Token bucket rate limiting per client
- `RequestLogger`: Structured JSON logging of requests
- `MetricsCollector`: Latency percentiles, throughput, error rates
- `MiddlewareChain`: Orchestrates middleware components

## Key Features

### Real-time Streaming
- Async generators for token delivery
- Backpressure handling for slow clients
- Server-sent events for browser compatibility
- Configurable stream timeouts

### Request Batching
- Priority-based scheduling
- Dynamic batch sizing based on queue depth
- Configurable batch parameters
- Per-model batch queues

### Model Management
- Hot-swapping without downtime
- Model versioning
- Warm-up inference on load
- Health monitoring

### Production Features
- Rate limiting per client
- Structured request logging
- Latency percentile metrics (p50, p95, p99)
- Throughput monitoring
- Graceful shutdown with connection draining
- Active connection tracking

## Type Hints

All code includes comprehensive type hints for:
- Function parameters and return types
- Class attributes
- Generic types (Dict, List, Optional, etc.)
- Async/await patterns

## Async/Await Throughout

- Uses asyncio for concurrency
- Non-blocking I/O
- Connection pooling
- Resource cleanup with async context managers

## Error Handling

- Request validation with informative errors
- Timeout handling
- Graceful degradation
- Detailed error logging

## Documentation

- Module-level docstrings
- Class docstrings with purpose
- Method docstrings with Args, Returns, Raises
- Inline comments for complex logic
