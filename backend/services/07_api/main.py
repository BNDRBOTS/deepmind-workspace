from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, AsyncGenerator
import os
import logging
import httpx
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="API Service",
    version="1.0.0",
    description="DeepSeek R1 API integration and model routing"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    model: str = "deepseek-reasoner"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=4000, ge=1, le=8000)
    stream: bool = False

class ChatResponse(BaseModel):
    id: str
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]
    created: int

@app.get("/health")
async def health():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    return {
        "status": "online",
        "service": "api",
        "deepseek_configured": bool(api_key),
        "available_models": ["deepseek-reasoner", "deepseek-chat"]
    }

@app.get("/models")
async def list_models():
    return {
        "models": [
            {
                "id": "deepseek-reasoner",
                "name": "DeepSeek R1",
                "description": "Advanced reasoning model",
                "max_tokens": 8000
            },
            {
                "id": "deepseek-chat",
                "name": "DeepSeek Chat",
                "description": "Fast conversational model",
                "max_tokens": 4000
            }
        ]
    }

async def call_deepseek_api(request: ChatRequest) -> Dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(500, "DEEPSEEK_API_KEY not configured")
    
    api_url = "https://api.deepseek.com/v1/chat/completions"
    
    payload = {
        "model": request.model,
        "messages": [msg.dict() for msg in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": request.stream
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek API error: {e.response.status_code} - {e.response.text}")
            raise HTTPException(e.response.status_code, f"DeepSeek API error: {e.response.text}")
        except Exception as e:
            logger.error(f"Error calling DeepSeek: {str(e)}")
            raise HTTPException(500, f"API error: {str(e)}")

async def stream_deepseek_api(request: ChatRequest) -> AsyncGenerator[str, None]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(500, "DEEPSEEK_API_KEY not configured")
    
    api_url = "https://api.deepseek.com/v1/chat/completions"
    
    payload = {
        "model": request.model,
        "messages": [msg.dict() for msg in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "stream": True
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream("POST", api_url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            yield f"data: {data}\n\n"
        except httpx.HTTPStatusError as e:
            logger.error(f"DeepSeek streaming error: {e.response.status_code}")
            error_data = {"error": f"API error: {e.response.status_code}"}
            yield f"data: {json.dumps(error_data)}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            error_data = {"error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

@app.post("/chat/completions")
async def chat_completions(request: ChatRequest):
    logger.info(f"Chat request: model={request.model}, messages={len(request.messages)}, stream={request.stream}")
    
    if request.stream:
        return StreamingResponse(
            stream_deepseek_api(request),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        response = await call_deepseek_api(request)
        return response

@app.post("/reasoning")
async def reasoning_task(request: ChatRequest):
    """Specialized endpoint for reasoning tasks with DeepSeek R1"""
    request.model = "deepseek-reasoner"
    request.temperature = 0.3  # Lower temperature for reasoning
    
    logger.info(f"Reasoning task: {len(request.messages)} messages")
    
    response = await call_deepseek_api(request)
    return response

@app.get("/usage/{user_id}")
async def get_usage_stats(user_id: str):
    """Placeholder for usage tracking - integrate with your database"""
    return {
        "user_id": user_id,
        "requests_today": 0,
        "tokens_used_today": 0,
        "last_request": None
    }