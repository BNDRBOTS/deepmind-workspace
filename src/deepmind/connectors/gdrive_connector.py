"""
Google Drive Connector — Browse, read, search with dual-purpose architecture:
1. User Knowledge Base: Retrieve and answer from stored documents
2. Dev Scaffold: Auto-search for technical resources during feature discussions

Uses Google API Python client with OAuth2 flow.
"""
from typing import Dict, List, Optional, Any
import io

import structlog

from deepmind.config import get_config
from deepmind.connectors.base import (
    BaseConnector, ConnectorStatus, DocumentInfo, FolderInfo
)

log = structlog.get_logger()


class GoogleDriveConnector(BaseConnector):
    """
    Google Drive integration with dual-purpose search architecture.
    
    Purpose 1 — User Knowledge Base:
      Standard document retrieval. User asks a question, system searches
      their Drive for relevant docs and provides context to the LLM.
    
    Purpose 2 — Dev Scaffold:
      When the conversation includes trigger phrases like "how to implement"
      or "documentation for", the system autonomously searches the user's
      Drive for technical resources (framework docs, code snippets, specs)
      to inform suggestions WITHOUT expanding scope.
    """
    
    connector_type = "google_drive"
    display_name = "Google Drive"
    
    def __init__(self):
        self.cfg = get_config().connectors.google_drive
        self._service = None
        self._credentials = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def connect(self) -> bool:
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            
            if not self.cfg.client_id or not self.cfg.client_secret:
                self._status = ConnectorStatus.ERROR
                return False
            
            # In production, credentials come from the OAuth callback flow
            # For initial setup, we check for stored credentials
            self._credentials = self._load_credentials()
            if not self._credentials:
                self._status = ConnectorStatus.DISCONNECTED
                return False
            
            self._service = build("drive", "v3", credentials=self._credentials)
            
            # Verify
            about = self._service.about().get(fields="user").execute()
            user_email = about.get("user", {}).get("emailAddress", "unknown")
            
            self._status = ConnectorStatus.CONNECTED
            log.info("gdrive_connected", user=user_email)
            return True
        except Exception as e:
            log.error("gdrive_connect_error", error=str(e))
            self._status = ConnectorStatus.ERROR
            return False
    
    async def disconnect(self):
        self._service = None
        self._credentials = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def get_status(self) -> ConnectorStatus:
        return self._status
    
    async def browse(self, path: str = "") -> Dict:
        """Browse Drive folders. path = folder_id or empty for root."""
        if not self._service:
            return {"folders": [], "files": []}
        
        folder_id = path or "root"
        folders = []
        docs = []
        
        try:
            query = f"'{folder_id}' in parents and trashed = false"
            results = self._service.files().list(
                q=query,
                pageSize=100,
                fields="files(id, name, mimeType, size, modifiedTime, parents)",
                orderBy="folder,name",
            ).execute()
            
            for item in results.get("files", []):
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    folders.append(FolderInfo(
                        id=item["id"],
                        name=item["name"],
                        path=item["id"],
                        connector_type=self.connector_type,
                    ))
                else:
                    docs.append(DocumentInfo(
                        id=item["id"],
                        name=item["name"],
                        path=item["id"],
                        connector_type=self.connector_type,
                        mime_type=item.get("mimeType", ""),
                        size_bytes=int(item.get("size", 0)),
                        last_modified=item.get("modifiedTime", ""),
                    ))
        except Exception as e:
            log.error("gdrive_browse_error", path=path, error=str(e))
        
        return {"folders": folders, "files": docs}
    
    async def read_document(self, document_id: str) -> bytes:
        """Read document content from Drive."""
        if not self._service:
            return b""
        
        try:
            # Get file metadata to check type
            file_meta = self._service.files().get(
                fileId=document_id, fields="mimeType,name"
            ).execute()
            mime = file_meta.get("mimeType", "")
            
            # Google Docs need to be exported
            if mime.startswith("application/vnd.google-apps."):
                export_mime = self._get_export_mime(mime)
                if not export_mime:
                    return b""
                request = self._service.files().export_media(
                    fileId=document_id, mimeType=export_mime
                )
            else:
                request = self._service.files().get_media(fileId=document_id)
            
            from googleapiclient.http import MediaIoBaseDownload
            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            return buffer.getvalue()
        except Exception as e:
            log.error("gdrive_read_error", doc_id=document_id, error=str(e))
            return b""
    
    async def search(self, query: str, **kwargs) -> List[DocumentInfo]:
        """
        Standard knowledge-base search across user's Drive.
        """
        if not self._service:
            return []
        
        results = []
        try:
            q = f"fullText contains '{query}' and trashed = false"
            
            # Filter by mime types if specified
            file_types = kwargs.get("file_types")
            if file_types:
                mime_filters = " or ".join(f"mimeType='{mt}'" for mt in file_types)
                q += f" and ({mime_filters})"
            
            response = self._service.files().list(
                q=q,
                pageSize=20,
                fields="files(id, name, mimeType, size, modifiedTime)",
                orderBy="modifiedTime desc",
            ).execute()
            
            for item in response.get("files", []):
                results.append(DocumentInfo(
                    id=item["id"],
                    name=item["name"],
                    path=item["id"],
                    connector_type=self.connector_type,
                    mime_type=item.get("mimeType", ""),
                    size_bytes=int(item.get("size", 0)),
                    last_modified=item.get("modifiedTime", ""),
                ))
        except Exception as e:
            log.error("gdrive_search_error", query=query, error=str(e))
        
        return results
    
    async def dev_scaffold_search(self, topic: str) -> List[DocumentInfo]:
        """
        Dev Scaffold search — finds technical resources in Drive
        relevant to the current development discussion.
        
        Triggered by conversational context (e.g., "how to implement X").
        Results inform suggestions WITHOUT expanding project scope.
        """
        scaffold_cfg = self.cfg.dev_scaffold
        if not scaffold_cfg.enabled:
            return []
        
        return await self.search(
            query=topic,
            file_types=scaffold_cfg.file_types,
        )
    
    def get_oauth_url(self) -> str:
        """Generate OAuth authorization URL for user consent."""
        from google_auth_oauthlib.flow import Flow
        
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.cfg.client_id,
                    "client_secret": self.cfg.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.cfg.redirect_uri],
                }
            },
            scopes=self.cfg.scopes,
        )
        flow.redirect_uri = self.cfg.redirect_uri
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url
    
    async def handle_oauth_callback(self, code: str) -> bool:
        """Handle OAuth callback, store credentials."""
        try:
            from google_auth_oauthlib.flow import Flow
            
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.cfg.client_id,
                        "client_secret": self.cfg.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.cfg.redirect_uri],
                    }
                },
                scopes=self.cfg.scopes,
            )
            flow.redirect_uri = self.cfg.redirect_uri
            flow.fetch_token(code=code)
            
            self._credentials = flow.credentials
            self._save_credentials(flow.credentials)
            
            return await self.connect()
        except Exception as e:
            log.error("gdrive_oauth_error", error=str(e))
            return False
    
    def _load_credentials(self):
        """Load stored OAuth credentials."""
        import json
        from pathlib import Path
        from google.oauth2.credentials import Credentials
        
        cred_path = Path("data/gdrive_credentials.json")
        if not cred_path.exists():
            return None
        
        try:
            cred_data = json.loads(cred_path.read_text())
            creds = Credentials.from_authorized_user_info(cred_data)
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                self._save_credentials(creds)
            return creds
        except Exception as e:
            log.warning("gdrive_cred_load_error", error=str(e))
            return None
    
    def _save_credentials(self, credentials):
        """Persist OAuth credentials."""
        import json
        from pathlib import Path
        
        cred_path = Path("data/gdrive_credentials.json")
        cred_path.parent.mkdir(parents=True, exist_ok=True)
        
        cred_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else [],
        }
        cred_path.write_text(json.dumps(cred_data, indent=2))
    
    def _get_export_mime(self, google_mime: str) -> Optional[str]:
        """Map Google Docs MIME types to export formats."""
        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }
        return export_map.get(google_mime)
    
    async def _get_document_info(self, document_id: str) -> Optional[DocumentInfo]:
        if not self._service:
            return None
        try:
            meta = self._service.files().get(
                fileId=document_id,
                fields="id,name,mimeType,size,modifiedTime",
            ).execute()
            return DocumentInfo(
                id=meta["id"],
                name=meta["name"],
                path=meta["id"],
                connector_type=self.connector_type,
                mime_type=meta.get("mimeType", ""),
                size_bytes=int(meta.get("size", 0)),
            )
        except Exception:
            return None
