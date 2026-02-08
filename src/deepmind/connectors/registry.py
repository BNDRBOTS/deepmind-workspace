"""
Connector Registry — Auto-discovers and manages all document connectors.
New connectors are registered via config/connectors.yaml.
"""
import importlib
from typing import Dict, Optional

import yaml
import structlog

from deepmind.connectors.base import BaseConnector, ConnectorStatus

log = structlog.get_logger()


class ConnectorRegistry:
    """Manages lifecycle of all document connectors."""
    
    def __init__(self):
        self._connectors: Dict[str, BaseConnector] = {}
        self._registry_config: Dict = {}
    
    def load_registry(self, config_path: str = "config/connectors.yaml"):
        """Load connector definitions from YAML config."""
        from pathlib import Path
        
        path = Path(config_path)
        if not path.exists():
            # Try relative to package
            path = Path(__file__).parent.parent.parent.parent / config_path
        
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            self._registry_config = data.get("registry", {})
        
        log.info("connector_registry_loaded", connectors=list(self._registry_config.keys()))
    
    def instantiate_all(self):
        """Create instances of all registered connectors."""
        for name, cfg in self._registry_config.items():
            try:
                module_path = cfg["module"]
                class_name = cfg["class"]
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                instance = cls()
                self._connectors[name] = instance
                log.info("connector_instantiated", name=name, cls=class_name)
            except Exception as e:
                log.error("connector_instantiate_error", name=name, error=str(e))
    
    async def connect_all(self):
        """Attempt to connect all enabled connectors."""
        from deepmind.config import get_config
        cfg = get_config()
        
        for name, connector in self._connectors.items():
            # Check if connector is enabled in app config
            connector_cfg = getattr(cfg.connectors, name, None)
            if connector_cfg and hasattr(connector_cfg, "enabled") and not connector_cfg.enabled:
                continue
            
            try:
                await connector.connect()
            except Exception as e:
                log.warning("connector_connect_failed", name=name, error=str(e))
    
    def get(self, name: str) -> Optional[BaseConnector]:
        return self._connectors.get(name)
    
    def get_all(self) -> Dict[str, BaseConnector]:
        return self._connectors
    
    async def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all connectors."""
        statuses = {}
        for name, connector in self._connectors.items():
            try:
                status = await connector.get_status()
                cfg = self._registry_config.get(name, {})
                statuses[name] = {
                    "name": name,
                    "display_name": cfg.get("display_name", name),
                    "icon": cfg.get("icon", ""),
                    "color": cfg.get("color", "#888"),
                    "status": status.value,
                    "capabilities": cfg.get("capabilities", []),
                }
            except Exception:
                statuses[name] = {
                    "name": name,
                    "status": "error",
                }
        return statuses


_registry: Optional[ConnectorRegistry] = None


def get_connector_registry() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
        _registry.load_registry()
        _registry.instantiate_all()
    return _registry
