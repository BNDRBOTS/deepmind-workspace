"""
Base connector interface — all document sources implement this.
To add a new connector (Slack, Notion, etc.):
1. Create a new file in this directory
2. Implement BaseConnector
3. Register in config/connectors.yaml
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ConnectorStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class DocumentInfo:
    """Metadata for a document from any connector."""
    id: str
    name: str
    path: str
    connector_type: str
    mime_type: str = ""
    size_bytes: int = 0
    last_modified: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FolderInfo:
    """Metadata for a folder/container from any connector."""
    id: str
    name: str
    path: str
    connector_type: str
    children_count: int = 0


class BaseConnector(ABC):
    """Interface that all document connectors must implement."""
    
    connector_type: str = ""
    display_name: str = ""
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection. Returns True on success."""
        ...
    
    @abstractmethod
    async def disconnect(self):
        """Clean up connection resources."""
        ...
    
    @abstractmethod
    async def get_status(self) -> ConnectorStatus:
        """Current connection status."""
        ...
    
    @abstractmethod
    async def browse(self, path: str = "") -> Dict:
        """
        Browse files/folders at a path.
        Returns: {"folders": [FolderInfo], "files": [DocumentInfo]}
        """
        ...
    
    @abstractmethod
    async def read_document(self, document_id: str) -> bytes:
        """Read full document content as bytes."""
        ...
    
    @abstractmethod
    async def search(self, query: str, **kwargs) -> List[DocumentInfo]:
        """Search documents matching query."""
        ...
    
    async def sync_to_vectors(self, document_id: str) -> int:
        """
        Process a document and store its chunks in ChromaDB.
        Returns number of chunks stored.
        """
        from deepmind.services.vector_store import get_vector_store
        from deepmind.services.document_processor import get_document_processor
        
        doc_info = await self._get_document_info(document_id)
        if not doc_info:
            return 0
        
        processor = get_document_processor()
        if not processor.is_supported(doc_info.name):
            return 0
        
        content = await self.read_document(document_id)
        text = processor.extract_text(content, doc_info.name, doc_info.mime_type)
        
        if not text.strip():
            return 0
        
        store = get_vector_store()
        collection_name = f"connector_{self.connector_type}"
        chunk_count = store.ingest_document(
            collection_name=collection_name,
            document_id=document_id,
            text=text,
            metadata={
                "connector": self.connector_type,
                "filename": doc_info.name,
                "path": doc_info.path,
                "mime_type": doc_info.mime_type,
            },
        )
        return chunk_count
    
    async def _get_document_info(self, document_id: str) -> Optional[DocumentInfo]:
        """Get document info — override in subclass if needed."""
        return None
