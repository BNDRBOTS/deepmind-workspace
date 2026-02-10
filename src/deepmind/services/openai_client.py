"""OpenAI GPT-4o client for streaming chat."""
import os
import json
from typing import AsyncGenerator
import httpx
import structlog

log = structlog.get_logger()


class OpenAIClient:
    """OpenAI API client with streaming support."""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            log.warning("openai_api_key_missing")
        
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.client = httpx.AsyncClient(timeout=180.0)
    
    async def stream_chat(
        self, 
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> AsyncGenerator[str, None]:
        """Stream GPT-4o response token by token."""
        if not self.api_key:
            log.error("openai_stream_failed", reason="missing_api_key")
            yield "Error: OpenAI API key not configured"
            return
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and len(data["choices"]) > 0:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue
        
        except httpx.HTTPStatusError as e:
            log.error("openai_http_error", status=e.response.status_code, detail=e.response.text)
            yield f"\n\nError: OpenAI API returned {e.response.status_code}"
        except Exception as e:
            log.error("openai_stream_error", error=str(e))
            yield f"\n\nError: {str(e)}"
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


_client = None


def get_openai_client() -> OpenAIClient:
    """Singleton OpenAI client."""
    global _client
    if _client is None:
        _client = OpenAIClient()
    return _client
