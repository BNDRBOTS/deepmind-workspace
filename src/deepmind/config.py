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
class OpenAIConfig:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = True
    timeout_seconds: int = 120
    retry_attempts: int = 3
    retry_backoff: float = 2.0


@dataclass
class CodeExecutionConfig:
    enabled: bool = True
    timeout_seconds: int = 300
    max_output_bytes: int = 10485760  # 10MB
    max_recursion_depth: int = 1000
    allow_network: bool = False
    restricted_python: bool = True


@dataclass
class ImageModelConfig:
    """Configuration for a single FLUX model variant."""
    name: str
    max_width: int
    max_height: int
    steps: int
    cost_per_image: float
    unfiltered: bool


@dataclass
class ImageGenerationModelsConfig:
    """Container for all FLUX model configurations."""
    ultra: ImageModelConfig = field(default_factory=lambda: ImageModelConfig(
        name="black-forest-labs/FLUX.1.1-pro",
        max_width=2048,
        max_height=2048,
        steps=50,
        cost_per_image=0.04,
        unfiltered=True,
    ))
    pro: ImageModelConfig = field(default_factory=lambda: ImageModelConfig(
        name="black-forest-labs/FLUX.1-pro",
        max_width=1440,
        max_height=1440,
        steps=25,
        cost_per_image=0.02,
        unfiltered=True,
    ))
    dev: ImageModelConfig = field(default_factory=lambda: ImageModelConfig(
        name="black-forest-labs/FLUX.1-dev",
        max_width=1024,
        max_height=1024,
        steps=20,
        cost_per_image=0.01,
        unfiltered=True,
    ))
    schnell: ImageModelConfig = field(default_factory=lambda: ImageModelConfig(
        name="black-forest-labs/FLUX.1-schnell",
        max_width=1024,
        max_height=768,
        steps=4,
        cost_per_image=0.005,
        unfiltered=False,
    ))


@dataclass
class ImageGenerationConfig:
    enabled: bool = True
    provider: str = "together"
    api_key: str = ""
    base_url: str = "https://api.together.xyz/v1"
    models: ImageGenerationModelsConfig = field(default_factory=ImageGenerationModelsConfig)
    default_model: str = "pro"
    default_width: int = 1024
    default_height: int = 1024
    timeout_seconds: int = 180
    retry_attempts: int = 2
    save_to_disk: bool = True
    output_dir: str = "/data/generated_images"
    inline_display: bool = True


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
class CodeControlsConfig:
    """UI controls for code execution settings."""
    show_timeout_slider: bool = True
    show_output_limit_slider: bool = True
    timeout_min: int = 10
    timeout_max: int = 600
    output_limit_presets: List[str] = field(default_factory=lambda: ["1MB", "10MB", "50MB", "100MB"])


@dataclass
class ImageControlsConfig:
    """UI controls for image generation settings."""
    show_model_selector: bool = True
    show_size_presets: bool = True
    show_quality_slider: bool = True
    size_presets: List[str] = field(default_factory=lambda: [
        "512x512", "768x768", "1024x1024",
        "1024x1536 (Portrait)", "1536x1024 (Landscape)", "2048x2048 (Ultra)"
    ])


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
    code_controls: CodeControlsConfig = field(default_factory=CodeControlsConfig)
    image_controls: ImageControlsConfig = field(default_factory=ImageControlsConfig)


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
    deepseek: DeepSeekConfig = field(default_factory=DeepSeekConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    code_execution: CodeExecutionConfig = field(default_factory=CodeExecutionConfig)
    image_generation: ImageGenerationConfig = field(default_factory=ImageGenerationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    connectors: ConnectorsConfig = field(default_factory=ConnectorsConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _parse_model_config(model_data: Dict[str, Any]) -> ImageModelConfig:
    """Parse a single model configuration from YAML."""
    return ImageModelConfig(
        name=model_data.get("name", ""),
        max_width=model_data.get("max_width", 1024),
        max_height=model_data.get("max_height", 1024),
        steps=model_data.get("steps", 20),
        cost_per_image=model_data.get("cost_per_image", 0.01),
        unfiltered=model_data.get("unfiltered", False),
    )


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
    
    # Parse simple configs
    if "app" in resolved:
        cfg.app = AppConfig(**{k: v for k, v in resolved["app"].items() if hasattr(cfg.app, k)})
    
    if "deepseek" in resolved:
        cfg.deepseek = DeepSeekConfig(**{k: v for k, v in resolved["deepseek"].items() if hasattr(cfg.deepseek, k)})
    
    if "openai" in resolved:
        cfg.openai = OpenAIConfig(**{k: v for k, v in resolved["openai"].items() if hasattr(cfg.openai, k)})
    
    if "code_execution" in resolved:
        cfg.code_execution = CodeExecutionConfig(**{k: v for k, v in resolved["code_execution"].items() if hasattr(cfg.code_execution, k)})
    
    if "database" in resolved:
        cfg.database = DatabaseConfig(**{k: v for k, v in resolved["database"].items() if hasattr(cfg.database, k)})
    
    if "context" in resolved:
        cfg.context = ContextConfig(**{k: v for k, v in resolved["context"].items() if hasattr(cfg.context, k)})
    
    if "embeddings" in resolved:
        cfg.embeddings = EmbeddingConfig(**{k: v for k, v in resolved["embeddings"].items() if hasattr(cfg.embeddings, k)})
    
    # Parse image_generation with nested models
    if "image_generation" in resolved:
        img_gen = resolved["image_generation"]
        
        # Parse models if present
        models = ImageGenerationModelsConfig()
        if "models" in img_gen:
            models_data = img_gen["models"]
            if "ultra" in models_data:
                models.ultra = _parse_model_config(models_data["ultra"])
            if "pro" in models_data:
                models.pro = _parse_model_config(models_data["pro"])
            if "dev" in models_data:
                models.dev = _parse_model_config(models_data["dev"])
            if "schnell" in models_data:
                models.schnell = _parse_model_config(models_data["schnell"])
        
        # Build ImageGenerationConfig
        img_gen_clean = {k: v for k, v in img_gen.items() if k != "models" and hasattr(cfg.image_generation, k)}
        cfg.image_generation = ImageGenerationConfig(**img_gen_clean)
        cfg.image_generation.models = models
    
    # Parse connectors
    if "connectors" in resolved:
        cn = resolved["connectors"]
        if "github" in cn:
            cfg.connectors.github = GitHubConfig(**{k: v for k, v in cn["github"].items() if hasattr(cfg.connectors.github, k)})
        if "dropbox" in cn:
            cfg.connectors.dropbox = DropboxConfig(**{k: v for k, v in cn["dropbox"].items() if hasattr(cfg.connectors.dropbox, k)})
        if "google_drive" in cn:
            gd = cn["google_drive"]
            dev_scaffold_data = gd.pop("dev_scaffold", {})
            cfg.connectors.google_drive = GoogleDriveConfig(**{k: v for k, v in gd.items() if hasattr(cfg.connectors.google_drive, k)})
            if dev_scaffold_data:
                cfg.connectors.google_drive.dev_scaffold = DevScaffoldConfig(**{k: v for k, v in dev_scaffold_data.items() if hasattr(cfg.connectors.google_drive.dev_scaffold, k)})
    
    # Parse UI with nested controls
    if "ui" in resolved:
        ui_data = resolved["ui"]
        
        # Parse code_controls if present
        code_controls = CodeControlsConfig()
        if "code_controls" in ui_data:
            code_controls = CodeControlsConfig(**{k: v for k, v in ui_data["code_controls"].items() if hasattr(code_controls, k)})
        
        # Parse image_controls if present
        image_controls = ImageControlsConfig()
        if "image_controls" in ui_data:
            image_controls = ImageControlsConfig(**{k: v for k, v in ui_data["image_controls"].items() if hasattr(image_controls, k)})
        
        # Build UIConfig
        ui_clean = {k: v for k, v in ui_data.items() if k not in ["code_controls", "image_controls"] and hasattr(cfg.ui, k)}
        cfg.ui = UIConfig(**ui_clean)
        cfg.ui.code_controls = code_controls
        cfg.ui.image_controls = image_controls
    
    _CONFIG = cfg
    return _CONFIG


def get_config() -> Config:
    """Get the cached config, loading if necessary."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG
