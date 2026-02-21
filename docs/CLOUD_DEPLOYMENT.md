# Cloud Deployment Guide

## Railway Deployment (Recommended)

### One-Click Deploy

1. Click the **Deploy on Railway** button in README
2. Connect your GitHub account
3. Railway automatically detects services from `railway.toml`
4. Add environment variables in Railway UI
5. Deploy automatically starts

### Manual Railway Deployment

#### Step 1: Create Railway Project

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init
```

#### Step 2: Link Repository

```bash
# Link to GitHub repository
railway link

# Select BNDRBOTS/deepmind-workspace
```

#### Step 3: Add Environment Variables

In Railway UI, add these variables to your project:

```bash
# Required for all services
DEEPSEEK_API_KEY=sk-...
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=us-east-1-aws
OPENAI_API_KEY=sk-...
JWT_SECRET=your_random_secret_string
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
REDIS_URL=redis://...

# Service URLs (Railway auto-generates these)
CHAT_SERVICE_URL=https://chat-production-xxxx.up.railway.app
MEMORY_SERVICE_URL=https://memory-production-xxxx.up.railway.app
API_SERVICE_URL=https://api-production-xxxx.up.railway.app
AUTH_SERVICE_URL=https://auth-production-xxxx.up.railway.app

# Frontend
VITE_API_URL=https://gateway-production-xxxx.up.railway.app
```

#### Step 4: Deploy

```bash
# Railway auto-deploys on git push
git push origin main

# Or manually trigger deploy
railway up
```

### Railway Service Configuration

Railway automatically detects services from `railway.toml`:

- **Gateway**: `backend/gateway`
- **Chat**: `backend/services/01_chat`
- **Memory**: `backend/services/04_memory`
- **API**: `backend/services/07_api`
- **Auth**: `backend/services/15_auth`
- **Frontend**: `frontend`

Each service gets:
- Unique URL
- Health check monitoring
- Auto-scaling
- HTTPS certificate
- Logging

## Infrastructure Setup

### Supabase (Database)

1. Create account at [supabase.com](https://supabase.com)
2. Create new project
3. Go to Project Settings → API
4. Copy `URL` and `anon/public` key
5. Create tables:

```sql
-- Users table
CREATE TABLE users (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Conversations table
CREATE TABLE conversations (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id TEXT NOT NULL,
  title TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Messages table
CREATE TABLE messages (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  conversation_id UUID REFERENCES conversations(id),
  user_id TEXT NOT NULL,
  content TEXT NOT NULL,
  role TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### Pinecone (Vector Database)

1. Create account at [pinecone.io](https://www.pinecone.io)
2. Create API key
3. Index auto-creates on first memory store
4. No manual setup needed

### Upstash (Redis)

1. Create account at [upstash.com](https://upstash.com)
2. Create Redis database
3. Select region (us-east-1 recommended)
4. Copy connection URL

### DeepSeek (LLM API)

1. Create account at [deepseek.com](https://www.deepseek.com)
2. Generate API key
3. Add credits for usage

## Monitoring & Maintenance

### Railway Dashboard

- View logs: `railway logs`
- Check status: Services → Status
- View metrics: Services → Metrics
- Update env vars: Services → Variables

### Health Checks

Each service has `/health` endpoint:

- Gateway: `https://gateway-xxxx.up.railway.app/health`
- Chat: `https://chat-xxxx.up.railway.app/health`
- Memory: `https://memory-xxxx.up.railway.app/health`
- API: `https://api-xxxx.up.railway.app/health`
- Auth: `https://auth-xxxx.up.railway.app/health`

### Logs

```bash
# View all logs
railway logs

# View specific service
railway logs --service gateway

# Follow logs
railway logs --follow
```

## Cost Optimization

### Railway

- **Hobby Plan**: $5/month (trial)
- **Pro Plan**: $20/month + usage
- Optimize: Scale down non-critical services during low traffic

### Supabase

- **Free Tier**: 500MB database, 2GB bandwidth
- **Pro Plan**: $25/month
- Optimize: Archive old messages, index optimization

### Pinecone

- **Free Tier**: 1 index, 100K vectors
- **Starter Plan**: $70/month
- Optimize: Reduce vector dimensions, batch operations

### Upstash

- **Free Tier**: 10K requests/day
- **Pay-as-you-go**: $0.20 per 100K requests
- Optimize: Set TTL on cache entries

### DeepSeek

- **Pay-per-use**: ~$0.14 per million tokens
- Optimize: Reduce max_tokens, cache responses

**Total Estimated Monthly Cost**: $50-150

## Scaling Guide

### Vertical Scaling (Railway)

```bash
# Increase resources for a service
railway service --name gateway
# UI: Service Settings → Resources → Adjust CPU/Memory
```

### Horizontal Scaling (Railway)

```bash
# Add replicas
# UI: Service Settings → Replicas → Increase count
```

### Database Scaling (Supabase)

- Upgrade to larger plan
- Enable connection pooling
- Add read replicas

### Cache Scaling (Upstash)

- Upgrade to larger plan
- Enable Redis clustering

## Troubleshooting

### Service Won't Start

1. Check logs: `railway logs --service <name>`
2. Verify environment variables
3. Check health endpoint
4. Restart service: `railway restart --service <name>`

### Database Connection Issues

1. Verify `SUPABASE_URL` and `SUPABASE_KEY`
2. Check Supabase project status
3. Test connection from local machine
4. Review connection pooling settings

### API Rate Limits

1. Check DeepSeek API quota
2. Implement request throttling
3. Add caching layer (Redis)
4. Reduce concurrent requests

### Memory/Embedding Issues

1. Verify `PINECONE_API_KEY` and `OPENAI_API_KEY`
2. Check Pinecone index status
3. Verify vector dimensions match (1536)
4. Review embedding request logs

## Backup & Recovery

### Database Backup (Supabase)

- Auto-backups: Daily (Pro plan)
- Manual backup: Project Settings → Backups
- Export: `pg_dump` via Supabase connection string

### Vector Backup (Pinecone)

- Use Pinecone export API
- Store in S3/Cloud Storage
- Restore via import API

### Configuration Backup

- Store environment variables in password manager
- Keep `railway.toml` in version control
- Document custom configurations

## Security Best Practices

1. **Rotate secrets regularly** (JWT_SECRET, API keys)
2. **Use strong passwords** for all services
3. **Enable 2FA** on all accounts
4. **Review access logs** regularly
5. **Update dependencies** monthly
6. **Monitor for vulnerabilities** (Dependabot)
7. **Limit API key permissions** to minimum required
8. **Use separate keys** for dev/staging/prod

## Production Checklist

- [ ] All environment variables set
- [ ] Database tables created
- [ ] Health checks passing
- [ ] HTTPS enabled (Railway default)
- [ ] CORS configured correctly
- [ ] API keys rotated from defaults
- [ ] Monitoring configured
- [ ] Backup strategy in place
- [ ] Cost alerts set up
- [ ] Documentation updated
- [ ] Team access configured
- [ ] Error tracking enabled

## Support

- Railway: [railway.app/help](https://railway.app/help)
- Supabase: [supabase.com/support](https://supabase.com/support)
- Pinecone: [docs.pinecone.io](https://docs.pinecone.io)
- Upstash: [upstash.com/docs](https://upstash.com/docs)