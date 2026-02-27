# Quick Start Guide

## Installation

```bash
# Clone the repository
git clone https://github.com/anmol-dhingra/realtime-ai-serve.git
cd realtime-ai-serve

# Install in development mode
pip install -e .

# Install with all dependencies for examples
pip install -e ".[torch]"
```

## 5-Minute Tutorial

### 1. Start the Server

In one terminal, run the example server:

```bash
cd realtime-ai-serve
python examples/serve_model.py
```

You should see:
```
Starting inference server...
Visit http://127.0.0.1:8000/health to check server status
POST to http://127.0.0.1:8000/infer to make requests
```

### 2. Make a Request

In another terminal, test the server:

```bash
# Check health
curl http://127.0.0.1:8000/health

# Make an inference request
curl -X POST http://127.0.0.1:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt2",
    "prompt": "Once upon a time",
    "max_tokens": 20
  }'
```

### 3. Run Benchmarks

In another terminal:

```bash
python examples/benchmark_client.py
```

This will run three benchmark scenarios and show latency percentiles and throughput.

## Basic Python Usage

### Create and Run a Server

```python
import asyncio
from realtime_serve import InferenceServer, ModelConfig

async def main():
    # Create server
    server = InferenceServer(max_connections=256, max_batch_size=32)
    
    # Register a model
    model_config = ModelConfig(
        name="my_model",
        version="1.0.0",
        device="cuda"
    )
    
    # In real usage, provide a loader function
    # server.register_model(model_config, loader=my_loader_func)
    
    # Start the server
    await server.start(host="127.0.0.1", port=8000)

asyncio.run(main())
```

### Make Requests from Python

```python
import asyncio
import aiohttp
import json

async def main():
    async with aiohttp.ClientSession() as session:
        # Non-streaming request
        payload = {
            "model": "gpt2",
            "prompt": "Hello world",
            "max_tokens": 50,
        }
        
        async with session.post(
            "http://127.0.0.1:8000/infer",
            json=payload
        ) as resp:
            result = await resp.json()
            for token_obj in result["tokens"]:
                print(token_obj["token"], end="")

asyncio.run(main())
```

## Common Tasks

### Change Batch Size (Latency vs Throughput Tradeoff)

```python
# For low latency (fast responses, fewer requests/sec)
server = InferenceServer(
    max_batch_size=8,
    max_batch_wait_ms=10
)

# For high throughput (slower responses, more requests/sec)
server = InferenceServer(
    max_batch_size=64,
    max_batch_wait_ms=100
)
```

### Enable Detailed Logging

```python
from realtime_serve import ServerConfig, InferenceServer

config = ServerConfig(
    host="127.0.0.1",
    port=8000,
    log_level="DEBUG"
)

server = InferenceServer(config=config)
```

### Check Server Status

```bash
# Via HTTP
curl http://127.0.0.1:8000/status | jq

# Shows:
# {
#   "is_shutting_down": false,
#   "active_connections": 5,
#   "active_streams": 3,
#   "loaded_models": {"gpt2": ["1.0.0"]},
#   "queue_stats": {...}
# }
```

### Get Performance Metrics

```bash
# Via HTTP
curl http://127.0.0.1:8000/metrics | jq '.gpt2'

# Shows:
# {
#   "model": "gpt2",
#   "request_count": 150,
#   "error_count": 0,
#   "error_rate": 0.0,
#   "latency_ms": {
#     "p50": 28.4,
#     "p95": 92.1,
#     "p99": 131.2,
#     "mean": 45.3
#   },
#   "throughput_tokens_per_sec": 4523.1
# }
```

### Handle Rate Limiting

```python
async def request_with_retry():
    async with aiohttp.ClientSession() as session:
        max_retries = 3
        for attempt in range(max_retries):
            async with session.post(
                "http://127.0.0.1:8000/infer",
                json=payload
            ) as resp:
                if resp.status == 429:  # Rate limited
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"Rate limited, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    continue
                
                data = await resp.json()
                return data
        
        raise Exception("Failed after retries")
```

### Update/Hot-Swap a Model

```python
import asyncio
from realtime_serve import ModelConfig

async def update_model(server):
    # Load new version while old one serves traffic
    new_config = ModelConfig(
        name="my_model",
        version="2.0.0",
        device="cuda"
    )
    
    await server.model_registry.load_model(new_config)
    
    # Switch traffic to new version
    server.model_registry.set_active_version("my_model", "2.0.0")
    
    # Old requests finish with v1, new requests use v2
    # Later, unload old version
    await server.model_registry.unload_model("my_model", version="1.0.0")
```

## Integrating Your Model

Create a model class that implements these methods:

```python
class MyModel:
    def __init__(self, config):
        self.config = config
        # Load your actual model
        self.model = load_from_checkpoint(config.model_path)
    
    async def generate(self, prompt, max_tokens=100, temperature=1.0):
        """Generate tokens for the given prompt.
        
        Returns: List[StreamToken]
        """
        tokens = []
        for _ in range(max_tokens):
            token_str = self.model.next_token(...)
            token = StreamToken(
                token=token_str,
                token_id=len(tokens),
            )
            tokens.append(token)
        return tokens
    
    async def health_check(self):
        """Optional: check if model is healthy."""
        try:
            self.model.forward("test")
            return True
        except Exception:
            return False

async def my_loader(config):
    return MyModel(config)

# Register with server
server.register_model(model_config, loader=my_loader)
```

## Troubleshooting

### Server won't start on port 8000

The port might be in use. Try a different port:

```python
await server.start(host="127.0.0.1", port=8001)
```

Or kill the existing process:

```bash
lsof -i :8000
kill -9 <PID>
```

### High latency p99

Check batch size - smaller batch size = lower latency:

```python
server = InferenceServer(max_batch_size=8, max_batch_wait_ms=10)
```

### Low throughput

Increase batch size:

```python
server = InferenceServer(max_batch_size=64, max_batch_wait_ms=100)
```

### Rate limit errors

Adjust rate limit configuration:

```python
config = ServerConfig(
    rate_limit_per_minute=20000  # Increase from default 10000
)
server = InferenceServer(config=config)
```

Or set client_id to share quota:

```python
payload = {
    "model": "gpt2",
    "prompt": "...",
    "client_id": "my-app",  # Requests from same client share rate limit
}
```

## Next Steps

- Read the full [README.md](README.md)
- Review [PACKAGE_STRUCTURE.md](PACKAGE_STRUCTURE.md) for architecture
- Check [IMPLEMENTATION_DETAILS.md](IMPLEMENTATION_DETAILS.md) for internals
- See [CODE_EXAMPLES.md](CODE_EXAMPLES.md) for more usage patterns

## Support

- Check [GitHub Issues](https://github.com/anmol-dhingra/realtime-ai-serve/issues)
- Review example code in `/examples`
- See test cases for usage patterns
