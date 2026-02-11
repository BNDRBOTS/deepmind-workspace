"""
GitHub Connector — Browse repos, read files, search code via PyGithub.
First-priority connector per spec.
"""
import base64
from typing import Dict, List, Optional

from github import Github, GithubException
import structlog

from deepmind.config import get_config
from deepmind.services.secrets_manager import get_secrets_manager
from deepmind.connectors.base import (
    BaseConnector, ConnectorStatus, DocumentInfo, FolderInfo
)

log = structlog.get_logger()


class GitHubConnector(BaseConnector):
    """GitHub integration using PyGithub."""
    
    connector_type = "github"
    display_name = "GitHub"
    
    def __init__(self):
        self.cfg = get_config().connectors.github
        self._github: Optional[Github] = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def connect(self) -> bool:
        try:
            token = get_secrets_manager().get("GITHUB_TOKEN", self.cfg.token)
            if not token:
                self._status = ConnectorStatus.ERROR
                return False
            self._github = Github(token)
            # Verify connection
            user = self._github.get_user()
            _ = user.login
            self._status = ConnectorStatus.CONNECTED
            log.info("github_connected", user=user.login)
            return True
        except GithubException as e:
            log.error("github_connect_error", error=str(e))
            self._status = ConnectorStatus.ERROR
            return False
    
    async def disconnect(self):
        if self._github:
            self._github.close()
            self._github = None
        self._status = ConnectorStatus.DISCONNECTED
    
    async def get_status(self) -> ConnectorStatus:
        return self._status
    
    async def browse(self, path: str = "") -> Dict:
        """
        Browse GitHub. Path format:
        - "" → list user repos
        - "owner/repo" → list repo root
        - "owner/repo/path/to/dir" → list directory
        """
        if not self._github:
            return {"folders": [], "files": []}
        
        folders = []
        docs = []
        
        try:
            if not path:
                # List repos
                repos = self._github.get_user().get_repos(sort="updated")
                for repo in repos[:50]:
                    folders.append(FolderInfo(
                        id=repo.full_name,
                        name=repo.full_name,
                        path=repo.full_name,
                        connector_type=self.connector_type,
                        children_count=0,
                    ))
            else:
                parts = path.split("/", 2)
                if len(parts) < 2:
                    return {"folders": [], "files": []}
                
                repo_name = f"{parts[0]}/{parts[1]}"
                repo = self._github.get_repo(repo_name)
                repo_path = parts[2] if len(parts) > 2 else ""
                
                contents = repo.get_contents(repo_path)
                if not isinstance(contents, list):
                    contents = [contents]
                
                for item in contents:
                    if item.type == "dir":
                        folders.append(FolderInfo(
                            id=f"{repo_name}/{item.path}",
                            name=item.name,
                            path=f"{repo_name}/{item.path}",
                            connector_type=self.connector_type,
                        ))
                    else:
                        docs.append(DocumentInfo(
                            id=f"{repo_name}/{item.path}",
                            name=item.name,
                            path=f"{repo_name}/{item.path}",
                            connector_type=self.connector_type,
                            mime_type=self._guess_mime(item.name),
                            size_bytes=item.size or 0,
                        ))
        except GithubException as e:
            log.error("github_browse_error", path=path, error=str(e))
        
        return {"folders": folders, "files": docs}
    
    async def read_document(self, document_id: str) -> bytes:
        """Read a file from GitHub. document_id = 'owner/repo/path/to/file'."""
        if not self._github:
            return b""
        
        try:
            parts = document_id.split("/", 2)
            repo_name = f"{parts[0]}/{parts[1]}"
            file_path = parts[2] if len(parts) > 2 else ""
            
            repo = self._github.get_repo(repo_name)
            content = repo.get_contents(file_path)
            
            if isinstance(content, list):
                return b""
            
            if content.encoding == "base64" and content.content:
                return base64.b64decode(content.content)
            
            return (content.decoded_content or b"")
        except GithubException as e:
            log.error("github_read_error", doc_id=document_id, error=str(e))
            return b""
    
    async def search(self, query: str, **kwargs) -> List[DocumentInfo]:
        """Search code across repos."""
        if not self._github:
            return []
        
        results = []
        try:
            org = kwargs.get("org", self.cfg.default_org)
            search_query = f"{query}"
            if org:
                search_query += f" org:{org}"
            
            code_results = self._github.search_code(search_query)
            for item in code_results[:20]:
                results.append(DocumentInfo(
                    id=f"{item.repository.full_name}/{item.path}",
                    name=item.name,
                    path=f"{item.repository.full_name}/{item.path}",
                    connector_type=self.connector_type,
                    mime_type=self._guess_mime(item.name),
                    size_bytes=0,
                    metadata={"repo": item.repository.full_name},
                ))
        except GithubException as e:
            log.error("github_search_error", query=query, error=str(e))
        
        return results
    
    async def _get_document_info(self, document_id: str) -> Optional[DocumentInfo]:
        parts = document_id.split("/", 2)
        name = parts[-1].split("/")[-1] if parts else document_id
        return DocumentInfo(
            id=document_id,
            name=name,
            path=document_id,
            connector_type=self.connector_type,
            mime_type=self._guess_mime(name),
        )
    
    def _guess_mime(self, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime_map = {
            "py": "text/x-python", "js": "text/javascript", "ts": "text/typescript",
            "md": "text/markdown", "json": "application/json", "yaml": "text/yaml",
            "yml": "text/yaml", "html": "text/html", "css": "text/css",
            "pdf": "application/pdf", "txt": "text/plain",
        }
        return mime_map.get(ext, "application/octet-stream")
