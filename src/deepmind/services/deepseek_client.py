"""
DeepSeek API Client — Handles chat completions, streaming, summarization.
OpenAI-compatible endpoint. Multimodal-ready architecture.
"""
import json
import asyncio
from typing import AsyncGenerator, Dict, List, Optional, Callable

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
import structlog

from deepmind.config import get_config

log = structlog.get_logger()


class DeepSeekClient:
    """Async client for the DeepSeek API."""
    
    def __init__(self):
        self.cfg = get_config().deepseek
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.cfg.base_url,
                headers={
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.cfg.timeout_seconds, connect=10.0),
            )
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(multiplier=1.0, max=10.0),
        reraise=True,
    )
    async def chat_completion(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Dict:
        """Non-streaming chat completion."""
        payload = {
            "model": model or self.cfg.chat_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "top_p": self.cfg.top_p,
            "stream": False,
        }
        
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        
        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data.get("model", payload["model"]),
            "usage": data.get("usage", {}),
            "finish_reason": data["choices"][0].get("finish_reason"),
        }
    
    async def chat_completion_stream(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        on_token: Optional[Callable[[str], None]] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion — yields content deltas."""
        payload = {
            "model": model or self.cfg.chat_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "top_p": self.cfg.top_p,
            "stream": True,
        }
        
        full_content = ""
        usage_data = {}
        
        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                chunk = line[len("data: "):]
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content += content
                        if on_token:
                            on_token(content)
                        yield content
                    if "usage" in obj:
                        usage_data = obj["usage"]
                except json.JSONDecodeError:
                    continue
    
    async def generate_summary(self, conversation_text: str) -> str:
        """Generate a concise summary of conversation history."""
        summary_prompt = [
            {
                "role": "system",
                "content": (
                    "You are a conversation summarizer. Create a concise but comprehensive "
                    "summary of the following conversation. Preserve key facts, decisions, "
                    "code snippets, URLs, names, and action items. The summary will be used "
                    "to maintain context in a long-running conversation. Be thorough but compact."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize this conversation segment:\n\n{conversation_text}",
            },
        ]
        
        result = await self.chat_completion(
            messages=summary_prompt,
            model=get_config().context.summarization_model,
            max_tokens=get_config().context.summarization_max_tokens,
            temperature=0.3,
        )
        return result.get("content", "")
    
    async def analyze_for_dev_scaffold(self, user_message: str) -> Optional[str]:
        """
        Detect if a user message warrants a dev-scaffold search in Google Drive.
        Returns a search query if triggered, None otherwise.
        """
        triggers = get_config().connectors.google_drive.dev_scaffold.search_triggers
        msg_lower = user_message.lower()
        
        for trigger in triggers:
            if trigger in msg_lower:
                # Extract the topic after the trigger phrase
                idx = msg_lower.index(trigger) + len(trigger)
                topic = user_message[idx:].strip().rstrip("?.,!")
                if topic:
                    return topic
        
        return None


_client: Optional[DeepSeekClient] = None


def get_deepseek_client() -> DeepSeekClient:
    global _client
    if _client is None:
        _client = DeepSeekClient()
    return _client
