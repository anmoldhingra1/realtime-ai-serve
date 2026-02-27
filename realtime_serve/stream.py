"""Stream management for real-time token delivery to clients."""

import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, Optional, Set

from realtime_serve.types import StreamToken


logger = logging.getLogger(__name__)


class StreamManager:
    """Manages individual output streams for clients.
    
    Handles incremental token delivery via async generators, implements
    backpressure when clients are slow, and manages stream timeouts and cleanup.
    """
    
    def __init__(self, default_timeout: float = 30.0, buffer_size: int = 100):
        """Initialize StreamManager.
        
        Args:
            default_timeout: Default timeout for streams in seconds
            buffer_size: Maximum tokens to buffer per stream
        """
        self.default_timeout = default_timeout
        self.buffer_size = buffer_size
        self._streams: Dict[str, Dict] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._cleanup_tasks: Set[asyncio.Task] = set()
    
    def create_stream(self, stream_id: str, timeout: Optional[float] = None) -> AsyncGenerator:
        """Create a new stream for a client.
        
        Args:
            stream_id: Unique identifier for the stream
            timeout: Optional timeout override for this stream
            
        Returns:
            Async generator that yields tokens as they're pushed
        """
        if stream_id in self._streams:
            raise ValueError(f"Stream {stream_id} already exists")
        
        timeout = timeout or self.default_timeout
        self._streams[stream_id] = {
            "queue": asyncio.Queue(maxsize=self.buffer_size),
            "closed": False,
            "created_at": time.time(),
            "timeout": timeout,
            "last_token_at": time.time(),
            "token_count": 0,
            "backpressure_events": 0,
        }
        self._locks[stream_id] = asyncio.Lock()
        
        logger.debug(f"Created stream {stream_id}")
        return self._stream_generator(stream_id)
    
    async def _stream_generator(self, stream_id: str) -> AsyncGenerator:
        """Internal async generator for stream token consumption.
        
        Args:
            stream_id: The stream identifier
            
        Yields:
            StreamToken objects pushed to the stream
        """
        stream = self._streams.get(stream_id)
        if not stream:
            return
        
        try:
            while not stream["closed"]:
                try:
                    token = await asyncio.wait_for(
                        stream["queue"].get(),
                        timeout=stream["timeout"]
                    )
                    stream["last_token_at"] = time.time()
                    yield token
                except asyncio.TimeoutError:
                    logger.warning(f"Stream {stream_id} timeout after {stream['timeout']}s")
                    break
        except GeneratorExit:
            logger.debug(f"Stream {stream_id} generator closed by client")
        finally:
            await self.close_stream(stream_id)
    
    async def push_token(self, stream_id: str, token: StreamToken) -> bool:
        """Push a token to a stream.
        
        Args:
            stream_id: The stream identifier
            token: The token to push
            
        Returns:
            True if token was queued, False if stream is closed or full
        """
        stream = self._streams.get(stream_id)
        if not stream or stream["closed"]:
            logger.debug(f"Cannot push to closed stream {stream_id}")
            return False
        
        async with self._locks[stream_id]:
            try:
                stream["queue"].put_nowait(token)
                stream["token_count"] += 1
                return True
            except asyncio.QueueFull:
                stream["backpressure_events"] += 1
                logger.warning(f"Backpressure on stream {stream_id}, waiting...")
                
                try:
                    await asyncio.wait_for(
                        stream["queue"].put(token),
                        timeout=1.0
                    )
                    stream["token_count"] += 1
                    return True
                except asyncio.TimeoutError:
                    logger.error(f"Failed to push token to {stream_id}: queue full")
                    await self.close_stream(stream_id)
                    return False
    
    async def close_stream(self, stream_id: str) -> None:
        """Close a stream and clean up resources.
        
        Args:
            stream_id: The stream identifier
        """
        stream = self._streams.get(stream_id)
        if not stream:
            return
        
        async with self._locks[stream_id]:
            stream["closed"] = True
            
            # Clear remaining items in queue
            while not stream["queue"].empty():
                try:
                    stream["queue"].get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            logger.debug(
                f"Closed stream {stream_id} after {stream['token_count']} tokens "
                f"({stream['backpressure_events']} backpressure events)"
            )
        
        # Schedule cleanup
        task = asyncio.create_task(self._cleanup_stream(stream_id))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)
    
    async def _cleanup_stream(self, stream_id: str) -> None:
        """Clean up a closed stream after a delay.
        
        Args:
            stream_id: The stream identifier
        """
        await asyncio.sleep(1.0)  # Allow final flushes
        
        if stream_id in self._streams:
            del self._streams[stream_id]
        if stream_id in self._locks:
            del self._locks[stream_id]
    
    async def stream_stats(self, stream_id: str) -> Optional[Dict]:
        """Get statistics for a stream.
        
        Args:
            stream_id: The stream identifier
            
        Returns:
            Dictionary of stream stats or None if stream doesn't exist
        """
        stream = self._streams.get(stream_id)
        if not stream:
            return None
        
        elapsed = time.time() - stream["created_at"]
        return {
            "stream_id": stream_id,
            "created_at": stream["created_at"],
            "elapsed_seconds": elapsed,
            "token_count": stream["token_count"],
            "tokens_per_second": stream["token_count"] / elapsed if elapsed > 0 else 0,
            "backpressure_events": stream["backpressure_events"],
            "queue_size": stream["queue"].qsize(),
            "is_closed": stream["closed"],
        }
    
    def active_streams(self) -> int:
        """Get count of active open streams.
        
        Returns:
            Number of open streams
        """
        return sum(1 for s in self._streams.values() if not s["closed"])
    
    async def cleanup_idle_streams(self, idle_timeout: float = 60.0) -> int:
        """Close streams that haven't received tokens in idle_timeout seconds.
        
        Args:
            idle_timeout: Timeout in seconds for idle streams
            
        Returns:
            Number of streams cleaned up
        """
        current_time = time.time()
        cleaned = 0
        
        for stream_id, stream in list(self._streams.items()):
            if not stream["closed"]:
                time_since_token = current_time - stream["last_token_at"]
                if time_since_token > idle_timeout:
                    logger.info(f"Cleaning up idle stream {stream_id} after {time_since_token:.1f}s")
                    await self.close_stream(stream_id)
                    cleaned += 1
        
        return cleaned
    
    async def shutdown(self) -> None:
        """Gracefully shutdown all streams."""
        logger.info(f"Shutting down StreamManager with {len(self._streams)} streams")
        
        for stream_id in list(self._streams.keys()):
            await self.close_stream(stream_id)
        
        # Wait for cleanup tasks
        if self._cleanup_tasks:
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
        
        logger.info("StreamManager shutdown complete")
