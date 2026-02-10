"""
FLUX Image Generation Client using Together AI.
Supports multiple FLUX models including unfiltered pro/ultra variants.
Inline ChatGPT-style rendering with disk storage.
"""
import os
import httpx
import base64
import hashlib
import time
from typing import Optional, Dict, Literal
from pathlib import Path
import structlog

from deepmind.config import get_config

log = structlog.get_logger()

ModelType = Literal["ultra", "pro", "dev", "schnell"]


class FluxClient:
    """
    Client for FLUX image generation via Together AI.
    
    Supported models:
    - ultra: FLUX.1-pro-ultra (2048x2048, unfiltered, highest quality)
    - pro: FLUX.1-pro (1440x1440, unfiltered, high quality) **DEFAULT**
    - dev: FLUX.1-dev (1024x1024, unfiltered, good quality)
    - schnell: FLUX.1-schnell (1024x768, filtered, fast preview)
    """
    
    def __init__(self):
        cfg = get_config()
        
        self.api_key = cfg.image_generation.api_key
        self.base_url = cfg.image_generation.base_url
        self.models = cfg.image_generation.models
        self.default_model = cfg.image_generation.default_model
        self.timeout = cfg.image_generation.timeout_seconds
        self.output_dir = Path(cfg.image_generation.output_dir)
        self.save_to_disk = cfg.image_generation.save_to_disk
        
        self.client = httpx.AsyncClient(timeout=self.timeout)
        self._closed = False
        
        # Ensure output directory exists
        if self.save_to_disk:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.api_key:
            log.warning("flux_client_no_key", message="TOGETHER_API_KEY not set")
    
    async def generate_image(
        self,
        prompt: str,
        model: ModelType = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        steps: Optional[int] = None,
    ) -> Dict[str, any]:
        """
        Generate image from text prompt.
        
        Args:
            prompt: Text description of desired image
            model: Model to use (ultra/pro/dev/schnell) - defaults to 'pro'
            width: Image width (uses model default if None)
            height: Image height (uses model default if None)
            steps: Inference steps (uses model default if None)
            
        Returns:
            Dict with keys:
                - success: bool
                - image_path: str (local file path for inline display)
                - image_url: str (file:// URL for rendering)
                - prompt: str (original prompt)
                - model: str (model used)
                - width: int
                - height: int
                - unfiltered: bool (whether model is unfiltered)
                - error: str (if failed)
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "TOGETHER_API_KEY not configured",
                "prompt": prompt,
            }
        
        # Select model
        model_key = model or self.default_model
        model_config = getattr(self.models, model_key)
        
        model_name = model_config.name
        width = width or model_config.max_width
        height = height or model_config.max_height
        steps = steps or model_config.steps
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "n": 1,
            "response_format": "b64_json",
        }
        
        try:
            log.info(
                "flux_generate_start",
                prompt=prompt[:100],
                model=model_key,
                unfiltered=model_config.unfiltered,
            )
            
            response = await self.client.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            
            data = response.json()
            
            if "data" not in data or len(data["data"]) == 0:
                raise ValueError("No image data in response")
            
            image_b64 = data["data"][0]["b64_json"]
            image_bytes = base64.b64decode(image_b64)
            
            # Generate unique filename
            timestamp = int(time.time())
            prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
            filename = f"flux_{model_key}_{timestamp}_{prompt_hash}.png"
            
            # Save to disk for inline display
            image_path = None
            image_url = None
            
            if self.save_to_disk:
                image_path = self.output_dir / filename
                image_path.write_bytes(image_bytes)
                
                # Create file:// URL for NiceGUI rendering
                image_url = f"file://{image_path.absolute()}"
                
                log.info(
                    "flux_image_saved",
                    path=str(image_path),
                    size_kb=len(image_bytes) / 1024,
                )
            
            log.info(
                "flux_generate_success",
                prompt=prompt[:100],
                model=model_key,
                unfiltered=model_config.unfiltered,
            )
            
            return {
                "success": True,
                "image_path": str(image_path) if image_path else None,
                "image_url": image_url,
                "base64_data": image_b64,  # Fallback for display
                "prompt": prompt,
                "model": model_key,
                "model_name": model_name,
                "width": width,
                "height": height,
                "unfiltered": model_config.unfiltered,
                "cost_estimate": model_config.cost_per_image,
            }
        
        except httpx.HTTPStatusError as e:
            error_msg = f"Together AI API error: {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg += f" - {error_detail.get('error', {}).get('message', '')}"
            except:
                pass
            
            log.error("flux_http_error", error=error_msg)
            return {
                "success": False,
                "error": error_msg,
                "prompt": prompt,
            }
        
        except Exception as e:
            log.error("flux_generate_error", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "prompt": prompt,
            }
    
    async def close(self):
        """Close the HTTP client."""
        if not self._closed:
            await self.client.aclose()
            self._closed = True
            log.info("flux_client_closed")


# Singleton instance
_client: Optional[FluxClient] = None


def get_flux_client() -> FluxClient:
    """Get the singleton FLUX client instance."""
    global _client
    if _client is None:
        _client = FluxClient()
    return _client
