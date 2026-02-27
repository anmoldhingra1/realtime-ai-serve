"""Example: Set up server with a mock model and show streaming response."""

import asyncio
import logging
from typing import Any

from realtime_serve import (
    InferenceServer,
    ModelConfig,
    ServerConfig,
    StreamToken,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MockLanguageModel:
    """Mock language model for demonstration.
    
    Generates tokens by splitting the prompt into words and returning
    them incrementally. Useful for testing streaming infrastructure.
    """
    
    def __init__(self, config: ModelConfig):
        """Initialize mock model.
        
        Args:
            config: Model configuration
        """
        self.config = config
        self.vocab_size = 50000
        logger.info(f"Initialized MockLanguageModel: {config.name}")
    
    async def generate(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 1.0,
    ) -> list:
        """Generate tokens.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            List of tokens
        """
        # Simulate token generation by creating mock tokens
        words = [
            "The", "quick", "brown", "fox", "jumps", "over", "the",
            "lazy", "dog", "and", "continues", "on", "its", "way",
            "through", "the", "forest", "at", "a", "steady", "pace",
        ]
        
        tokens = []
        for i, word in enumerate(words[:max_tokens]):
            # Simulate some processing delay (would be actual GPU time)
            await asyncio.sleep(0.01)
            
            # Create token
            token = StreamToken(
                token=word,
                token_id=i + 100,
                logprob=-0.5,
                is_special=False,
            )
            tokens.append(token)
        
        return tokens


async def create_model_loader(config: ModelConfig) -> MockLanguageModel:
    """Factory function to create a mock model.
    
    Args:
        config: Model configuration
        
    Returns:
        Model instance
    """
    return MockLanguageModel(config)


async def main() -> None:
    """Run example server."""
    
    # Create server configuration
    server_config = ServerConfig(
        host="127.0.0.1",
        port=8000,
        max_connections=256,
        request_timeout=30.0,
        max_batch_size=32,
        max_batch_wait_ms=50,
        enable_metrics=True,
        log_level="INFO",
        rate_limit_per_minute=10000,
    )
    
    # Create server
    server = InferenceServer(config=server_config)
    
    # Register model with loader
    model_config = ModelConfig(
        name="gpt2",
        version="1.0.0",
        device="cpu",
        warmup_tokens=50,
    )
    server.register_model(model_config, loader=create_model_loader)
    
    logger.info("Starting inference server...")
    logger.info("Visit http://127.0.0.1:8000/health to check server status")
    logger.info("POST to http://127.0.0.1:8000/infer to make requests")
    
    try:
        await server.start(host=server_config.host, port=server_config.port)
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
