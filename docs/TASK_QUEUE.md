# BenchGoblins — Claude Code Task Queue

## Context
BenchGoblins is a fantasy sports AI decision engine built on Next.js (frontend) + FastAPI (backend), deployed on Railway. Auth is Google OAuth via NextAuth. Database is Postgres. The core product is an AI chat interface ("the Goblin") that makes start/sit/trade decisions.

---

## Task 1 — Fix Google OAuth Callback (500 Error)

**Problem:** Google redirects back to the app after auth and hits a 500. The redirect URI is correct in the app but not registered in Google Cloud Console. This is a two-part fix: env config + route verification.

**Claude Code Prompt:**
```
Fix the Google OAuth 500 error on the auth callback. Do the following:

1. Find the NextAuth config (likely /app/api/auth/[...nextauth]/route.ts or pages/api/auth/[...nextauth].ts)
2. Confirm the callbackUrl and NEXTAUTH_URL env var point to the correct base URL
3. Verify the callback route handler exists at /api/auth/callback or is handled by NextAuth's [...nextauth] catch-all
4. Check .env.local for these required vars and flag any that are missing or mismatched:
   - NEXTAUTH_URL
   - NEXTAUTH_SECRET
   - GOOGLE_CLIENT_ID
   - GOOGLE_CLIENT_SECRET
5. If NEXTAUTH_URL is not set to http://localhost:3001, fix it
6. Print a summary of what was changed and what still needs to be done manually in Google Cloud Console
```

**Manual step required (cannot be automated):**
Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials → your OAuth 2.0 Client ID → **Authorized redirect URIs** (NOT JavaScript origins) → Add:
```
http://localhost:3001/api/auth/callback/google
```
Save. Wait 1-5 minutes. Retry the OAuth flow.

---

## Task 2 — Change Landing Page Countdown to NFL Draft

**Problem:** The current countdown on the landing page is generic. The target audience is fantasy football players — the NFL Draft is their most important event and the product's launch window.

**NFL Draft 2025 date:** April 24, 2025 (8:00 PM ET, Green Bay)

**Claude Code Prompt:**
```
Find the countdown timer on the BenchGoblins landing page (check index.html, app/page.tsx, or components/Countdown.tsx). 

1. Change the target date to April 24, 2025 at 20:00:00 ET (UTC-4, so 00:00:00 UTC on April 25)
2. Change the label/heading to: "NFL Draft Starts In"
3. Add a subline beneath the countdown that reads: "Your AI edge. Ready before Round 1."
4. Keep all existing styling — only change the date, label, and add the subline
5. If the countdown is hardcoded HTML, update it. If it's a JS Date object, update the target date string.
```

---

## Task 3 — Sleeper League Sync (Subscription Value Core Feature)

**Problem:** The chat interface alone is not sufficient subscription justification. Users need the Goblin to already know their roster. Sleeper has a fully public API requiring zero OAuth — just a username. This is the fastest path to "Goblin knows your team."

**Why Sleeper first:** Public API, no auth, huge serious-player user base, can ship in one day.

**Claude Code Prompt:**
```
Build Sleeper league sync for BenchGoblins. This is the highest priority feature for subscription value.

Backend tasks:
1. Create a Sleeper service at /lib/sleeper.ts (or /services/sleeper.py if FastAPI):
   - GET https://api.sleeper.app/v1/user/{username} — validate user exists
   - GET https://api.sleeper.app/v1/user/{user_id}/leagues/nfl/2025 — fetch leagues
   - GET https://api.sleeper.app/v1/league/{league_id}/rosters — fetch rosters
   - GET https://api.sleeper.app/v1/league/{league_id}/users — map roster_id to user
   - Find the authenticated user's roster from the roster list
   - Return: league_name, scoring_settings, roster (player IDs), matchup data

2. Store in DB on the user's profile:
   - sleeper_username
   - sleeper_user_id  
   - sleeper_league_id (if multiple leagues, store primary)
   - roster_snapshot (JSON, refreshed on each session)
   - last_synced_at timestamp

3. Create API route POST /api/user/sleeper-sync:
   - Accepts { username: string }
   - Validates, fetches, stores
   - Returns success + league name for confirmation message

Frontend tasks:
4. Add a "Connect Your League" step to onboarding (after signup, before first chat)
   - Platform selector: Sleeper | ESPN | Yahoo (ESPN/Yahoo show "coming soon")
   - Sleeper: simple username input field + "Sync" button
   - On success: show "✓ Connected to [League Name] — the Goblin knows your roster"

5. In the chat system prompt builder, inject roster context when available:
   - "User's fantasy roster: [player list]"
   - "League scoring: [PPR/standard/half-PPR]"
   - "Current matchup: [opponent's team]"
   - This context should be prepended to every chat request silently

Test by syncing a real Sleeper username and verifying the Goblin references the roster in its response without being asked.
```

---

## Priority Order

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | Google OAuth fix | 30 min | Unblocks all auth |
| 2 | NFL Draft countdown | 15 min | Marketing/timing alignment |
| 3 | Sleeper sync | 1-2 days | Core subscription value |

Run Task 1 first — nothing else matters if users can't log in.

---

## Notes for Claude Code
- Ask for the repo structure before making changes if file locations are ambiguous
- Do not modify existing styling on the landing page — only content changes
- All env vars should be read from .env.local, never hardcoded
- Sleeper API is rate-limited — add a simple in-memory cache (5 min TTL) on roster fetches
