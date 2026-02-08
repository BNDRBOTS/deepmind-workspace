"""CLI entry point for DeepMind Workspace."""
import os
import sys
import asyncio
import uvicorn

def main():
    """Launch the DeepMind Workspace server."""
    from deepmind.config import load_config
    cfg = load_config()
    
    os.makedirs(os.path.dirname(cfg.database.sqlite_path), exist_ok=True)
    os.makedirs(cfg.database.chromadb_path, exist_ok=True)
    
    # Import here to trigger NiceGUI route registration before uvicorn starts
    from deepmind.app import create_app  # noqa: F401
    
    uvicorn.run(
        "deepmind.app:app",
        host=cfg.app.host,
        port=cfg.app.port,
        reload=cfg.app.env == "development",
        log_level=cfg.app.log_level.lower(),
        timeout_keep_alive=30,
    )

if __name__ == "__main__":
    main()
