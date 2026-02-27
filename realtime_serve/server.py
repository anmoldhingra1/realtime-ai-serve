"""Main inference server implementation."""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional, Set

from aiohttp import web

from realtime_serve.types import (
    InferenceRequest,
    ModelConfig,
    RequestPriority,
    ServerConfig,
    BatchConfig,
)
from realtime_serve.batch import BatchScheduler
from realtime_serve.models import ModelRegistry
from realtime_serve.stream import StreamManager
from realtime_serve.middleware import (
    MiddlewareChain,
    RateLimiter,
    RequestLogger,
    MetricsCollector,
)


logger = logging.getLogger(__name__)


class InferenceServer:
    """Main HTTP server for real-time inference.

    Handles incoming inference requests, manages connections, routes to batch
    queues, and streams responses. Features graceful shutdown with connection
    draining and configurable connection limits.
    """

    def __init__(
        self,
        config: Optional[ServerConfig] = None,
        max_connections: Optional[int] = None,
        request_timeout: Optional[float] = None,
        max_batch_size: Optional[int] = None,
        max_batch_wait_ms: Optional[int] = None,
    ):
        """Initialize InferenceServer.

        Args:
            config: ServerConfig instance (overrides other params if provided)
            max_connections: Maximum concurrent connections
            request_timeout: Request timeout in seconds
            max_batch_size: Maximum batch size
            max_batch_wait_ms: Maximum wait time for batching
        """
        if config:
            self.config = config
        else:
            self.config = ServerConfig(
                max_connections=max_connections or 256,
                request_timeout=request_timeout or 30.0,
                max_batch_size=max_batch_size or 32,
                max_batch_wait_ms=max_batch_wait_ms or 50,
            )

        # Configure logging
        logging.basicConfig(level=self.config.log_level)

        # Core components
        self.model_registry = ModelRegistry()
        self.stream_manager = StreamManager(default_timeout=self.config.request_timeout)
        self._batch_schedulers: Dict[str, BatchScheduler] = {}

        # Middleware
        self.rate_limiter = RateLimiter(
            tokens_per_minute=self.config.rate_limit_per_minute
        )
        self.request_logger = RequestLogger(log_level=self.config.log_level)
        self.metrics_collector = MetricsCollector()

        self.middleware_chain = MiddlewareChain(
            rate_limiter=self.rate_limiter,
            request_logger=self.request_logger,
            metrics_collector=self.metrics_collector,
        )

        # Server state
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._active_connections: Set[str] = set()
        self._is_shutting_down = False
        self._shutdown_event = asyncio.Event()
        self._inference_tasks: Set[asyncio.Task] = set()

    def register_model(
        self,
        config: ModelConfig,
        loader: Optional[Callable[[ModelConfig], Any]] = None,
    ) -> None:
        """Register a model with the server.

        Args:
            config: Model configuration
            loader: Optional custom model loader function
        """
        if loader:
            self.model_registry.register_loader(config.name, loader)

        # Create batch scheduler for this model
        batch_config = BatchConfig(
            max_batch_size=self.config.max_batch_size,
            max_wait_ms=self.config.max_batch_wait_ms,
        )
        self._batch_schedulers[config.name] = BatchScheduler(config.name, batch_config)

        logger.info(f"Registered model {config.name}")

    async def _load_models(self) -> None:
        """Load all registered models."""
        logger.info("Loading models...")

        for model_name, scheduler in self._batch_schedulers.items():
            # Get model config - in real setup would come from config file
            # For now, create a basic config
            config = ModelConfig(name=model_name)

            try:
                await self.model_registry.load_model(config)
            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")

    async def start(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        """Start the inference server.

        Args:
            host: Server host (default from config)
            port: Server port (default from config)
        """
        host = host or self.config.host
        port = port or self.config.port

        logger.info(f"Starting InferenceServer on {host}:{port}")

        # Create web application
        self._app = web.Application()

        # Setup routes
        self._app.router.add_post("/infer", self._handle_infer)
        self._app.router.add_post("/infer_stream", self._handle_infer_stream)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/models", self._handle_list_models)
        self._app.router.add_get("/metrics", self._handle_metrics)
        self._app.router.add_get("/status", self._handle_status)

        # Setup cleanup
        self._app.on_startup.append(self._on_startup)
        self._app.on_shutdown.append(self._on_shutdown)

        # Start server
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port)
        await site.start()

        logger.info(f"InferenceServer started on {host}:{port}")

        # Keep running
        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the inference server."""
        logger.info("Stopping InferenceServer")

        self._is_shutting_down = True

        # Drain active connections
        await self._drain_connections()

        # Cancel inference tasks
        if self._inference_tasks:
            for task in self._inference_tasks:
                task.cancel()

            await asyncio.gather(*self._inference_tasks, return_exceptions=True)

        # Cleanup stream manager
        await self.stream_manager.shutdown()

        # Cleanup model registry
        await self.model_registry.shutdown()

        # Shutdown web server
        if self._runner:
            await self._runner.cleanup()

        self._shutdown_event.set()
        logger.info("InferenceServer stopped")

    async def _on_startup(self, app: web.Application) -> None:
        """Handle server startup."""
        await self._load_models()

    async def _on_shutdown(self, app: web.Application) -> None:
        """Handle server shutdown."""
        pass

    async def _drain_connections(self) -> None:
        """Gracefully drain active connections."""
        logger.info(f"Draining {len(self._active_connections)} connections")

        deadline = time.time() + self.config.graceful_shutdown_timeout

        while self._active_connections and time.time() < deadline:
            await asyncio.sleep(0.1)

        if self._active_connections:
            logger.warning(
                f"Forcefully closing {len(self._active_connections)} remaining connections"
            )

    async def _handle_infer(self, request: web.Request) -> web.Response:
        """Handle non-streaming inference request."""
        conn_id = str(uuid.uuid4())
        self._active_connections.add(conn_id)

        try:
            return await self._process_infer_request(request, stream=False)
        finally:
            self._active_connections.discard(conn_id)

    async def _handle_infer_stream(self, request: web.Request) -> web.StreamResponse:
        """Handle streaming inference request."""
        conn_id = str(uuid.uuid4())
        self._active_connections.add(conn_id)

        try:
            return await self._process_infer_request(request, stream=True)
        finally:
            self._active_connections.discard(conn_id)

    async def _process_infer_request(
        self,
        request: web.Request,
        stream: bool = False,
    ) -> web.Response:
        """Process an inference request.

        Args:
            request: HTTP request
            stream: Whether to stream response

        Returns:
            HTTP response
        """
        request_id = str(uuid.uuid4())
        client_addr = request.remote
        start_time = time.time()

        try:
            # Parse request
            body = await request.json()

            inference_req = InferenceRequest(
                request_id=request_id,
                model=body.get("model", "default"),
                prompt=body.get("prompt", ""),
                max_tokens=body.get("max_tokens", 100),
                temperature=body.get("temperature", 1.0),
                top_p=body.get("top_p", 0.95),
                client_id=body.get("client_id", ""),
                priority=RequestPriority[body.get("priority", "NORMAL")],
            )

            # Process through middleware
            if not await self.middleware_chain.process_request(inference_req, client_addr):
                await self.middleware_chain.record_response(
                    request_id,
                    inference_req.model,
                    0,
                    0,
                    error="Rate limited"
                )
                return web.json_response(
                    {"error": "Rate limited"},
                    status=429
                )

            # Get or create batch scheduler
            if inference_req.model not in self._batch_schedulers:
                batch_config = BatchConfig(
                    max_batch_size=self.config.max_batch_size,
                    max_wait_ms=self.config.max_batch_wait_ms,
                )
                self._batch_schedulers[inference_req.model] = BatchScheduler(
                    inference_req.model, batch_config
                )

            # Enqueue request
            await self._batch_schedulers[inference_req.model].enqueue(inference_req)

            if stream:
                # Streaming response
                return await self._stream_response(inference_req, client_addr)
            else:
                # Collect all tokens then respond
                tokens = []
                stream_id = request_id
                stream_gen = self.stream_manager.create_stream(stream_id)

                try:
                    async for token in stream_gen:
                        tokens.append(token)
                except asyncio.TimeoutError:
                    pass
                finally:
                    await self.stream_manager.close_stream(stream_id)

                latency_ms = (time.time() - start_time) * 1000

                await self.middleware_chain.record_response(
                    request_id,
                    inference_req.model,
                    latency_ms,
                    len(tokens),
                )

                return web.json_response({
                    "request_id": request_id,
                    "model": inference_req.model,
                    "tokens": [
                        {
                            "token": t.token,
                            "token_id": t.token_id,
                            "logprob": t.logprob,
                        }
                        for t in tokens
                    ],
                })

        except Exception as e:
            logger.error(f"Error processing request {request_id}: {e}")

            await self.middleware_chain.record_response(
                request_id,
                "unknown",
                (time.time() - start_time) * 1000,
                0,
                error=str(e)
            )

            return web.json_response(
                {"error": str(e)},
                status=400
            )

    async def _stream_response(
        self,
        request: InferenceRequest,
        client_addr: str,
    ) -> web.StreamResponse:
        """Stream response tokens to client.

        Args:
            request: Inference request
            client_addr: Client address

        Returns:
            Streaming HTTP response
        """
        resp = web.StreamResponse()
        resp.content_type = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        await resp.prepare(request)

        stream_id = request.request_id
        stream_gen = self.stream_manager.create_stream(stream_id)

        try:
            async for token in stream_gen:
                data = json.dumps({
                    "token": token.token,
                    "token_id": token.token_id,
                }).encode() + b"\n"
                await resp.write(data)
        except Exception as e:
            logger.error(f"Error streaming to {client_addr}: {e}")
        finally:
            await self.stream_manager.close_stream(stream_id)
            await resp.write_eof()

        return resp

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "healthy",
            "active_connections": len(self._active_connections),
            "active_streams": self.stream_manager.active_streams(),
        })

    async def _handle_list_models(self, request: web.Request) -> web.Response:
        """List registered models."""
        models = self.model_registry.list_models()

        return web.json_response({
            "models": models,
            "total_models": len(models),
        })

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Get metrics endpoint."""
        metrics = await self.metrics_collector.get_all_metrics()

        return web.json_response(metrics)

    async def _handle_status(self, request: web.Request) -> web.Response:
        """Get server status."""
        models = self.model_registry.list_models()

        status = {
            "is_shutting_down": self._is_shutting_down,
            "active_connections": len(self._active_connections),
            "active_streams": self.stream_manager.active_streams(),
            "loaded_models": models,
            "queue_stats": {
                name: scheduler.stats()
                for name, scheduler in self._batch_schedulers.items()
            },
        }

        return web.json_response(status)


async def run_server(config: ServerConfig) -> None:
    """Utility function to run a configured server.

    Args:
        config: Server configuration
    """
    server = InferenceServer(config=config)
    await server.start(config.host, config.port)
