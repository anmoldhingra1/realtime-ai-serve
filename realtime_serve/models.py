"""Model registry and lifecycle management."""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from realtime_serve.types import ModelConfig


logger = logging.getLogger(__name__)


class Model:
    """Wrapper for a loaded model with metadata."""
    
    def __init__(self, config: ModelConfig, model_obj: Any):
        """Initialize Model wrapper.
        
        Args:
            config: Model configuration
            model_obj: The actual model object
        """
        self.config = config
        self.model = model_obj
        self.loaded_at = time.time()
        self.inference_count = 0
        self.total_tokens_generated = 0
        self.last_used_at = time.time()
        self.health_check_passed = True
    
    def record_inference(self, tokens_generated: int) -> None:
        """Record an inference execution.
        
        Args:
            tokens_generated: Number of tokens generated
        """
        self.inference_count += 1
        self.total_tokens_generated += tokens_generated
        self.last_used_at = time.time()
    
    def uptime_seconds(self) -> float:
        """Get model uptime in seconds.
        
        Returns:
            Seconds since model was loaded
        """
        return time.time() - self.loaded_at


class ModelRegistry:
    """Manages model lifecycle including registration, unregistration, and hot-swapping.
    
    Supports loading new model versions while old versions continue serving traffic.
    Includes health monitoring and warm-up inference.
    """
    
    def __init__(self):
        """Initialize ModelRegistry."""
        self._models: Dict[str, Dict[str, Model]] = {}  # model_name -> {version: Model}
        self._active_versions: Dict[str, str] = {}  # model_name -> active_version
        self._lock = asyncio.Lock()
        self._model_loaders: Dict[str, Callable] = {}  # model_name -> loader_func
    
    def register_loader(self, model_name: str, loader: Callable[[ModelConfig], Any]) -> None:
        """Register a model loader function.
        
        Args:
            model_name: Name of the model family
            loader: Async or sync callable that loads a model given config
        """
        self._model_loaders[model_name] = loader
        logger.info(f"Registered loader for model {model_name}")
    
    async def load_model(self, config: ModelConfig) -> None:
        """Load a model and register it.
        
        Args:
            config: Model configuration
            
        Raises:
            ValueError: If no loader is registered for this model
            RuntimeError: If model loading fails
        """
        if config.name not in self._model_loaders:
            raise ValueError(f"No loader registered for model {config.name}")
        
        async with self._lock:
            logger.info(f"Loading model {config.name} v{config.version}")
            
            try:
                loader = self._model_loaders[config.name]
                
                # Call loader (handle both async and sync)
                if asyncio.iscoroutinefunction(loader):
                    model_obj = await loader(config)
                else:
                    model_obj = await asyncio.to_thread(loader, config)
                
                # Wrap in Model
                model = Model(config, model_obj)
                
                # Perform warm-up inference
                if config.warmup_tokens > 0:
                    await self._warmup_model(model, config.warmup_tokens)
                
                # Store model
                if config.name not in self._models:
                    self._models[config.name] = {}
                
                self._models[config.name][config.version] = model
                self._active_versions[config.name] = config.version
                
                logger.info(
                    f"Successfully loaded {config.name} v{config.version} "
                    f"(device={config.device})"
                )
            
            except Exception as e:
                logger.error(f"Failed to load model {config.name}: {e}")
                raise RuntimeError(f"Model loading failed: {e}") from e
    
    async def _warmup_model(self, model: Model, num_tokens: int) -> None:
        """Perform warm-up inference on a model.
        
        Args:
            model: Model to warm up
            num_tokens: Number of tokens to generate in warm-up
        """
        logger.debug(f"Warming up model with {num_tokens} tokens")
        
        try:
            # Simulate warmup by calling a generate method if available
            if hasattr(model.model, 'generate'):
                await asyncio.to_thread(
                    model.model.generate,
                    "Warmup",  # dummy input
                    max_tokens=min(num_tokens, 10)
                )
            elif hasattr(model.model, 'inference'):
                await asyncio.to_thread(
                    model.model.inference,
                    "Warmup",
                    max_tokens=min(num_tokens, 10)
                )
            
            logger.debug("Model warmup complete")
        except Exception as e:
            logger.warning(f"Model warmup failed (non-fatal): {e}")
    
    async def unload_model(self, model_name: str, version: Optional[str] = None) -> None:
        """Unload a model version.
        
        Args:
            model_name: Name of the model
            version: Version to unload (if None, unload all versions)
        """
        async with self._lock:
            if model_name not in self._models:
                logger.warning(f"Model {model_name} not found")
                return
            
            if version:
                if version in self._models[model_name]:
                    model = self._models[model_name][version]
                    
                    # Cleanup model if it has a cleanup method
                    if hasattr(model.model, 'cleanup'):
                        try:
                            if asyncio.iscoroutinefunction(model.model.cleanup):
                                await model.model.cleanup()
                            else:
                                await asyncio.to_thread(model.model.cleanup)
                        except Exception as e:
                            logger.warning(f"Error during model cleanup: {e}")
                    
                    del self._models[model_name][version]
                    
                    # Update active version if needed
                    if self._active_versions.get(model_name) == version:
                        remaining = list(self._models[model_name].keys())
                        self._active_versions[model_name] = remaining[0] if remaining else None
                    
                    logger.info(f"Unloaded {model_name} v{version}")
            else:
                # Unload all versions
                for version in list(self._models[model_name].keys()):
                    await self.unload_model(model_name, version)
    
    def get_model(self, model_name: str, version: Optional[str] = None) -> Optional[Model]:
        """Get a loaded model.
        
        Args:
            model_name: Name of the model
            version: Specific version (if None, get active version)
            
        Returns:
            Model object or None if not found
        """
        if model_name not in self._models:
            return None
        
        if version is None:
            version = self._active_versions.get(model_name)
        
        if version is None:
            return None
        
        return self._models[model_name].get(version)
    
    def list_models(self) -> Dict[str, List[str]]:
        """List all loaded models and their versions.
        
        Returns:
            Dictionary mapping model names to list of versions
        """
        return {
            name: list(versions.keys())
            for name, versions in self._models.items()
        }
    
    def set_active_version(self, model_name: str, version: str) -> bool:
        """Switch to a different model version.
        
        Args:
            model_name: Name of the model
            version: Version to activate
            
        Returns:
            True if successful, False otherwise
        """
        if model_name not in self._models or version not in self._models[model_name]:
            logger.error(f"Version {version} not found for model {model_name}")
            return False
        
        old_version = self._active_versions.get(model_name)
        self._active_versions[model_name] = version
        logger.info(f"Switched {model_name} from v{old_version} to v{version}")
        return True
    
    async def health_check(self, model_name: str) -> bool:
        """Check health of a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            True if model is healthy
        """
        model = self.get_model(model_name)
        if not model:
            return False
        
        try:
            if hasattr(model.model, 'health_check'):
                if asyncio.iscoroutinefunction(model.model.health_check):
                    result = await model.model.health_check()
                else:
                    result = await asyncio.to_thread(model.model.health_check)
                
                model.health_check_passed = bool(result)
                return model.health_check_passed
            
            return True  # Assume healthy if no health check method
        except Exception as e:
            logger.error(f"Health check failed for {model_name}: {e}")
            model.health_check_passed = False
            return False
    
    def model_stats(self, model_name: str) -> Dict:
        """Get statistics for a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Dictionary of statistics
        """
        model = self.get_model(model_name)
        if not model:
            return {}
        
        return {
            "name": model_name,
            "version": model.config.version,
            "device": model.config.device,
            "uptime_seconds": model.uptime_seconds(),
            "inference_count": model.inference_count,
            "total_tokens_generated": model.total_tokens_generated,
            "tokens_per_inference": (
                model.total_tokens_generated / model.inference_count
                if model.inference_count > 0 else 0
            ),
            "healthy": model.health_check_passed,
        }
    
    async def shutdown(self) -> None:
        """Shutdown the registry and cleanup all models."""
        logger.info("Shutting down ModelRegistry")
        
        async with self._lock:
            for model_name in list(self._models.keys()):
                await self.unload_model(model_name)
        
        logger.info("ModelRegistry shutdown complete")
