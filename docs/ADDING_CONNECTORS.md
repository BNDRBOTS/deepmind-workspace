# Adding New Document Connectors

This guide explains how to add a new document source (e.g., Notion, Slack, S3)
to DeepMind Workspace.

## Architecture

All connectors implement `BaseConnector` from `src/deepmind/connectors/base.py`.
The system auto-discovers connectors via `config/connectors.yaml`.

## Step-by-Step

### 1. Create the connector module

Create a new file: `src/deepmind/connectors/notion_connector.py`

```python
"""Notion Connector — Browse pages, read content via Notion API."""
from typing import Dict, List, Optional
from deepmind.connectors.base import (
    BaseConnector, ConnectorStatus, DocumentInfo, FolderInfo
)


class NotionConnector(BaseConnector):
    """Notion integration using the Notion API."""
    
    connector_type = "notion"
    display_name = "Notion"
    
    def __init__(self):
        from deepmind.config import get_config
        # Load config (add notion section to app.yaml connectors)
        self._status = ConnectorStatus.DISCONNECTED
        self._client = None
    
    async def connect(self) -> bool:
        # Initialize Notion client
        ...
        self._status = ConnectorStatus.CONNECTED
        return True
    
    async def disconnect(self):
        self._client = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def get_status(self) -> ConnectorStatus:
        return self._status
    
    async def browse(self, path: str = "") -> Dict:
        # Browse Notion pages/databases
        return {"folders": [], "files": []}
    
    async def read_document(self, document_id: str) -> bytes:
        # Read a Notion page as text
        return b""
    
    async def search(self, query: str, **kwargs) -> List[DocumentInfo]:
        # Search Notion workspace
        return []
```

### 2. Register in connectors.yaml

Add to `config/connectors.yaml`:

```yaml
  notion:
    module: "deepmind.connectors.notion_connector"
    class: "NotionConnector"
    display_name: "Notion"
    icon: "mdi-notion"
    color: "#000000"
    config_ref: "connectors.notion"
    capabilities:
      - "browse_pages"
      - "read_page"
      - "search_workspace"
```

### 3. Add config section in app.yaml

```yaml
  notion:
    enabled: true
    token: "${NOTION_TOKEN}"
    workspace_id: "${NOTION_WORKSPACE_ID}"
    sync_interval_minutes: 15
```

### 4. Add config dataclass (optional but recommended)

In `src/deepmind/config.py`, add a `NotionConfig` dataclass and include it
in `ConnectorsConfig`.

### 5. Restart

The connector registry auto-discovers and instantiates the new connector
on startup. It will appear in the sidebar Connectors panel.

## Document Processing

When a document is synced (`sync_to_vectors`), the base class handles:
1. Reading content via `read_document()`
2. Text extraction via `DocumentProcessor`
3. Chunking and embedding into ChromaDB

The collection name is `connector_{connector_type}` (e.g., `connector_notion`).

## API Endpoints

All connectors automatically get these REST endpoints:
- `GET /api/connectors/{name}/browse?path=...`
- `GET /api/connectors/{name}/search?q=...`
- `POST /api/connectors/{name}/sync/{document_id}`
- `POST /api/connectors/{name}/connect`
