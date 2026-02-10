"""OpenAI GPT-4o client for streaming chat responses."""
from typing import AsyncGenerator, Optional
import httpx
import structlog

from deepmind.config import get_config

log = structlog.get_logger()


class OpenAIClient:
    """Client for OpenAI GPT-4o API with streaming support."""
    
    def __init__(self):
        cfg = get_config()
        
        self.api_key = cfg.openai.api_key
        self.base_url = cfg.openai.base_url
        self.model = cfg.openai.model
        self.client = httpx.AsyncClient(timeout=120.0)
        self._closed = False
        
        if not self.api_key:
            log.warning("openai_client_no_key", message="OPENAI_API_KEY not set")
    
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Stream GPT-4o chat completion response.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            
        Yields:
            Content chunks from the streaming response
        """
        if not self.api_key:
            log.error("openai_stream_no_key")
            yield "[ERROR: OPENAI_API_KEY not configured]"
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            import json
                            data = json.loads(data_str)
                            
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            log.error("openai_stream_parse_error", error=str(e))
                            continue
        
        except httpx.HTTPStatusError as e:
            log.error("openai_http_error", status=e.response.status_code, detail=str(e))
            yield f"[ERROR: OpenAI API returned {e.response.status_code}]"
        except Exception as e:
            log.error("openai_stream_error", error=str(e))
            yield f"[ERROR: {str(e)}]"
    
    async def close(self):
        """Close the HTTP client."""
        if not self._closed:
            await self.client.aclose()
            self._closed = True
            log.info("openai_client_closed")


# Singleton instance
_client: Optional[OpenAIClient] = None


def get_openai_client() -> OpenAIClient:
    """Get the singleton OpenAI client instance."""
    global _client
    if _client is None:
        _client = OpenAIClient()
    return _client
