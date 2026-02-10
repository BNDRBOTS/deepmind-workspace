"""
FastAPI API routes — Backend endpoints for conversation, connectors, and context.
The NiceGUI frontend calls these internally via httpx or directly.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from deepmind.services.conversation_service import get_conversation_service
from deepmind.services.context_manager import get_context_manager
from deepmind.services.vector_store import get_vector_store
from deepmind.services.code_executor import get_code_executor
from deepmind.services.flux_client import get_flux_client
from deepmind.connectors.registry import get_connector_registry


router = APIRouter(prefix="/api", tags=["api"])


# ---- Conversation Endpoints ----

class CreateConversationRequest(BaseModel):
    title: str = "New Conversation"


class SendMessageRequest(BaseModel):
    content: str


class PinDocumentRequest(BaseModel):
    document_id: str
    source_connector: str
    document_name: str
    document_path: str = ""


@router.get("/conversations")
async def list_conversations(include_archived: bool = False):
    svc = get_conversation_service()
    return await svc.list_conversations(include_archived=include_archived)


@router.post("/conversations")
async def create_conversation(req: CreateConversationRequest):
    svc = get_conversation_service()
    return await svc.create_conversation(title=req.title)


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    svc = get_conversation_service()
    return await svc.get_conversation_messages(conversation_id)


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, req: SendMessageRequest):
    svc = get_conversation_service()
    response_text = await svc.send_message_sync(conversation_id, req.content)
    return {"content": response_text}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    svc = get_conversation_service()
    await svc.delete_conversation(conversation_id)
    return {"status": "deleted"}


# ---- Context Endpoints ----

@router.get("/conversations/{conversation_id}/context")
async def get_context_stats(conversation_id: str):
    ctx = get_context_manager()
    return await ctx.get_context_stats(conversation_id)


# ---- Document Pin Endpoints ----

@router.post("/conversations/{conversation_id}/pins")
async def pin_document(conversation_id: str, req: PinDocumentRequest):
    svc = get_conversation_service()
    return await svc.pin_document(
        conversation_id=conversation_id,
        document_id=req.document_id,
        source_connector=req.source_connector,
        document_name=req.document_name,
        document_path=req.document_path,
    )


@router.delete("/pins/{pin_id}")
async def unpin_document(pin_id: str):
    svc = get_conversation_service()
    await svc.unpin_document(pin_id)
    return {"status": "unpinned"}


# ---- Code Execution Endpoint ----

class ExecuteCodeRequest(BaseModel):
    code: str
    timeout: Optional[int] = None


@router.post("/execute-code")
async def execute_code(req: ExecuteCodeRequest):
    """
    Execute Python code in RestrictedPython sandbox.
    
    Args:
        code: Python code to execute
        timeout: Optional timeout override (seconds)
        
    Returns:
        Execution result with stdout, stderr, success status
    """
    executor = get_code_executor()
    result = executor.execute(req.code, timeout_override=req.timeout)
    return result


# ---- Image Generation Endpoint ----

class GenerateImageRequest(BaseModel):
    prompt: str
    model: Optional[str] = None  # ultra/pro/dev/schnell
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None


@router.post("/generate-image")
async def generate_image(req: GenerateImageRequest):
    """
    Generate image using FLUX models via Together AI.
    
    Args:
        prompt: Text description of desired image
        model: Model to use (ultra/pro/dev/schnell) - defaults to 'pro'
        width: Image width (uses model default if None)
        height: Image height (uses model default if None)
        steps: Inference steps (uses model default if None)
        
    Returns:
        Generation result with image_path, image_url, base64_data, metadata
    """
    flux = get_flux_client()
    result = await flux.generate_image(
        prompt=req.prompt,
        model=req.model,
        width=req.width,
        height=req.height,
        steps=req.steps,
    )
    return result


# ---- Connector Endpoints ----

@router.get("/connectors/status")
async def connector_status():
    registry = get_connector_registry()
    return await registry.get_all_status()


@router.post("/connectors/{connector_name}/connect")
async def connect_connector(connector_name: str):
    registry = get_connector_registry()
    connector = registry.get(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector {connector_name} not found")
    ok = await connector.connect()
    return {"connected": ok}


@router.get("/connectors/{connector_name}/browse")
async def browse_connector(connector_name: str, path: str = ""):
    registry = get_connector_registry()
    connector = registry.get(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector {connector_name} not found")
    result = await connector.browse(path)
    # Convert dataclass objects to dicts
    return {
        "folders": [f.__dict__ for f in result.get("folders", [])],
        "files": [d.__dict__ for d in result.get("files", [])],
    }


@router.get("/connectors/{connector_name}/search")
async def search_connector(connector_name: str, q: str = Query(...)):
    registry = get_connector_registry()
    connector = registry.get(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector {connector_name} not found")
    results = await connector.search(q)
    return [d.__dict__ for d in results]


@router.post("/connectors/{connector_name}/sync/{document_id:path}")
async def sync_document(connector_name: str, document_id: str):
    registry = get_connector_registry()
    connector = registry.get(connector_name)
    if not connector:
        raise HTTPException(404, f"Connector {connector_name} not found")
    chunk_count = await connector.sync_to_vectors(document_id)
    return {"document_id": document_id, "chunks_created": chunk_count}


# ---- Google Drive OAuth ----

@router.get("/connectors/google/auth")
async def google_auth_url():
    registry = get_connector_registry()
    connector = registry.get("google_drive")
    if not connector or not hasattr(connector, "get_oauth_url"):
        raise HTTPException(400, "Google Drive connector not available")
    url = connector.get_oauth_url()
    return {"auth_url": url}


@router.get("/connectors/google/callback")
async def google_callback(code: str = Query(...)):
    registry = get_connector_registry()
    connector = registry.get("google_drive")
    if not connector or not hasattr(connector, "handle_oauth_callback"):
        raise HTTPException(400, "Google Drive connector not available")
    ok = await connector.handle_oauth_callback(code)
    if ok:
        return RedirectResponse("/?google_auth=success")
    raise HTTPException(400, "OAuth failed")


# ---- Vector Store ----

@router.get("/vectors/stats")
async def vector_stats():
    store = get_vector_store()
    collections = ["connector_github", "connector_dropbox", "connector_google_drive"]
    stats = {}
    for name in collections:
        stats[name] = store.get_collection_stats(name)
    return stats


@router.post("/vectors/query")
async def vector_query(collection: str = "connector_github", q: str = Query(...), n: int = 5):
    store = get_vector_store()
    results = store.query(collection_name=collection, query_text=q, n_results=n)
    return results
