"""SQLAlchemy models for conversation persistence."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, 
    ForeignKey, JSON, Index, event
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, default="New Conversation")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    is_archived = Column(Boolean, default=False)
    total_tokens_used = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    
    messages = relationship("Message", back_populates="conversation",
                           order_by="Message.sequence_num", cascade="all, delete-orphan")
    summaries = relationship("ContextSummary", back_populates="conversation",
                            cascade="all, delete-orphan")
    pinned_docs = relationship("PinnedDocument", back_populates="conversation",
                              cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_conv_updated", "updated_at"),
        Index("idx_conv_archived", "is_archived"),
    )


class Message(Base):
    __tablename__ = "messages"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    sequence_num = Column(Integer, nullable=False)
    token_count = Column(Integer, default=0)
    model_used = Column(String(100))
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_summarized = Column(Boolean, default=False)
    metadata_json = Column(JSON, default=dict)
    
    conversation = relationship("Conversation", back_populates="messages")
    
    __table_args__ = (
        Index("idx_msg_conv_seq", "conversation_id", "sequence_num"),
        Index("idx_msg_conv_role", "conversation_id", "role"),
        Index("idx_msg_summarized", "conversation_id", "is_summarized"),
    )


class ContextSummary(Base):
    __tablename__ = "context_summaries"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    summary_text = Column(Text, nullable=False)
    messages_start_seq = Column(Integer, nullable=False)
    messages_end_seq = Column(Integer, nullable=False)
    token_count = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    conversation = relationship("Conversation", back_populates="summaries")
    
    __table_args__ = (
        Index("idx_summary_conv", "conversation_id", "messages_start_seq"),
    )


class PinnedDocument(Base):
    __tablename__ = "pinned_documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(500), nullable=False)
    source_connector = Column(String(50), nullable=False)
    document_name = Column(String(500), nullable=False)
    document_path = Column(String(2000))
    pinned_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    
    conversation = relationship("Conversation", back_populates="pinned_docs")
    
    __table_args__ = (
        Index("idx_pin_conv_active", "conversation_id", "is_active"),
    )


class TokenUsageLog(Base):
    __tablename__ = "token_usage_log"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), nullable=False)
    message_id = Column(String(36))
    model = Column(String(100), nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_estimate_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (
        Index("idx_usage_conv", "conversation_id"),
        Index("idx_usage_created", "created_at"),
    )


class ConnectorDocument(Base):
    __tablename__ = "connector_documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    connector_type = Column(String(50), nullable=False)
    external_id = Column(String(1000), nullable=False)
    name = Column(String(500), nullable=False)
    path = Column(String(2000))
    mime_type = Column(String(200))
    size_bytes = Column(Integer)
    content_hash = Column(String(128))
    last_synced_at = Column(DateTime)
    last_modified_at = Column(DateTime)
    chromadb_collection = Column(String(200))
    chunk_count = Column(Integer, default=0)
    metadata_json = Column(JSON, default=dict)
    
    __table_args__ = (
        Index("idx_cdoc_connector", "connector_type"),
        Index("idx_cdoc_ext", "connector_type", "external_id", unique=True),
    )
