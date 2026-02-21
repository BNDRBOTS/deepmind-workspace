from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import logging
from pinecone import Pinecone, ServerlessSpec
import httpx
from datetime import datetime
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Memory Service",
    version="1.0.0",
    description="Vector-based memory storage with Pinecone"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pinecone client
def get_pinecone():
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY must be set")
    return Pinecone(api_key=api_key)

INDEX_NAME = "bndr-memory"
DIMENSION = 1536  # OpenAI ada-002 dimension

class MemoryStore(BaseModel):
    content: str = Field(..., min_length=1)
    user_id: str
    metadata: Optional[Dict[str, Any]] = None

class MemoryQuery(BaseModel):
    query: str
    user_id: str
    top_k: int = Field(default=5, ge=1, le=20)

@app.on_event("startup")
async def startup_event():
    try:
        pc = get_pinecone()
        existing_indexes = [index.name for index in pc.list_indexes()]
        
        if INDEX_NAME not in existing_indexes:
            logger.info(f"Creating Pinecone index: {INDEX_NAME}")
            pc.create_index(
                name=INDEX_NAME,
                dimension=DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            logger.info(f"Index {INDEX_NAME} created successfully")
        else:
            logger.info(f"Index {INDEX_NAME} already exists")
    except Exception as e:
        logger.error(f"Error initializing Pinecone: {str(e)}")

@app.get("/health")
async def health():
    try:
        pc = get_pinecone()
        indexes = [index.name for index in pc.list_indexes()]
        return {
            "status": "online",
            "service": "memory",
            "pinecone_connected": True,
            "index": INDEX_NAME,
            "available_indexes": indexes
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "memory",
            "pinecone_connected": False,
            "error": str(e)
        }

async def get_embedding(text: str) -> List[float]:
    """Get embedding from OpenAI API"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY must be set")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": text, "model": "text-embedding-ada-002"},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Error getting embedding: {str(e)}")
            raise HTTPException(500, f"Embedding error: {str(e)}")

@app.post("/store", status_code=201)
async def store_memory(memory: MemoryStore):
    try:
        pc = get_pinecone()
        index = pc.Index(INDEX_NAME)
        
        # Generate embedding
        embedding = await get_embedding(memory.content)
        
        # Generate unique ID
        memory_id = hashlib.sha256(f"{memory.user_id}_{memory.content}_{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
        
        # Prepare metadata
        metadata = memory.metadata or {}
        metadata.update({
            "user_id": memory.user_id,
            "content": memory.content[:1000],  # Pinecone metadata limit
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Upsert to Pinecone
        index.upsert(vectors=[{
            "id": memory_id,
            "values": embedding,
            "metadata": metadata
        }])
        
        logger.info(f"Stored memory {memory_id} for user {memory.user_id}")
        return {"memory_id": memory_id, "status": "stored"}
    
    except Exception as e:
        logger.error(f"Error storing memory: {str(e)}")
        raise HTTPException(500, str(e))

@app.post("/query")
async def query_memory(query: MemoryQuery):
    try:
        pc = get_pinecone()
        index = pc.Index(INDEX_NAME)
        
        # Generate query embedding
        query_embedding = await get_embedding(query.query)
        
        # Query Pinecone with user_id filter
        results = index.query(
            vector=query_embedding,
            top_k=query.top_k,
            filter={"user_id": query.user_id},
            include_metadata=True
        )
        
        memories = []
        for match in results.matches:
            memories.append({
                "id": match.id,
                "score": match.score,
                "content": match.metadata.get("content", ""),
                "timestamp": match.metadata.get("timestamp", ""),
                "metadata": {k: v for k, v in match.metadata.items() if k not in ["user_id", "content", "timestamp"]}
            })
        
        logger.info(f"Retrieved {len(memories)} memories for user {query.user_id}")
        return {"memories": memories, "count": len(memories)}
    
    except Exception as e:
        logger.error(f"Error querying memory: {str(e)}")
        raise HTTPException(500, str(e))

@app.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, user_id: str):
    try:
        pc = get_pinecone()
        index = pc.Index(INDEX_NAME)
        
        # Delete from Pinecone
        index.delete(ids=[memory_id], filter={"user_id": user_id})
        
        logger.info(f"Deleted memory {memory_id} for user {user_id}")
        return {"status": "deleted", "memory_id": memory_id}
    
    except Exception as e:
        logger.error(f"Error deleting memory: {str(e)}")
        raise HTTPException(500, str(e))

@app.get("/stats/{user_id}")
async def get_memory_stats(user_id: str):
    try:
        pc = get_pinecone()
        index = pc.Index(INDEX_NAME)
        
        stats = index.describe_index_stats()
        
        return {
            "user_id": user_id,
            "total_vectors": stats.total_vector_count,
            "dimension": stats.dimension,
            "index_fullness": stats.index_fullness
        }
    
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(500, str(e))