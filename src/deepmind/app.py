"""
Application entry point — Creates and configures the NiceGUI + FastAPI app.
"""
import asyncio
import structlog
from contextlib import asynccontextmanager

from nicegui import ui, app as nicegui_app
from fastapi import FastAPI

from deepmind.config import load_config
from deepmind.services.database import init_database, close_database
from deepmind.connectors.registry import get_connector_registry
from deepmind.api.routes import router as api_router
from deepmind.ui.pages import WorkspaceUI

log = structlog.get_logger()


# Load config early
cfg = load_config()

# NiceGUI creates its own FastAPI app — we mount our API on it
nicegui_app.include_router(api_router)


@nicegui_app.on_startup
async def startup():
    """Application startup — init DB, connect services."""
    log.info("app_starting", version=cfg.app.version)
    await init_database()
    
    # Connect enabled connectors
    registry = get_connector_registry()
    await registry.connect_all()
    
    log.info("app_started")


@nicegui_app.on_shutdown
async def shutdown():
    """Graceful shutdown."""
    log.info("app_shutting_down")
    
    # Disconnect all connectors
    registry = get_connector_registry()
    for name, connector in registry.get_all().items():
        try:
            await connector.disconnect()
        except Exception:
            pass
    
    # Close DeepSeek client
    from deepmind.services.deepseek_client import get_deepseek_client
    await get_deepseek_client().close()
    
    # Close database
    await close_database()
    log.info("app_stopped")


# ---- NiceGUI Page ----

@ui.page("/")
def main_page():
    """Render the main workspace UI."""
    workspace = WorkspaceUI()
    workspace.build()


# The app object for uvicorn
app = nicegui_app
