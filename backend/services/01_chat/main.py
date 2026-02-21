from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import os
from supabase import create_client, Client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Chat Service",
    version="1.0.0",
    description="Real-time messaging and conversation management"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(url, key)

class Message(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    conversation_id: str
    user_id: str
    role: str = "user"

class Conversation(BaseModel):
    user_id: str
    title: Optional[str] = None

class MessageResponse(BaseModel):
    id: str
    content: str
    conversation_id: str
    user_id: str
    role: str
    created_at: datetime

@app.get("/health")
async def health():
    return {"status": "online", "service": "chat"}

@app.post("/conversations", status_code=201)
async def create_conversation(conversation: Conversation, supabase: Client = Depends(get_supabase)):
    try:
        data = {
            "user_id": conversation.user_id,
            "title": conversation.title or f"Conversation {datetime.utcnow().isoformat()}",
            "created_at": datetime.utcnow().isoformat()
        }
        result = supabase.table("conversations").insert(data).execute()
        return result.data[0] if result.data else {"error": "Failed to create conversation"}
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(500, str(e))

@app.get("/conversations/{user_id}")
async def get_conversations(user_id: str, limit: int = 50, supabase: Client = Depends(get_supabase)):
    try:
        result = supabase.table("conversations").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching conversations: {str(e)}")
        raise HTTPException(500, str(e))

@app.post("/messages", status_code=201)
async def send_message(message: Message, supabase: Client = Depends(get_supabase)):
    try:
        data = {
            "content": message.content,
            "conversation_id": message.conversation_id,
            "user_id": message.user_id,
            "role": message.role,
            "created_at": datetime.utcnow().isoformat()
        }
        result = supabase.table("messages").insert(data).execute()
        return result.data[0] if result.data else {"error": "Failed to send message"}
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        raise HTTPException(500, str(e))

@app.get("/messages/{conversation_id}")
async def get_messages(conversation_id: str, limit: int = 100, supabase: Client = Depends(get_supabase)):
    try:
        result = supabase.table("messages").select("*").eq("conversation_id", conversation_id).order("created_at", desc=False).limit(limit).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching messages: {str(e)}")
        raise HTTPException(500, str(e))

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, supabase: Client = Depends(get_supabase)):
    try:
        # Delete messages first (foreign key)
        supabase.table("messages").delete().eq("conversation_id", conversation_id).execute()
        # Then delete conversation
        result = supabase.table("conversations").delete().eq("id", conversation_id).execute()
        return {"status": "deleted", "conversation_id": conversation_id}
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        raise HTTPException(500, str(e))