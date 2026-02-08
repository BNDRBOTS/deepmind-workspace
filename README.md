# DeepMind Workspace

**Modular AI Assistant with Persistent Context, Document Integration, and DeepSeek API**

A ChatGPT-like workspace that never forgets. Full conversation history with intelligent
summarization, document integration from GitHub/Dropbox/Google Drive, and a premium
dark-mode UI built on NiceGUI + FastAPI.

## Features

- **Persistent Memory** — Full conversation history stored in SQLite. No truncation ever.
  Intelligent summarization compresses old messages while keeping every detail accessible.
- **Context Visualizer** — Real-time indicator showing context window utilization,
  token counts, and summarization status.
- **Document Integration** — Browse, search, and pin documents from GitHub, Dropbox,
  and Google Drive directly into your conversation context.
- **Dev Scaffold** — Google Drive auto-searches for technical resources when your
  conversation touches implementation topics (configurable triggers).
- **Vector Search** — All documents processed into ChromaDB embeddings for
  semantic retrieval during conversations.
- **DeepSeek API** — Streaming responses, multimodal-ready architecture,
  automatic summarization via DeepSeek models.
- **Dark/Light Mode** — Premium ChatGPT-inspired UI with theme toggle.
- **Cloud-Native** — Docker + Docker Compose, ready for AWS/GCP/Azure deployment.
- **Modular Connectors** — Add Slack, Notion, S3, or any source in <30 minutes.
  See `docs/ADDING_CONNECTORS.md`.

## Quick Start

### 1. Clone and Configure

```bash
git clone <your-repo-url>
cd deepmind-workspace
cp .env.example .env
# Edit .env with your API keys
```

### 2. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Run

```bash
python -m deepmind.cli
# Open http://localhost:8080
```

### 4. Docker

```bash
docker compose up --build
# Open http://localhost:8080
```

## Configuration

All configuration lives in `config/app.yaml` with environment variable overrides.
No code changes needed to:
- Switch DeepSeek models
- Adjust context window limits
- Enable/disable connectors
- Change UI theme defaults
- Tune embedding parameters

## Architecture

```
src/deepmind/
├── app.py                 # NiceGUI + FastAPI app entry
├── cli.py                 # CLI launcher
├── config.py              # YAML + env config loader
├── api/
│   └── routes.py          # REST API endpoints
├── connectors/
│   ├── base.py            # BaseConnector interface
│   ├── registry.py        # Auto-discovery + lifecycle
│   ├── github_connector.py
│   ├── dropbox_connector.py
│   └── gdrive_connector.py
├── models/
│   └── conversation.py    # SQLAlchemy models
├── services/
│   ├── context_manager.py # NO-TRUNCATION context engine
│   ├── conversation_service.py
│   ├── database.py        # Async SQLite via SQLAlchemy
│   ├── deepseek_client.py # DeepSeek API client
│   ├── document_processor.py
│   └── vector_store.py    # ChromaDB wrapper
└── ui/
    ├── theme.py           # Dark/Light theme system
    └── pages.py           # NiceGUI workspace UI
```

## Adding New Connectors

See [docs/ADDING_CONNECTORS.md](docs/ADDING_CONNECTORS.md) for the full guide.
The system is designed so you can add Slack, Notion, S3, or any document source
by implementing a single Python class and adding a YAML entry.

## License

MIT
