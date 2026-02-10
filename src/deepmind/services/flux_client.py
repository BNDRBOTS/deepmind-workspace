"""
FLUX.1 Image Generation Client using Together AI.
Generates images from text prompts using FLUX.1-schnell model.
"""
import os
import httpx
import base64
from typing import Optional, Dict
from pathlib import Path
import structlog

log = structlog.get_logger()


class FluxClient:
    """Client for FLUX.1 image generation via Together AI."""
    
    def __init__(self):
        self.api_key = os.getenv("TOGETHER_API_KEY")
        self.base_url = os.getenv("TOGETHER_BASE_URL", "https://api.together.xyz/v1")
        self.model = os.getenv("FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")
        self.client = httpx.AsyncClient(timeout=120.0)
        self._closed = False
        
        if not self.api_key:
            log.warning("flux_client_no_key", message="TOGETHER_API_KEY not set")
    
    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 768,
        steps: int = 4,  # FLUX.1-schnell optimized for 4 steps
        output_dir: Optional[Path] = None,
    ) -> Dict[str, any]:
        """
        Generate image from text prompt.
        
        Args:
            prompt: Text description of desired image
            width: Image width (default 1024)
            height: Image height (default 768)
            steps: Number of inference steps (4 for schnell)
            output_dir: Directory to save image (if None, returns base64)
            
        Returns:
            Dict with keys:
                - success: bool
                - image_url: str (local path if saved, or base64 data URL)
                - base64_data: str (base64 encoded image)
                - prompt: str (original prompt)
                - model: str (model used)
                - error: str (if failed)
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "TOGETHER_API_KEY not configured",
                "prompt": prompt,
            }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "n": 1,
            "response_format": "b64_json",
        }
        
        try:
            log.info("flux_generate_start", prompt=prompt[:100], model=self.model)
            
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
            
            # Save to file if output_dir provided
            image_path = None
            if output_dir:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate filename from prompt (sanitized)
                import hashlib
                import time
                filename = f"flux_{int(time.time())}_{hashlib.md5(prompt.encode()).hexdigest()[:8]}.png"
                image_path = output_dir / filename
                
                # Decode and save
                image_bytes = base64.b64decode(image_b64)
                image_path.write_bytes(image_bytes)
                
                log.info("flux_image_saved", path=str(image_path))
            
            log.info("flux_generate_success", prompt=prompt[:100])
            
            return {
                "success": True,
                "image_path": str(image_path) if image_path else None,
                "image_url": f"data:image/png;base64,{image_b64}",
                "base64_data": image_b64,
                "prompt": prompt,
                "model": self.model,
                "width": width,
                "height": height,
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
