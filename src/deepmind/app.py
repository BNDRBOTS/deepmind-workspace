"""
Application entry point — Creates and configures the NiceGUI + FastAPI app.
"""
import asyncio
import os
import structlog
from contextlib import asynccontextmanager

from nicegui import ui, app as nicegui_app
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from deepmind.config import load_config
from deepmind.services.database import init_database, close_database
from deepmind.connectors.registry import get_connector_registry
from deepmind.api.routes import router as api_router
from deepmind.api.auth_routes import router as auth_router
from deepmind.middleware.rate_limiter import get_limiter, rate_limit_exceeded_handler
from deepmind.ui.pages import WorkspaceUI

log = structlog.get_logger()

# Load config early
cfg = load_config()

# Initialize rate limiter
limiter = get_limiter()

# NiceGUI creates its own FastAPI app — we mount our API on it
nicegui_app.include_router(api_router)
nicegui_app.include_router(auth_router)

# Register rate limiter with FastAPI app state
nicegui_app.state.limiter = limiter

# Add custom exception handler for rate limit exceeded
nicegui_app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


@nicegui_app.on_startup
async def startup():
    """Application startup — init DB, connect services."""
    log.info("app_starting", version=cfg.app.version)
    await init_database()
    
    # Connect enabled connectors
    registry = get_connector_registry()
    await registry.connect_all()
    
    log.info("app_started", rate_limiting_enabled=cfg.rate_limits.enabled)


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
    
    # Close LLM clients
    from deepmind.services.deepseek_client import get_deepseek_client
    from deepmind.services.openai_client import get_openai_client
    from deepmind.services.flux_client import get_flux_client
    
    try:
        await get_deepseek_client().close()
    except Exception:
        pass
    
    try:
        await get_openai_client().close()
    except Exception:
        pass
    
    try:
        await get_flux_client().close()
    except Exception:
        pass
    
    # Close database
    await close_database()
    log.info("app_stopped")


# ---- Health Check Endpoint for Render ----

@nicegui_app.get("/api/health")
async def health_check():
    """Health check endpoint for Render monitoring."""
    return JSONResponse({
        "status": "healthy",
        "version": cfg.app.version,
        "service": "deepmind-workspace"
    })


# ---- NiceGUI Page ----

@ui.page("/")
def main_page():
    """Render the main workspace UI."""
    workspace = WorkspaceUI()
    workspace.build()


# The app object for uvicorn
app = nicegui_app

# For local development with python -m deepmind.cli
if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("APP_PORT", 8080)))
    ui.run(
        host="0.0.0.0",
        port=port,
        reload=False,
        show=False,
        title="DeepMind Workspace"
    )
