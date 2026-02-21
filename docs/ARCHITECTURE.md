# System Architecture

## Overview

BNDR::ON is a cloud-native microservices platform built for Railway deployment. Each service is independently deployable and scalable.

## Service Architecture

```
┌────────────────────────────────────────┐
│              Client (Browser)              │
└──────────────────┬─────────────────────┘
                   │ HTTPS
                   │
┌──────────────────┴─────────────────────┐
│         Frontend (Railway Service)         │
│          React + TypeScript + Vite         │
│                Port 3000                    │
└──────────────────┬─────────────────────┘
                   │ HTTP
                   │
┌──────────────────┴─────────────────────┐
│           Gateway (Railway Service)        │
│             FastAPI Router                 │
│                Port 8000                    │
└──────────────────┬─────────────────────┘
                   │
       ┌───────────┼────────────┐
       │           │              │
   ┌───┴───┐   ┌──┴───┐   ┌──┴───┐
   │  Chat  │   │  API  │   │  Auth │
   │  8001  │   │  8007 │   │  8015 │
   └───┬───┘   └──┬───┘   └──┬───┘
       │           │              │
   ┌───┴───────────┼────────────┴───┐
   │          Memory Core                  │
   │    Pinecone Vector Storage          │
   │           Port 8004                   │
   └────────────────────────────────────┘
           │           │              │
       ┌───┴───┐   ┌──┴───┐   ┌──┴───┐
       │Supabase│   │Pinecone│   │Upstash│
       │   DB   │   │ Vectors│   │ Redis │
       └────────┘   └─────────┘   └────────┘
```

## Services Detail

### Gateway (Port 8000)

**Purpose**: API routing and request aggregation

**Responsibilities**:
- Route requests to appropriate services
- CORS handling
- Health check aggregation
- Request/response logging

**Technology**: FastAPI, httpx

### Service 01: Chat (Port 8001)

**Purpose**: Real-time messaging and conversation management

**Responsibilities**:
- Create/read/delete conversations
- Send/retrieve messages
- Message persistence
- Conversation history

**Technology**: FastAPI, Supabase

**Database Schema**:
```sql
conversations:
- id (uuid, primary key)
- user_id (text)
- title (text)
- created_at (timestamp)

messages:
- id (uuid, primary key)
- conversation_id (uuid, foreign key)
- user_id (text)
- content (text)
- role (text: 'user' | 'assistant')
- created_at (timestamp)
```

### Service 04: Memory (Port 8004)

**Purpose**: Vector-based memory storage and retrieval

**Responsibilities**:
- Store text as vector embeddings
- Semantic search in memory
- Memory persistence
- Context-aware recall

**Technology**: FastAPI, Pinecone, OpenAI Embeddings

**Vector Spec**:
- Dimension: 1536 (OpenAI ada-002)
- Metric: Cosine similarity
- Index: Serverless (AWS us-east-1)

### Service 07: API (Port 8007)

**Purpose**: LLM integration and model routing

**Responsibilities**:
- DeepSeek R1 API integration
- Streaming responses
- Token management
- Model fallbacks

**Technology**: FastAPI, httpx, DeepSeek API

**Supported Models**:
- `deepseek-reasoner` (R1)
- `deepseek-chat`

### Service 15: Auth (Port 8015)

**Purpose**: Authentication and user identity

**Responsibilities**:
- User registration/login
- JWT token generation
- Token refresh
- Password hashing

**Technology**: FastAPI, Python-JOSE, Passlib, Supabase

**Token Spec**:
- Algorithm: HS256
- Access Token: 60 minutes
- Refresh Token: 30 days

### Frontend (Port 3000)

**Purpose**: User interface

**Responsibilities**:
- User authentication UI
- Chat interface
- Memory management UI
- Settings dashboard

**Technology**: React 18, TypeScript, Vite, Tailwind CSS

**State Management**: Zustand
**Routing**: React Router v6

## Data Flow

### Authentication Flow

```
1. User → Frontend: Enter credentials
2. Frontend → Gateway → Auth: POST /auth/login
3. Auth → Supabase: Verify credentials
4. Auth → Frontend: Return JWT tokens
5. Frontend: Store tokens in localStorage
6. Frontend: Add token to all subsequent requests
```

### Chat Flow

```
1. User → Frontend: Send message
2. Frontend → Gateway → Chat: POST /chat/messages
3. Chat → Supabase: Store user message
4. Frontend → Gateway → API: POST /api/chat/completions
5. API → DeepSeek: Forward request
6. DeepSeek → API → Frontend: Stream response
7. Frontend → Gateway → Chat: POST /chat/messages (assistant)
8. Chat → Supabase: Store assistant message
```

### Memory Flow

```
1. User → Frontend: Store memory
2. Frontend → Gateway → Memory: POST /memory/store
3. Memory → OpenAI: Generate embedding
4. Memory → Pinecone: Upsert vector
5. Memory → Frontend: Confirm stored

--- Later ---

1. User → Frontend: Query memory
2. Frontend → Gateway → Memory: POST /memory/query
3. Memory → OpenAI: Generate query embedding
4. Memory → Pinecone: Search vectors
5. Memory → Frontend: Return matches
```

## Scalability

### Horizontal Scaling

- Each service can scale independently on Railway
- Stateless services enable easy replication
- Load balancing handled by Railway

### Vertical Scaling

- Resource allocation adjustable per service
- Database connection pooling
- Redis caching layer

### Performance Optimizations

- Async/await throughout
- Connection pooling
- Response caching (Redis)
- Vector index optimization (Pinecone)
- Frontend code splitting (Vite)

## Security

### Authentication

- JWT with HS256 algorithm
- Bcrypt password hashing (cost factor 12)
- Token refresh mechanism
- Secure token storage

### Network

- HTTPS enforcement (Railway)
- CORS configured
- Rate limiting ready
- Request validation (Pydantic)

### Data

- SQL injection protection (Supabase)
- XSS protection (React)
- Environment variable secrets
- Database encryption at rest (Supabase)

## Monitoring

### Health Checks

- `/health` endpoint on each service
- Database connectivity checks
- External API availability checks

### Logging

- Structured logging (Python logging)
- Request/response logging
- Error tracking
- Railway logs aggregation

### Metrics

- Response times
- Error rates
- Token usage
- Database query performance

## Deployment

### Railway Configuration

- `railway.json`: Service definitions
- `railway.toml`: Build and deploy config
- Environment variables via Railway UI
- Auto-deploy on git push

### Infrastructure

- **Compute**: Railway
- **Database**: Supabase (PostgreSQL)
- **Cache**: Upstash (Redis)
- **Vectors**: Pinecone
- **LLM**: DeepSeek API

## Future Enhancements

- WebSocket support for real-time chat
- Redis caching layer
- Rate limiting middleware
- Usage analytics
- Admin dashboard
- Multi-model support
- File upload/storage
- Voice interface