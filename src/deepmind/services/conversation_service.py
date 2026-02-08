"""
Conversation Service — orchestrates chat, context, vector retrieval, and streaming.
"""
import uuid
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime, timezone

from sqlalchemy import select, update, func

from deepmind.config import get_config
from deepmind.models.conversation import Conversation, Message, PinnedDocument, TokenUsageLog
from deepmind.services.database import get_session
from deepmind.services.context_manager import get_context_manager
from deepmind.services.deepseek_client import get_deepseek_client
from deepmind.services.vector_store import get_vector_store


SYSTEM_PROMPT = """You are DeepMind Workspace, an advanced AI assistant with persistent memory and document integration.

Key capabilities:
- Full conversation history is maintained — nothing is ever lost
- Documents from GitHub, Dropbox, and Google Drive can be referenced
- You can search through pinned and indexed documents for relevant context
- You provide detailed, accurate, and well-structured responses

Guidelines:
- Reference specific documents when they are relevant to the question
- Be thorough but concise — quality over verbosity
- When discussing code, provide complete implementations
- If you're unsure about something, say so clearly
- Use markdown formatting for readability"""


class ConversationService:
    """Orchestrates the full chat pipeline."""
    
    def __init__(self):
        self.ctx = get_context_manager()
        self.llm = get_deepseek_client()
        self.vectors = get_vector_store()
        self.cfg = get_config()
    
    async def list_conversations(self, include_archived: bool = False) -> List[Dict]:
        """List all conversations, newest first."""
        async with get_session() as session:
            query = select(Conversation).order_by(Conversation.updated_at.desc())
            if not include_archived:
                query = query.where(Conversation.is_archived == False)
            result = await session.execute(query)
            convos = result.scalars().all()
            return [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                    "total_tokens": c.total_tokens_used,
                    "is_archived": c.is_archived,
                }
                for c in convos
            ]
    
    async def create_conversation(self, title: str = "New Conversation") -> Dict:
        """Create a new conversation."""
        async with get_session() as session:
            conv = Conversation(title=title)
            session.add(conv)
            await session.flush()
            return {"id": conv.id, "title": conv.title}
    
    async def get_conversation_messages(self, conversation_id: str) -> List[Dict]:
        """Get all messages for a conversation (full history, no truncation)."""
        async with get_session() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.sequence_num.asc())
            )
            messages = result.scalars().all()
            return [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "sequence_num": m.sequence_num,
                    "token_count": m.token_count,
                    "model_used": m.model_used,
                    "created_at": m.created_at.isoformat(),
                    "is_summarized": m.is_summarized,
                }
                for m in messages
            ]
    
    async def send_message(
        self,
        conversation_id: str,
        user_content: str,
    ) -> AsyncGenerator[str, None]:
        """
        Send a user message and stream the assistant response.
        Yields content deltas for real-time UI updates.
        """
        # Store user message
        user_msg = await self._store_message(conversation_id, "user", user_content)
        
        # Get pinned document chunks
        pinned_chunks = await self._get_pinned_chunks(conversation_id)
        
        # RAG: query vector store for relevant chunks
        rag_chunks = self._get_rag_chunks(user_content)
        
        # Check for dev-scaffold trigger (Google Drive search)
        scaffold_query = await self.llm.analyze_for_dev_scaffold(user_content)
        if scaffold_query:
            scaffold_chunks = self._get_scaffold_chunks(scaffold_query)
            if scaffold_chunks:
                rag_chunks.extend(scaffold_chunks)
        
        # Build context window (summaries + recent messages)
        context_messages, stats = await self.ctx.build_context_window(
            conversation_id=conversation_id,
            system_prompt=SYSTEM_PROMPT,
            pinned_doc_chunks=pinned_chunks,
            rag_chunks=[c["text"] for c in rag_chunks] if rag_chunks else None,
        )
        
        # Stream response from DeepSeek
        full_response = ""
        async for delta in self.llm.chat_completion_stream(messages=context_messages):
            full_response += delta
            yield delta
        
        # Store assistant message
        assistant_msg = await self._store_message(
            conversation_id, "assistant", full_response,
            model_used=self.cfg.deepseek.chat_model,
        )
        
        # Update conversation metadata
        async with get_session() as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(
                    updated_at=datetime.now(timezone.utc),
                    total_tokens_used=Conversation.total_tokens_used
                        + user_msg["token_count"]
                        + assistant_msg["token_count"],
                )
            )
        
        # Auto-title if this is the first exchange
        await self._auto_title(conversation_id, user_content)
        
        # Check if summarization is needed
        await self.ctx.check_and_summarize(conversation_id)
    
    async def send_message_sync(self, conversation_id: str, user_content: str) -> str:
        """Non-streaming variant — returns full response."""
        full = ""
        async for delta in self.send_message(conversation_id, user_content):
            full += delta
        return full
    
    async def _store_message(
        self, conversation_id: str, role: str, content: str,
        model_used: Optional[str] = None,
    ) -> Dict:
        """Store a message and return its metadata."""
        token_count = self.ctx.count_tokens(content)
        
        async with get_session() as session:
            # Get next sequence number
            result = await session.execute(
                select(func.max(Message.sequence_num))
                .where(Message.conversation_id == conversation_id)
            )
            max_seq = result.scalar() or 0
            
            msg = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                sequence_num=max_seq + 1,
                token_count=token_count,
                model_used=model_used,
            )
            session.add(msg)
            await session.flush()
            
            return {
                "id": msg.id,
                "role": role,
                "content": content,
                "sequence_num": msg.sequence_num,
                "token_count": token_count,
            }
    
    async def _get_pinned_chunks(self, conversation_id: str) -> List[str]:
        """Get text chunks from pinned documents."""
        async with get_session() as session:
            result = await session.execute(
                select(PinnedDocument)
                .where(
                    PinnedDocument.conversation_id == conversation_id,
                    PinnedDocument.is_active == True,
                )
            )
            pins = result.scalars().all()
        
        chunks = []
        for pin in pins:
            collection_name = f"connector_{pin.source_connector}"
            results = self.vectors.query(
                collection_name=collection_name,
                query_text=pin.document_name,
                n_results=4,
                where={"source_id": pin.document_id},
            )
            for r in results:
                chunks.append(f"[{pin.document_name}]: {r['text']}")
        
        return chunks[:12]  # Cap at 12 chunks to avoid flooding context
    
    def _get_rag_chunks(self, query: str) -> List[Dict]:
        """Search across all connector collections for relevant content."""
        all_results = []
        for collection_name in ["connector_github", "connector_dropbox", "connector_google_drive"]:
            try:
                results = self.vectors.query(
                    collection_name=collection_name,
                    query_text=query,
                )
                all_results.extend(results)
            except Exception:
                continue
        
        # Sort by relevance, take top results
        all_results.sort(key=lambda x: x["relevance"], reverse=True)
        return all_results[:self.cfg.embeddings.max_results]
    
    def _get_scaffold_chunks(self, query: str) -> List[Dict]:
        """Dev-scaffold: search Google Drive for technical resources."""
        try:
            return self.vectors.query(
                collection_name="connector_google_drive",
                query_text=query,
                n_results=4,
            )
        except Exception:
            return []
    
    async def _auto_title(self, conversation_id: str, first_message: str):
        """Auto-generate conversation title from the first user message."""
        async with get_session() as session:
            result = await session.execute(
                select(func.count(Message.id))
                .where(Message.conversation_id == conversation_id)
            )
            count = result.scalar()
            if count > 2:
                return
            
            # Generate title
            title = first_message[:80].strip()
            if len(first_message) > 80:
                title = title.rsplit(" ", 1)[0] + "..."
            
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(title=title)
            )
    
    async def pin_document(
        self, conversation_id: str, document_id: str,
        source_connector: str, document_name: str, document_path: str = "",
    ) -> Dict:
        """Pin a document to the current conversation context."""
        async with get_session() as session:
            pin = PinnedDocument(
                conversation_id=conversation_id,
                document_id=document_id,
                source_connector=source_connector,
                document_name=document_name,
                document_path=document_path,
            )
            session.add(pin)
            await session.flush()
            return {"id": pin.id, "document_name": document_name}
    
    async def unpin_document(self, pin_id: str):
        """Unpin a document from the conversation."""
        async with get_session() as session:
            await session.execute(
                update(PinnedDocument)
                .where(PinnedDocument.id == pin_id)
                .values(is_active=False)
            )
    
    async def delete_conversation(self, conversation_id: str):
        """Delete a conversation and all its data."""
        async with get_session() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                await session.delete(conv)


_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    global _service
    if _service is None:
        _service = ConversationService()
    return _service
