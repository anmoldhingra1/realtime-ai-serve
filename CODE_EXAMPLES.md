# Code Examples

## Complete Example: Running a Server

```python
# examples/serve_model.py
import asyncio
from realtime_serve import InferenceServer, ModelConfig, ServerConfig

async def main():
    # Create configuration
    config = ServerConfig(
        host="127.0.0.1",
        port=8000,
        max_batch_size=32,
        max_batch_wait_ms=50,
    )
    
    # Create server
    server = InferenceServer(config=config)
    
    # Register model
    model_config = ModelConfig(
        name="gpt2",
        version="1.0.0",
        device="cuda",
    )
    server.register_model(model_config, loader=my_model_loader)
    
    # Start server
    await server.start()

asyncio.run(main())
```

## Client: Non-streaming Request

```python
import aiohttp
import json

async def request():
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": "gpt2",
            "prompt": "Once upon a time",
            "max_tokens": 100,
            "temperature": 0.8,
            "priority": "NORMAL",
        }
        
        async with session.post(
            "http://localhost:8000/infer",
            json=payload
        ) as resp:
            data = await resp.json()
            # data["tokens"] = [{"token": "...", "token_id": 123}, ...]
            for token_obj in data["tokens"]:
                print(token_obj["token"], end="")
```

## Client: Streaming Request

```python
async def stream():
    async with aiohttp.ClientSession() as session:
        payload = {
            "model": "gpt2",
            "prompt": "Once upon a time",
            "max_tokens": 100,
        }
        
        async with session.post(
            "http://localhost:8000/infer_stream",
            json=payload
        ) as resp:
            async for line in resp.content:
                if line:
                    token_data = json.loads(line)
                    print(token_data["token"], end="", flush=True)
```

## Custom Model Loader

```python
from realtime_serve import ModelConfig

class MyModel:
    def __init__(self, config: ModelConfig):
        self.config = config
        # Load actual model here
        # self.model = load_model_from(config.model_path)
    
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 1.0,
    ) -> List[StreamToken]:
        """Generate tokens."""
        tokens = []
        # Generate tokens one by one
        for i in range(max_tokens):
            token_str = self.model.next_token(...)
            token = StreamToken(
                token=token_str,
                token_id=i,
                logprob=-0.5,
            )
            tokens.append(token)
        return tokens
    
    async def health_check(self) -> bool:
        """Check model health."""
        try:
            # Test inference with dummy input
            output = self.model.forward("test", max_tokens=1)
            return True
        except Exception:
            return False
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        if hasattr(self.model, 'cleanup'):
            await self.model.cleanup()

async def loader(config: ModelConfig) -> MyModel:
    """Load a model."""
    return MyModel(config)
```

## Request Prioritization

```python
payload_high_priority = {
    "model": "gpt2",
    "prompt": "Urgent: ...",
    "priority": "HIGH",  # Will be processed first
}

payload_low_priority = {
    "model": "gpt2",
    "prompt": "Background task: ...",
    "priority": "LOW",  # Fills remaining batch slots
}

await session.post("http://localhost:8000/infer", json=payload_high_priority)
await session.post("http://localhost:8000/infer", json=payload_low_priority)
```

## Model Hot-Swapping

```python
server = InferenceServer()

# Load initial version
config_v1 = ModelConfig(name="gpt2", version="1.0.0")
server.register_model(config_v1, loader=loader)
await server.model_registry.load_model(config_v1)

# In production, request traffic served by v1.0.0
# ...

# Load new version in background
config_v2 = ModelConfig(name="gpt2", version="2.0.0")
server.register_model(config_v2, loader=loader)
await server.model_registry.load_model(config_v2)

# Switch traffic to v2 (existing requests finish with v1)
server.model_registry.set_active_version("gpt2", "2.0.0")

# Later, unload old version
await server.model_registry.unload_model("gpt2", version="1.0.0")
```

## Rate Limiting

```python
# Server-side: configured per client
config = ServerConfig(rate_limit_per_minute=600)  # 10 req/sec per client

# Client-side: handle 429 response
async with session.post("http://localhost:8000/infer", json=payload) as resp:
    if resp.status == 429:
        print("Rate limited, backing off...")
        await asyncio.sleep(1.0)
    elif resp.status == 200:
        data = await resp.json()
        process(data)
```

## Metrics Collection

```python
# Get metrics for a model
metrics = await server.metrics_collector.get_metrics("gpt2")
print(f"p50 latency: {metrics['latency_ms']['p50']:.1f}ms")
print(f"p99 latency: {metrics['latency_ms']['p99']:.1f}ms")
print(f"Error rate: {metrics['error_rate']:.2%}")
print(f"Throughput: {metrics['throughput_tokens_per_sec']:.0f} tokens/sec")

# Via HTTP endpoint
async with session.get("http://localhost:8000/metrics") as resp:
    all_metrics = await resp.json()
```

## Batch Configuration

```python
# More aggressive batching (higher latency, higher throughput)
config = ServerConfig(
    max_batch_size=64,      # Larger batches
    max_batch_wait_ms=100,  # Longer wait
)
# Expected: p50 latency increases, p99 improves, throughput increases

# More latency-sensitive (lower latency, lower throughput)
config = ServerConfig(
    max_batch_size=16,      # Smaller batches
    max_batch_wait_ms=10,   # Shorter wait
)
# Expected: p50 latency decreases, throughput decreases
```

## Health Check

```python
# Simple health endpoint
async with session.get("http://localhost:8000/health") as resp:
    health = await resp.json()
    # {"status": "healthy", "active_connections": 42, "active_streams": 18}

# Full status endpoint
async with session.get("http://localhost:8000/status") as resp:
    status = await resp.json()
    # {
    #     "is_shutting_down": false,
    #     "active_connections": 42,
    #     "active_streams": 18,
    #     "loaded_models": {"gpt2": ["1.0.0", "2.0.0"]},
    #     "queue_stats": {...}
    # }
```

## Load Testing

```bash
# Run benchmark client
python examples/benchmark_client.py

# Output:
# BENCHMARK RESULTS
# ====================================================================
# Total Requests: 100
# Successful: 100
# Failed: 0
# Total Time: 12.34s
# Throughput: 8.10 req/s
# 
# Latency Statistics (ms):
#   Min: 8.23
#   Max: 142.5
#   Mean: 34.6
#   Median (p50): 28.4
#   p95: 92.1
#   p99: 131.2
```

## API Endpoints

```
POST /infer
  - Non-streaming inference
  - Request: JSON with model, prompt, max_tokens, etc.
  - Response: JSON with tokens array

POST /infer_stream
  - Streaming inference
  - Request: JSON with model, prompt, max_tokens, etc.
  - Response: Server-sent events (text/event-stream)

GET /health
  - Health check
  - Response: {"status": "healthy", ...}

GET /models
  - List loaded models
  - Response: {"models": {"gpt2": ["1.0.0"]}, ...}

GET /metrics
  - Performance metrics per model
  - Response: {"gpt2": {"p50": 28.4, "p95": 92.1, ...}, ...}

GET /status
  - Server status and debug info
  - Response: Full server state
```

## Error Handling

```python
try:
    async with session.post("http://localhost:8000/infer", json=payload) as resp:
        if resp.status == 400:
            error = await resp.json()
            print(f"Invalid request: {error['error']}")
        elif resp.status == 429:
            print("Rate limited")
        elif resp.status == 500:
            error = await resp.json()
            print(f"Server error: {error['error']}")
        else:
            data = await resp.json()
            process(data)
except asyncio.TimeoutError:
    print("Request timeout")
except aiohttp.ClientError as e:
    print(f"Connection error: {e}")
```
