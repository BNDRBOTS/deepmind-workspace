#!/usr/bin/env bash
set -e

echo "🚀 Starting Render Build for DeepMind Workspace"
echo "================================================"

# Increase pip timeout for large packages
export PIP_DEFAULT_TIMEOUT=300
export PIP_NO_CACHE_DIR=1

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --timeout=300 --no-cache-dir -e .

# Pre-download embedding model to avoid first-request delay
echo "🤖 Pre-downloading sentence-transformers model..."
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Initialize database schema
echo "🗄️  Initializing database schema..."
python -c "
import asyncio
from deepmind.services.database import init_database
asyncio.run(init_database())
print('✅ Database schema initialized')
"

# Verify ChromaDB can initialize
echo "🔍 Verifying ChromaDB setup..."
python -c "
import chromadb
import os
chroma_path = os.getenv('CHROMADB_PATH', '/data/chromadb')
client = chromadb.PersistentClient(path=chroma_path)
print(f'✅ ChromaDB initialized at {chroma_path}')
"

echo "================================================"
echo "✅ Build complete! Ready for deployment."
echo "================================================"
