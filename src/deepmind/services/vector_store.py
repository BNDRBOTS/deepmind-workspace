"""
ChromaDB Vector Store — Document embedding, storage, and retrieval.
Handles chunking, embedding, and semantic search across all document sources.
"""
import hashlib
import re
from typing import List, Dict, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings
import structlog

from deepmind.config import get_config

log = structlog.get_logger()


class VectorStore:
    """Manages ChromaDB collections for document vector storage."""
    
    def __init__(self):
        self.cfg = get_config()
        self._client: Optional[chromadb.PersistentClient] = None
        self._embedding_fn = None
    
    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self.cfg.database.chromadb_path,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
        return self._client
    
    @property
    def embedding_fn(self):
        if self._embedding_fn is None:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            self._embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=self.cfg.embeddings.model
            )
        return self._embedding_fn
    
    def get_collection(self, name: str):
        """Get or create a ChromaDB collection."""
        return self.client.get_or_create_collection(
            name=name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
    
    def chunk_text(self, text: str, source_id: str = "") -> List[Dict]:
        """Split text into overlapping chunks for embedding."""
        chunk_size = self.cfg.embeddings.chunk_size
        chunk_overlap = self.cfg.embeddings.chunk_overlap
        
        # Clean text
        text = re.sub(r"\n{3,}", "\n\n", text.strip())
        
        if len(text) <= chunk_size:
            return [{
                "id": hashlib.sha256(f"{source_id}:0:{text[:100]}".encode()).hexdigest()[:32],
                "text": text,
                "metadata": {"source_id": source_id, "chunk_index": 0, "total_chunks": 1},
            }]
        
        chunks = []
        start = 0
        idx = 0
        while start < len(text):
            end = start + chunk_size
            
            # Try to break at paragraph or sentence boundary
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind("\n\n", start + chunk_size // 2, end)
                if para_break > start:
                    end = para_break + 2
                else:
                    # Look for sentence break
                    sent_break = max(
                        text.rfind(". ", start + chunk_size // 2, end),
                        text.rfind("\n", start + chunk_size // 2, end),
                    )
                    if sent_break > start:
                        end = sent_break + 1
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunk_id = hashlib.sha256(
                    f"{source_id}:{idx}:{chunk_text[:100]}".encode()
                ).hexdigest()[:32]
                chunks.append({
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": {"source_id": source_id, "chunk_index": idx},
                })
                idx += 1
            
            start = end - chunk_overlap
        
        # Set total_chunks
        for c in chunks:
            c["metadata"]["total_chunks"] = len(chunks)
        
        return chunks
    
    def ingest_document(
        self,
        collection_name: str,
        document_id: str,
        text: str,
        metadata: Optional[Dict] = None,
    ) -> int:
        """Chunk and embed a document into a collection. Returns chunk count."""
        collection = self.get_collection(collection_name)
        chunks = self.chunk_text(text, source_id=document_id)
        
        if not chunks:
            return 0
        
        base_meta = metadata or {}
        
        # Batch upsert
        batch_size = self.cfg.embeddings.batch_size
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            ids = [c["id"] for c in batch]
            documents = [c["text"] for c in batch]
            metadatas = [{**base_meta, **c["metadata"]} for c in batch]
            
            collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        
        return len(chunks)
    
    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: Optional[int] = None,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """Query a collection for relevant documents."""
        n = n_results or self.cfg.embeddings.max_results
        collection = self.get_collection(collection_name)
        
        try:
            results = collection.query(
                query_texts=[query_text],
                n_results=min(n, collection.count() or 1),
                where=where,
            )
        except Exception as e:
            log.warning("vector_query_error", error=str(e))
            return []
        
        if not results or not results.get("documents"):
            return []
        
        output = []
        for i, doc in enumerate(results["documents"][0]):
            distance = results["distances"][0][i] if results.get("distances") else 1.0
            relevance = 1.0 - distance  # cosine distance to similarity
            
            if relevance < self.cfg.embeddings.relevance_threshold:
                continue
            
            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
            output.append({
                "text": doc,
                "relevance": round(relevance, 4),
                "metadata": meta,
                "id": results["ids"][0][i] if results.get("ids") else "",
            })
        
        return sorted(output, key=lambda x: x["relevance"], reverse=True)
    
    def delete_document(self, collection_name: str, document_id: str):
        """Delete all chunks for a document from a collection."""
        collection = self.get_collection(collection_name)
        try:
            collection.delete(where={"source_id": document_id})
        except Exception as e:
            log.warning("vector_delete_error", error=str(e), doc_id=document_id)
    
    def get_collection_stats(self, collection_name: str) -> Dict:
        """Get statistics for a collection."""
        try:
            collection = self.get_collection(collection_name)
            return {
                "name": collection_name,
                "count": collection.count(),
            }
        except Exception:
            return {"name": collection_name, "count": 0}


_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
