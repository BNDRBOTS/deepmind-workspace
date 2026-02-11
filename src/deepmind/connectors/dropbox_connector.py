"""
Dropbox Connector — Browse folders, read files via Dropbox SDK.
Uses OAuth refresh token flow for persistent access.
"""
from typing import Dict, List, Optional

import structlog

from deepmind.config import get_config
from deepmind.services.secrets_manager import get_secrets_manager
from deepmind.connectors.base import (
    BaseConnector, ConnectorStatus, DocumentInfo, FolderInfo
)

log = structlog.get_logger()


class DropboxConnector(BaseConnector):
    """Dropbox integration using the Dropbox Python SDK."""
    
    connector_type = "dropbox"
    display_name = "Dropbox"
    
    def __init__(self):
        self.cfg = get_config().connectors.dropbox
        self._dbx = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def connect(self) -> bool:
        try:
            import dropbox
            
            sm = get_secrets_manager()
            refresh_token = sm.get("DROPBOX_REFRESH_TOKEN", self.cfg.refresh_token)
            app_key = sm.get("DROPBOX_APP_KEY", self.cfg.app_key)
            app_secret = sm.get("DROPBOX_APP_SECRET", self.cfg.app_secret)
            
            if not refresh_token:
                self._status = ConnectorStatus.ERROR
                return False
            
            self._dbx = dropbox.Dropbox(
                oauth2_refresh_token=refresh_token,
                app_key=app_key,
                app_secret=app_secret,
            )
            account = self._dbx.users_get_current_account()
            self._status = ConnectorStatus.CONNECTED
            log.info("dropbox_connected", user=account.name.display_name)
            return True
        except Exception as e:
            log.error("dropbox_connect_error", error=str(e))
            self._status = ConnectorStatus.ERROR
            return False
    
    async def disconnect(self):
        self._dbx = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def get_status(self) -> ConnectorStatus:
        return self._status
    
    async def browse(self, path: str = "") -> Dict:
        if not self._dbx:
            return {"folders": [], "files": []}
        
        import dropbox
        
        folders = []
        docs = []
        browse_path = path or ""
        
        try:
            result = self._dbx.files_list_folder(browse_path)
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FolderMetadata):
                    folders.append(FolderInfo(
                        id=entry.id,
                        name=entry.name,
                        path=entry.path_display,
                        connector_type=self.connector_type,
                    ))
                elif isinstance(entry, dropbox.files.FileMetadata):
                    docs.append(DocumentInfo(
                        id=entry.id,
                        name=entry.name,
                        path=entry.path_display,
                        connector_type=self.connector_type,
                        size_bytes=entry.size,
                        last_modified=entry.server_modified.isoformat() if entry.server_modified else "",
                    ))
        except Exception as e:
            log.error("dropbox_browse_error", path=path, error=str(e))
        
        return {"folders": folders, "files": docs}
    
    async def read_document(self, document_id: str) -> bytes:
        if not self._dbx:
            return b""
        try:
            _, response = self._dbx.files_download(document_id)
            return response.content
        except Exception as e:
            log.error("dropbox_read_error", doc_id=document_id, error=str(e))
            return b""
    
    async def search(self, query: str, **kwargs) -> List[DocumentInfo]:
        if not self._dbx:
            return []
        
        results = []
        try:
            search_result = self._dbx.files_search_v2(query)
            for match in search_result.matches[:20]:
                metadata = match.metadata.get_metadata()
                if hasattr(metadata, "name"):
                    results.append(DocumentInfo(
                        id=metadata.id if hasattr(metadata, "id") else metadata.path_display,
                        name=metadata.name,
                        path=metadata.path_display,
                        connector_type=self.connector_type,
                        size_bytes=metadata.size if hasattr(metadata, "size") else 0,
                    ))
        except Exception as e:
            log.error("dropbox_search_error", query=query, error=str(e))
        
        return results
    
    async def _get_document_info(self, document_id: str) -> Optional[DocumentInfo]:
        if not self._dbx:
            return None
        try:
            metadata = self._dbx.files_get_metadata(document_id)
            return DocumentInfo(
                id=document_id,
                name=metadata.name,
                path=metadata.path_display,
                connector_type=self.connector_type,
                size_bytes=metadata.size if hasattr(metadata, "size") else 0,
            )
        except Exception:
            return None
