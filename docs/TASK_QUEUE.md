# BenchGoblins — Claude Code Task Queue

## Context
BenchGoblins is a fantasy sports AI decision engine built on Next.js (frontend) + FastAPI (backend), deployed on Railway. Auth is Google OAuth via custom handler. Database is Postgres. The core product is an AI chat interface ("the Goblin") that makes start/sit/trade decisions.

---

## Task 1 — Fix Google OAuth Callback (500 Error) — DONE (code-side)

**Status:** Code verified. The custom OAuth handler at `src/web/src/app/api/auth/callback/route.ts` correctly constructs the redirect URI from `NEXT_PUBLIC_APP_URL`. The Google route at `src/web/src/app/api/auth/google/route.ts` uses the same pattern. Both files are consistent.

**Remaining manual step:**
Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials → your OAuth 2.0 Client ID → **Authorized redirect URIs** → Add:
```
http://localhost:3000/api/auth/callback
```
For production, add:
```
https://your-production-domain.com/api/auth/callback
```
Save. Wait 1-5 minutes. Retry the OAuth flow.

---

## Task 2 — Change Landing Page Countdown to NFL Draft — SUPERSEDED

**Status:** Already superseded. The landing page uses a dynamic rotating countdown with 7 events across 5 sports, auto-advancing to the nearest future event. NFL Draft is listed as April 23, 2026 (Pittsburgh). No code change needed.

---

## Task 3 — Sleeper League Sync (Subscription Value Core Feature) — IN PROGRESS

**Status:** Database schema ready. Migration 011 adds `sleeper_username`, `sleeper_user_id`, `sleeper_league_id`, `roster_snapshot`, and `sleeper_synced_at` columns to users table. User ORM model updated.

**Remaining work:**
1. Backend Sleeper service (`services/sleeper.py`) — API client for Sleeper endpoints
2. API route `POST /api/user/sleeper-sync` — validates username, fetches leagues/rosters, persists
3. Frontend onboarding step — Sleeper username input after signup
4. Chat system prompt injection — prepend roster context to every `/decide` request

---

## Priority Order

| # | Task | Status |
|---|------|--------|
| 1 | Google OAuth fix | Done (manual GCP Console step remains) |
| 2 | NFL Draft countdown | Superseded (rotating countdown already covers it) |
| 3 | Sleeper sync | DB schema ready, service/frontend pending |

---

## Notes for Claude Code
- Ask for the repo structure before making changes if file locations are ambiguous
- Do not modify existing styling on the landing page — only content changes
- All env vars should be read from .env.local, never hardcoded
- Sleeper API is rate-limited — add a simple in-memory cache (5 min TTL) on roster fetches
