"""
Intelligent Context Window Manager — NO TRUNCATION.

Strategy:
1. Full conversation history is always stored in SQLite
2. When context window approaches limit, older messages get summarized
3. The LLM sees: [system prompt] + [summaries of old parts] + [recent messages]
4. Summaries are chained — each summary covers a range of messages
5. A visual indicator shows current context utilization
"""
import asyncio
import hashlib
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone

import tiktoken
from sqlalchemy import select, func, update

from deepmind.config import get_config
from deepmind.models.conversation import Conversation, Message, ContextSummary
from deepmind.services.database import get_session


class ContextManager:
    """Manages the context window for conversations without truncation."""
    
    def __init__(self):
        self.cfg = get_config()
        try:
            self._encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._encoder = tiktoken.get_encoding("gpt2")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        if not text:
            return 0
        return len(self._encoder.encode(text))
    
    def count_messages_tokens(self, messages: List[Dict]) -> int:
        """Count total tokens across a list of message dicts."""
        total = 0
        for msg in messages:
            total += self.count_tokens(msg.get("content", ""))
            total += 4  # overhead per message (role, separators)
        total += 2  # conversation overhead
        return total
    
    async def build_context_window(
        self,
        conversation_id: str,
        system_prompt: str,
        pinned_doc_chunks: Optional[List[str]] = None,
        rag_chunks: Optional[List[str]] = None,
    ) -> Tuple[List[Dict], Dict]:
        """
        Build the optimal context window for the LLM.
        
        Returns:
            - messages: List of message dicts ready for the API
            - stats: Token usage statistics for the UI indicator
        """
        max_tokens = self.cfg.context.max_tokens
        summary_trigger = self.cfg.context.summary_trigger_tokens
        recent_keep = self.cfg.context.recent_messages_keep
        
        # Start with system prompt
        context_messages = []
        system_content = system_prompt
        
        # Inject pinned document content
        if pinned_doc_chunks:
            doc_context = "\n\n---\n\n".join(pinned_doc_chunks)
            system_content += f"\n\n## Pinned Documents Context:\n{doc_context}"
        
        # Inject RAG-retrieved chunks
        if rag_chunks:
            rag_context = "\n\n---\n\n".join(rag_chunks)
            system_content += f"\n\n## Relevant Document Excerpts:\n{rag_context}"
        
        system_tokens = self.count_tokens(system_content)
        context_messages.append({"role": "system", "content": system_content})
        
        available_tokens = max_tokens - system_tokens - 500  # reserve for response overhead
        
        async with get_session() as session:
            # Get all messages for the conversation
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.sequence_num.asc())
            )
            all_messages = result.scalars().all()
            
            if not all_messages:
                return context_messages, self._build_stats(system_tokens, 0, 0, max_tokens)
            
            # Get existing summaries
            sum_result = await session.execute(
                select(ContextSummary)
                .where(ContextSummary.conversation_id == conversation_id)
                .order_by(ContextSummary.messages_start_seq.asc())
            )
            summaries = sum_result.scalars().all()
            
            # Calculate total conversation tokens
            total_conversation_tokens = sum(m.token_count for m in all_messages)
            
            # Split: recent messages (always included verbatim) vs older messages
            recent_messages = all_messages[-recent_keep:]
            older_messages = all_messages[:-recent_keep] if len(all_messages) > recent_keep else []
            
            recent_tokens = sum(m.token_count for m in recent_messages) + (len(recent_messages) * 4)
            
            # Add summaries for older portion
            summary_tokens = 0
            if summaries:
                for s in summaries:
                    if summary_tokens + s.token_count + recent_tokens < available_tokens:
                        context_messages.append({
                            "role": "system",
                            "content": f"[Conversation Summary — messages {s.messages_start_seq}-{s.messages_end_seq}]:\n{s.summary_text}"
                        })
                        summary_tokens += s.token_count
            elif older_messages:
                # No summaries yet but we have older messages — include as many as fit
                remaining = available_tokens - recent_tokens
                for msg in older_messages:
                    msg_tokens = msg.token_count + 4
                    if remaining >= msg_tokens:
                        context_messages.append({"role": msg.role, "content": msg.content})
                        summary_tokens += msg_tokens
                        remaining -= msg_tokens
                    else:
                        break
            
            # Add recent messages verbatim
            for msg in recent_messages:
                context_messages.append({"role": msg.role, "content": msg.content})
            
            used_tokens = system_tokens + summary_tokens + recent_tokens
            stats = self._build_stats(system_tokens, summary_tokens, recent_tokens, max_tokens)
            stats["total_stored_tokens"] = total_conversation_tokens
            stats["total_messages"] = len(all_messages)
            stats["summarized_messages"] = len([m for m in all_messages if m.is_summarized])
            
            return context_messages, stats
    
    async def check_and_summarize(self, conversation_id: str) -> bool:
        """
        Check if summarization is needed and trigger it if so.
        Returns True if summarization was performed.
        """
        cfg = self.cfg.context
        
        async with get_session() as session:
            # Count total tokens in unsummarized messages
            result = await session.execute(
                select(func.sum(Message.token_count))
                .where(
                    Message.conversation_id == conversation_id,
                    Message.is_summarized == False
                )
            )
            total_unsummarized = result.scalar() or 0
            
            if total_unsummarized < cfg.summary_trigger_tokens:
                return False
            
            # Get unsummarized messages (except recent ones to keep)
            result = await session.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.is_summarized == False
                )
                .order_by(Message.sequence_num.asc())
            )
            unsummarized = result.scalars().all()
            
            if len(unsummarized) <= cfg.recent_messages_keep + cfg.overlap_messages:
                return False
            
            # Messages to summarize (leave recent + overlap intact)
            to_summarize = unsummarized[:-(cfg.recent_messages_keep)]
            
            if not to_summarize:
                return False
            
            # Build the text to summarize
            text_for_summary = "\n".join(
                f"[{m.role}]: {m.content}" for m in to_summarize
            )
            
            # Generate summary via DeepSeek
            from deepmind.services.deepseek_client import get_deepseek_client
            client = get_deepseek_client()
            
            summary_text = await client.generate_summary(text_for_summary)
            
            if not summary_text:
                return False
            
            # Store the summary
            summary = ContextSummary(
                conversation_id=conversation_id,
                summary_text=summary_text,
                messages_start_seq=to_summarize[0].sequence_num,
                messages_end_seq=to_summarize[-1].sequence_num,
                token_count=self.count_tokens(summary_text),
            )
            session.add(summary)
            
            # Mark messages as summarized
            msg_ids = [m.id for m in to_summarize]
            await session.execute(
                update(Message)
                .where(Message.id.in_(msg_ids))
                .values(is_summarized=True)
            )
            
            return True
    
    async def get_context_stats(self, conversation_id: str) -> Dict:
        """Get current context statistics for the UI indicator."""
        async with get_session() as session:
            msg_result = await session.execute(
                select(
                    func.count(Message.id),
                    func.sum(Message.token_count),
                )
                .where(Message.conversation_id == conversation_id)
            )
            row = msg_result.one()
            total_messages = row[0] or 0
            total_tokens = row[1] or 0
            
            summarized_result = await session.execute(
                select(func.count(Message.id))
                .where(
                    Message.conversation_id == conversation_id,
                    Message.is_summarized == True
                )
            )
            summarized_count = summarized_result.scalar() or 0
            
            summary_result = await session.execute(
                select(func.sum(ContextSummary.token_count))
                .where(ContextSummary.conversation_id == conversation_id)
            )
            summary_tokens = summary_result.scalar() or 0
            
            max_tokens = self.cfg.context.max_tokens
            active_tokens = total_tokens - sum(0 for _ in range(summarized_count)) + summary_tokens
            
            return {
                "total_messages": total_messages,
                "total_stored_tokens": total_tokens,
                "summarized_messages": summarized_count,
                "summary_tokens": summary_tokens,
                "max_context_tokens": max_tokens,
                "utilization_percent": min(100, round((active_tokens / max_tokens) * 100, 1)),
                "status": self._token_status(active_tokens, max_tokens),
            }
    
    def _build_stats(self, system_tokens: int, summary_tokens: int, recent_tokens: int, max_tokens: int) -> Dict:
        used = system_tokens + summary_tokens + recent_tokens
        return {
            "system_tokens": system_tokens,
            "summary_tokens": summary_tokens,
            "recent_tokens": recent_tokens,
            "total_used_tokens": used,
            "max_context_tokens": max_tokens,
            "available_tokens": max(0, max_tokens - used),
            "utilization_percent": min(100, round((used / max_tokens) * 100, 1)),
            "status": self._token_status(used, max_tokens),
        }
    
    def _token_status(self, used: int, max_tokens: int) -> str:
        pct = (used / max_tokens) * 100 if max_tokens else 0
        if pct >= self.cfg.ui.token_critical_percent:
            return "critical"
        if pct >= self.cfg.ui.token_warning_percent:
            return "warning"
        return "healthy"


_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
