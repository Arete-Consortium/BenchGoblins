# BenchGoblins Deployment Guide

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
   - Click "New" → "GitHub Repo" → Select `BenchGoblins`

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
2. Add custom domain (e.g., `api.benchgoblins.app`)
3. Configure DNS CNAME to Railway's provided domain

---

## Alternative: Docker Compose (Self-Hosted)

For local development or self-hosted deployment:

```bash
cd /home/arete/projects/BenchGoblins

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

## Database Backups

### Automated Backups (GitHub Actions)

The repository includes a GitHub Actions workflow for automated daily backups.

**Setup:**

1. Enable backups by setting repository variable:
   - Go to Settings → Secrets and variables → Actions → Variables
   - Add `DATABASE_BACKUP_ENABLED` = `true`

2. Add your database connection string as a secret:
   - Settings → Secrets and variables → Actions → Secrets
   - Add `DATABASE_URL` = `postgresql://...` (your Railway PostgreSQL URL)

3. (Optional) For S3 backups:
   - Add variable `S3_BACKUP_ENABLED` = `true`
   - Add variable `S3_BACKUP_BUCKET` = `your-bucket-name`
   - Add secrets `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

**Schedule:** Backups run daily at 3:00 AM UTC.

**Manual trigger:** Go to Actions → Database Backup → Run workflow

### Manual Backups

```bash
# Set your database URL
export DATABASE_URL="postgresql://user:pass@host:5432/benchgoblins"

# Run backup script
./scripts/backup_db.sh

# Backups are saved to ./backups/ by default
ls -la ./backups/
```

### Docker Compose Backups

For self-hosted deployments:

```bash
# Run backup manually
docker-compose --profile backup up backup

# Or use the backup script with Docker
docker-compose exec postgres pg_dump -U benchgoblins benchgoblins | gzip > backups/benchgoblins_backup_$(date +%Y%m%d).sql.gz
```

For scheduled backups, add a cron job on the host:

```bash
# Edit crontab
crontab -e

# Add daily backup at 3 AM
0 3 * * * cd /path/to/BenchGoblins && docker-compose --profile backup up backup
```

### Restore from Backup

```bash
# Set your database URL
export DATABASE_URL="postgresql://user:pass@host:5432/benchgoblins"

# Restore from backup (will prompt for confirmation)
./scripts/restore_db.sh backups/benchgoblins_backup_20260125_120000.sql.gz
```

**Warning:** Restore will replace all existing data!

### Railway Point-in-Time Recovery

Railway Pro plan includes automatic point-in-time recovery:

1. Go to your PostgreSQL service
2. Click "Backups" tab
3. Select a restore point
4. Railway creates a new database from that point

This is the recommended backup strategy for production on Railway.

---

## Costs

Railway pricing (as of 2024):
- **Hobby**: $5/month, includes $5 credit
- **Pro**: $20/month, includes usage credits

Typical BenchGoblins costs:
- PostgreSQL: ~$5-10/month
- Redis: ~$3-5/month
- API: ~$5-15/month (depends on traffic)

Total: ~$15-30/month for moderate usage
