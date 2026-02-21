# BNDR::ON Enterprise Platform

🚀 **100% Cloud-Native AI Platform** powered by Railway

## Quick Deploy

### Deploy to Railway (Recommended)

One-click deployment for entire application:

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/deepmind-workspace)

## Architecture

```
┌───────────────────────────────┐
│      BNDR::ON Platform         │
└──────────────┬────────────────┘
               │
       ┌───────┼───────┐
       │       Gateway      │
       │    (Port 8000)   │
       └───────┬───────┘
               │
   ┌────────┼────────────┐
   │           │             │
┌──┴──┐   ┌──┴──┐   ┌──┴──┐
│Chat │   │ API │   │Auth│
│8001 │   │8007 │   │8015│
└─────┘   └─────┘   └─────┘
   │           │             │
┌──┴────────┴───────────┴──┐
│        Memory Core            │
│      (Port 8004)             │
│    Pinecone Vectors         │
└────────────────────────────┘
         │
┌────────┼─────────┐
│    Frontend         │
│   (Port 3000)      │
│  React TypeScript  │
└──────────────────┘
```

## Services

### Backend Services (Python/FastAPI)

1. **Gateway (Port 8000)** - API routing & aggregation
2. **Service 01: Chat (Port 8001)** - Real-time messaging with Supabase
3. **Service 04: Memory (Port 8004)** - Vector storage with Pinecone
4. **Service 07: API (Port 8007)** - DeepSeek R1 integration
5. **Service 15: Auth (Port 8015)** - JWT authentication

### Frontend (Port 3000)

- React 18 + TypeScript
- Vite build system
- Tailwind CSS
- Zustand state management
- React Router v6

## Infrastructure

- **Platform**: Railway (100% Cloud)
- **Database**: Supabase PostgreSQL
- **Cache**: Upstash Redis
- **Vectors**: Pinecone
- **LLM**: DeepSeek R1

## Environment Variables

### Required for Railway Deployment

```bash
# API Keys
DEEPSEEK_API_KEY=your_deepseek_key
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=your_pinecone_env
OPENAI_API_KEY=your_openai_key

# Authentication
JWT_SECRET=your_jwt_secret

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Redis (Upstash)
REDIS_URL=your_redis_url
```

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL (or Supabase account)
- Redis (or Upstash account)
- Pinecone account
- DeepSeek API key

### Backend Setup

```bash
# Install dependencies for each service
cd backend/gateway && pip install -r requirements.txt
cd backend/services/01_chat && pip install -r requirements.txt
cd backend/services/04_memory && pip install -r requirements.txt
cd backend/services/07_api && pip install -r requirements.txt
cd backend/services/15_auth && pip install -r requirements.txt

# Run services (separate terminals)
cd backend/gateway && uvicorn main:app --port 8000
cd backend/services/01_chat && uvicorn main:app --port 8001
cd backend/services/04_memory && uvicorn main:app --port 8004
cd backend/services/07_api && uvicorn main:app --port 8007
cd backend/services/15_auth && uvicorn main:app --port 8015
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Tech Stack

### Backend

- **Framework**: FastAPI 0.115.0
- **Server**: Uvicorn 0.32.0
- **Database ORM**: Supabase Client 2.9.0
- **Cache**: Redis 5.2.0
- **Vectors**: Pinecone 5.0.1
- **LLM**: OpenAI SDK 1.54.0 + DeepSeek
- **Auth**: Python-JOSE 3.3.0, Passlib 1.7.4
- **Validation**: Pydantic 2.9.2

### Frontend

- **Framework**: React 18.3.1
- **Language**: TypeScript 5.6.2
- **Build**: Vite 5.4.8
- **Styling**: Tailwind CSS 3.4.13
- **State**: Zustand 5.0.0
- **Routing**: React Router 6.26.2
- **HTTP**: Axios 1.7.7
- **Icons**: Lucide React 0.462.0

## Features

✅ **Real-time Chat** with DeepSeek R1
✅ **Vector Memory** with Pinecone
✅ **JWT Authentication** with refresh tokens
✅ **Message History** with Supabase
✅ **Semantic Search** in memory
✅ **Responsive UI** with Tailwind
✅ **Type Safety** with TypeScript
✅ **Auto-scaling** on Railway
✅ **Health Checks** for all services
✅ **CORS** configured
✅ **Production Ready**

## Cost Estimate (Monthly)

- Railway: $50-100
- Supabase: $25
- Upstash Redis: $10-20
- Pinecone: $70
- DeepSeek API: Variable (pay-per-use)

**Total**: ~$155-215/month

## Documentation

- [Cloud Deployment Guide](docs/CLOUD_DEPLOYMENT.md)
- [Architecture Overview](docs/ARCHITECTURE.md)

## Security

- JWT RS256 authentication
- Bcrypt password hashing
- Environment variable secrets
- CORS middleware
- Input validation (Pydantic)
- SQL injection protection
- XSS protection
- HTTPS enforcement (Railway)

## Monitoring

- Health check endpoints
- Railway logs integration
- Error tracking ready
- Performance metrics
- Database query logging

## License

Proprietary - BNDR BOTS 2026

## Support

For issues and questions:
- GitHub Issues: [deepmind-workspace/issues](https://github.com/BNDRBOTS/deepmind-workspace/issues)
- Email: bndrbots@gmail.com