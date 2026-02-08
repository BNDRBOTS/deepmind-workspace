"""
Configuration loader — merges YAML config with environment variables.
Supports ${VAR:default} interpolation in YAML values.
"""
import os
import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

_ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        def replacer(m):
            var, default = m.group(1), m.group(2)
            return os.environ.get(var, default if default is not None else "")
        resolved = _ENV_PATTERN.sub(replacer, value)
        if resolved.isdigit():
            return int(resolved)
        if resolved.replace(".", "", 1).isdigit():
            return float(resolved)
        if resolved.lower() in ("true", "false"):
            return resolved.lower() == "true"
        return resolved
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env(v) for v in value]
    return value


@dataclass
class AppConfig:
    name: str = "DeepMind Workspace"
    version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8080
    secret_key: str = ""
    env: str = "production"
    log_level: str = "INFO"


@dataclass
class DeepSeekConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    chat_model: str = "deepseek-chat"
    reasoning_model: str = "deepseek-reasoner"
    max_tokens: int = 8192
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = True
    timeout_seconds: int = 120
    retry_attempts: int = 3
    retry_backoff: float = 2.0


@dataclass
class DatabaseConfig:
    sqlite_path: str = "./data/conversations.db"
    chromadb_path: str = "./data/chromadb"
    wal_mode: bool = True
    busy_timeout_ms: int = 10000


@dataclass
class ContextConfig:
    max_tokens: int = 128000
    summary_trigger_tokens: int = 96000
    recent_messages_keep: int = 20
    summarization_model: str = "deepseek-chat"
    summarization_max_tokens: int = 2048
    overlap_messages: int = 3


@dataclass
class EmbeddingConfig:
    model: str = "all-MiniLM-L6-v2"
    dimension: int = 384
    chunk_size: int = 1000
    chunk_overlap: int = 200
    batch_size: int = 64
    relevance_threshold: float = 0.35
    max_results: int = 8


@dataclass
class GitHubConfig:
    enabled: bool = True
    token: str = ""
    default_org: str = ""
    sync_interval_minutes: int = 30
    file_extensions: List[str] = field(default_factory=lambda: [".py", ".js", ".ts", ".md", ".yaml", ".json"])
    max_file_size_kb: int = 500


@dataclass
class DropboxConfig:
    enabled: bool = False
    app_key: str = ""
    app_secret: str = ""
    refresh_token: str = ""
    sync_folder: str = "/DeepMindWorkspace"
    sync_interval_minutes: int = 15


@dataclass
class DevScaffoldConfig:
    enabled: bool = True
    search_triggers: List[str] = field(default_factory=lambda: [
        "how to implement", "documentation for", "code example",
        "framework reference", "architecture pattern"
    ])
    file_types: List[str] = field(default_factory=lambda: [
        "application/pdf", "text/plain", "text/markdown",
        "application/vnd.google-apps.document"
    ])


@dataclass
class GoogleDriveConfig:
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8080/api/connectors/google/callback"
    scopes: List[str] = field(default_factory=lambda: [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ])
    sync_interval_minutes: int = 15
    dev_scaffold: DevScaffoldConfig = field(default_factory=DevScaffoldConfig)


@dataclass
class ConnectorsConfig:
    github: GitHubConfig = field(default_factory=GitHubConfig)
    dropbox: DropboxConfig = field(default_factory=DropboxConfig)
    google_drive: GoogleDriveConfig = field(default_factory=GoogleDriveConfig)


@dataclass
class UIConfig:
    theme: str = "dark"
    title: str = "DeepMind Workspace"
    sidebar_width: int = 340
    message_max_display: int = 200
    token_warning_percent: int = 80
    token_critical_percent: int = 95
    animations: bool = True
    font_family: str = "Inter, system-ui, -apple-system, sans-serif"
    code_font: str = "JetBrains Mono, Fira Code, monospace"


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    connectors: ConnectorsConfig = field(default_factory=ConnectorsConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _dict_to_dataclass(cls, data: Dict[str, Any]):
    """Recursively convert a dict to nested dataclasses."""
    import dataclasses
    if not dataclasses.is_dataclass(cls):
        return data
    fieldtypes = {f.name: f.type for f in dataclasses.fields(cls)}
    kwargs = {}
    for k, v in data.items():
        if k in fieldtypes:
            ft = fieldtypes[k]
            if isinstance(ft, str):
                ft = eval(ft) if ft in dir() else str
            if dataclasses.is_dataclass(ft) and isinstance(v, dict):
                kwargs[k] = _dict_to_dataclass(ft, v)
            else:
                kwargs[k] = v
    return cls(**kwargs)


_CONFIG: Optional[Config] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """Load and cache application configuration."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    
    if config_path is None:
        candidates = [
            Path("config/app.yaml"),
            Path(__file__).parent.parent.parent / "config" / "app.yaml",
            Path.home() / ".deepmind" / "app.yaml",
        ]
        for c in candidates:
            if c.exists():
                config_path = str(c)
                break
    
    raw = {}
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
    
    resolved = _resolve_env(raw)
    
    cfg = Config()
    if "app" in resolved:
        cfg.app = AppConfig(**{k: v for k, v in resolved["app"].items() if hasattr(cfg.app, k)})
    if "deepseek" in resolved:
        cfg.deepseek = DeepSeekConfig(**{k: v for k, v in resolved["deepseek"].items() if hasattr(cfg.deepseek, k)})
    if "database" in resolved:
        cfg.database = DatabaseConfig(**{k: v for k, v in resolved["database"].items() if hasattr(cfg.database, k)})
    if "context" in resolved:
        cfg.context = ContextConfig(**{k: v for k, v in resolved["context"].items() if hasattr(cfg.context, k)})
    if "embeddings" in resolved:
        cfg.embeddings = EmbeddingConfig(**{k: v for k, v in resolved["embeddings"].items() if hasattr(cfg.embeddings, k)})
    if "ui" in resolved:
        cfg.ui = UIConfig(**{k: v for k, v in resolved["ui"].items() if hasattr(cfg.ui, k)})
    if "connectors" in resolved:
        cn = resolved["connectors"]
        if "github" in cn:
            cfg.connectors.github = GitHubConfig(**{k: v for k, v in cn["github"].items() if hasattr(cfg.connectors.github, k)})
        if "dropbox" in cn:
            cfg.connectors.dropbox = DropboxConfig(**{k: v for k, v in cn["dropbox"].items() if hasattr(cfg.connectors.dropbox, k)})
        if "google_drive" in cn:
            gd = cn["google_drive"]
            dev_scaffold = gd.pop("dev_scaffold", {})
            cfg.connectors.google_drive = GoogleDriveConfig(**{k: v for k, v in gd.items() if hasattr(cfg.connectors.google_drive, k)})
            if dev_scaffold:
                cfg.connectors.google_drive.dev_scaffold = DevScaffoldConfig(**{k: v for k, v in dev_scaffold.items() if hasattr(cfg.connectors.google_drive.dev_scaffold, k)})
    
    _CONFIG = cfg
    return _CONFIG


def get_config() -> Config:
    """Get the cached config, loading if necessary."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG
