"""Benchmark client for load testing the inference server.

Measures request latencies (p50, p95, p99) and throughput.
"""

import asyncio
import logging
import statistics
import time
from typing import List, Optional

import aiohttp


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BenchmarkClient:
    """Load testing client for the inference server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        num_requests: int = 100,
        concurrency: int = 10,
    ):
        """Initialize BenchmarkClient.

        Args:
            base_url: Server base URL
            num_requests: Number of requests to send
            concurrency: Number of concurrent requests
        """
        self.base_url = base_url
        self.num_requests = num_requests
        self.concurrency = concurrency
        self.latencies: List[float] = []
        self.errors: List[str] = []
        self.successful_requests = 0
        self.total_tokens = 0

    async def make_request(
        self,
        session: aiohttp.ClientSession,
        request_num: int,
    ) -> Optional[float]:
        """Make a single inference request.

        Args:
            session: aiohttp session
            request_num: Request number

        Returns:
            Latency in milliseconds or None if failed
        """
        payload = {
            "model": "gpt2",
            "prompt": f"Request {request_num}: Once upon a time",
            "max_tokens": 50,
            "temperature": 0.8,
            "priority": "NORMAL",
        }

        start_time = time.time()
        tokens_count = 0

        try:
            async with session.post(
                f"{self.base_url}/infer",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    self.errors.append(f"Request {request_num}: HTTP {resp.status}")
                    return None

                data = await resp.json()
                tokens_count = len(data.get("tokens", []))

                self.successful_requests += 1
                self.total_tokens += tokens_count

                latency_ms = (time.time() - start_time) * 1000
                self.latencies.append(latency_ms)

                logger.debug(
                    f"Request {request_num}: {latency_ms:.1f}ms, "
                    f"{tokens_count} tokens"
                )

                return latency_ms

        except asyncio.TimeoutError:
            self.errors.append(f"Request {request_num}: Timeout")
            return None
        except Exception as e:
            self.errors.append(f"Request {request_num}: {str(e)}")
            return None

    async def run_benchmark(self) -> None:
        """Run the benchmark."""
        logger.info(
            f"Starting benchmark: {self.num_requests} requests, "
            f"concurrency={self.concurrency}"
        )

        connector = aiohttp.TCPConnector(limit=self.concurrency)

        async with aiohttp.ClientSession(connector=connector) as session:
            start_time = time.time()

            # Create tasks for all requests
            tasks = [
                self.make_request(session, i)
                for i in range(self.num_requests)
            ]

            # Run with concurrency limit
            semaphore = asyncio.Semaphore(self.concurrency)

            async def bounded_request(task: asyncio.Task) -> Optional[float]:
                async with semaphore:
                    return await task

            await asyncio.gather(
                *[bounded_request(task) for task in tasks],
                return_exceptions=False,
            )

            total_time = time.time() - start_time

        self.print_results(total_time)

    def print_results(self, total_time: float) -> None:
        """Print benchmark results.

        Args:
            total_time: Total time taken
        """
        print("\n" + "="*70)
        print("BENCHMARK RESULTS")
        print("="*70)

        print(f"\nTotal Requests: {self.num_requests}")
        print(f"Successful: {self.successful_requests}")
        print(f"Failed: {len(self.errors)}")
        print(f"Total Time: {total_time:.2f}s")
        print(f"Throughput: {self.successful_requests / total_time:.2f} req/s")

        if self.successful_requests > 0:
            print("\nToken Statistics:")
            print(f"  Total Tokens Generated: {self.total_tokens}")
            print(f"  Avg Tokens per Request: {self.total_tokens / self.successful_requests:.1f}")
            print(f"  Token Throughput: {self.total_tokens / total_time:.1f} tokens/sec")

        if self.latencies:
            sorted_latencies = sorted(self.latencies)
            n = len(sorted_latencies)

            print("\nLatency Statistics (ms):")
            print(f"  Min: {sorted_latencies[0]:.2f}")
            print(f"  Max: {sorted_latencies[-1]:.2f}")
            print(f"  Mean: {statistics.mean(sorted_latencies):.2f}")
            print(f"  Median (p50): {sorted_latencies[n//2]:.2f}")
            print(f"  p95: {sorted_latencies[int(n*0.95)]:.2f}")
            print(f"  p99: {sorted_latencies[int(n*0.99)]:.2f}")

            if n > 1:
                print(f"  Stdev: {statistics.stdev(sorted_latencies):.2f}")

        if self.errors:
            print("\nFirst 5 Errors:")
            for error in self.errors[:5]:
                print(f"  - {error}")

        print("\n" + "="*70)


async def run_benchmarks() -> None:
    """Run multiple benchmark scenarios."""

    scenarios = [
        {"num_requests": 50, "concurrency": 1, "name": "Sequential"},
        {"num_requests": 50, "concurrency": 5, "name": "Low Concurrency"},
        {"num_requests": 100, "concurrency": 20, "name": "High Concurrency"},
    ]

    for scenario in scenarios:
        print(f"\n\nRunning scenario: {scenario['name']}")
        print("-" * 70)

        client = BenchmarkClient(
            base_url="http://127.0.0.1:8000",
            num_requests=scenario["num_requests"],
            concurrency=scenario["concurrency"],
        )

        try:
            await client.run_benchmark()
        except ConnectionRefusedError:
            print("ERROR: Cannot connect to server at http://127.0.0.1:8000")
            print("Make sure the server is running (python examples/serve_model.py)")
            break


if __name__ == "__main__":
    asyncio.run(run_benchmarks())
