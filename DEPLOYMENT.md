# GameSpace Deployment Guide

## Railway Deployment (Recommended)

Railway provides managed PostgreSQL, Redis, and easy deployment from GitHub.

### Prerequisites

1. [Railway account](https://railway.app)
2. GitHub repo connected to Railway
3. Anthropic API key for Claude integration

### Quick Deploy

1. **Create New Project** in Railway dashboard

2. **Add Services:**
   - Click "New" → "Database" → **PostgreSQL**
   - Click "New" → "Database" → **Redis**
   - Click "New" → "GitHub Repo" → Select `GameSpace`

3. **Configure API Service:**
   - Set root directory: `src/api`
   - Railway auto-detects the Dockerfile

4. **Set Environment Variables** (Settings → Variables):
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   LOG_LEVEL=info
   ```

5. **Deploy** — Railway builds and deploys automatically

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key from Anthropic |
| `DATABASE_URL` | Yes | PostgreSQL connection string (Railway provides) |
| `REDIS_URL` | No | Redis connection string (caching, optional) |
| `LOG_LEVEL` | No | Logging level: debug, info, warning, error |

### Database Setup

Railway's PostgreSQL is empty by default. Initialize the schema:

```bash
# Connect to Railway PostgreSQL
railway connect postgres

# Run schema
psql < data/schema.sql
```

Or use Railway's web SQL editor to paste `data/schema.sql` contents.

### Health Check

The API exposes `/health` for monitoring:

```json
{
  "status": "healthy",
  "version": "0.3.0",
  "claude_available": true,
  "espn_available": true,
  "postgres_connected": true,
  "redis_connected": true
}
```

### Custom Domain

1. Go to service Settings → Networking
2. Add custom domain (e.g., `api.gamespace.app`)
3. Configure DNS CNAME to Railway's provided domain

---

## Alternative: Docker Compose (Self-Hosted)

For local development or self-hosted deployment:

```bash
cd /home/arete/projects/GameSpace

# Create .env file
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f api
```

Services:
- API: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

---

## Mobile App Configuration

Update the API URL in the mobile app:

```bash
# src/mobile/.env
EXPO_PUBLIC_API_URL=https://your-api.railway.app
```

For production builds, set this in EAS secrets:

```bash
eas secret:create --name EXPO_PUBLIC_API_URL --value https://your-api.railway.app
```

---

## Monitoring

### Logs

Railway provides built-in log viewing. For structured logging:

```bash
railway logs
```

### Metrics

Railway dashboard shows:
- CPU/Memory usage
- Request count
- Response times

### Error Tracking (Future)

Add Sentry for error monitoring:

```bash
pip install sentry-sdk[fastapi]
```

```python
import sentry_sdk
sentry_sdk.init(dsn="your-sentry-dsn")
```

---

## Scaling

Railway auto-scales based on load. For manual control:

1. Go to service Settings → Deploy
2. Adjust instance count or memory limits

### Database Scaling

Railway PostgreSQL supports:
- Vertical scaling (more RAM/CPU)
- Read replicas (Pro plan)
- Point-in-time recovery

---

## Costs

Railway pricing (as of 2024):
- **Hobby**: $5/month, includes $5 credit
- **Pro**: $20/month, includes usage credits

Typical GameSpace costs:
- PostgreSQL: ~$5-10/month
- Redis: ~$3-5/month
- API: ~$5-15/month (depends on traffic)

Total: ~$15-30/month for moderate usage
