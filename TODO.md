# BenchGoblins — Development TODO

## Phase 1: Foundation (Week 1-2)
*Goal: Local scoring engine works for simple A vs B comparisons*

### Data Layer
- [x] Set up PostgreSQL schema for players, stats, rosters
- [x] Build ESPN API client for player data
- [x] Create nightly stats sync job (cron or scheduled task)
- [x] Implement Redis caching layer for hot player data
- [x] Add Basketball Reference scraper for advanced stats (NBA)
- [x] Add Pro Football Reference scraper (NFL)

### Core Scoring Engine
- [x] Implement `Player` data model with all required fields
- [x] Build Space Creation Index (SCI) calculator
- [x] Build Role Motion Index (RMI) calculator
- [x] Build Gravity Impact Score (GIS) calculator
- [x] Build Opportunity Delta (OD) calculator
- [x] Build Matchup Space Fit (MSF) calculator
- [x] Create composite scoring function with risk mode weights
- [x] Write unit tests for each index calculation
- [x] Add MLB/NHL sport-specific scoring (SCI, RMI, GIS for all 4 sports)
- [x] Wire ESPN game log trends into OD calculation
- [x] Wire opponent defensive stats into MSF calculation

### Basic API
- [x] FastAPI project setup with proper structure
- [x] `/health` endpoint
- [x] `/players/search` endpoint
- [x] `/decide` endpoint (local scoring only)
- [x] Request/response Pydantic models
- [x] Basic error handling middleware

---

## Phase 2: Claude Integration (Week 3)
*Goal: Complex queries route to Claude with proper context*

### Decision Router
- [x] Implement query complexity classifier
- [x] Route simple queries to local engine
- [x] Route complex queries to Claude
- [x] Add query type detection (start/sit, trade, waiver, explain)

### Claude Integration
- [x] Create system prompt from SYSTEM_PROMPT.md
- [x] Build Claude API client with retry logic
- [x] Context enrichment: inject relevant player stats before calling Claude
- [x] Response parser: extract structured decision from Claude output
- [x] Streaming support for faster perceived response
- [x] Token usage tracking and cost monitoring

### Caching
- [x] Cache Claude responses for identical queries (TTL: 1 hour)
- [x] Cache common player comparisons
- [x] Implement cache invalidation on stat updates

---

## Phase 3: Mobile App MVP (Week 4-5)
*Goal: Working iOS/Android app with core decision flow*

### React Native Setup
- [x] Initialize Expo project
- [x] Configure navigation (React Navigation)
- [x] Set up state management (Zustand or Redux Toolkit)
- [x] API client setup with axios
- [x] Environment configuration (dev/staging/prod)

### Screens
- [x] **Dashboard** — Quick actions, recent decisions, league overview
- [x] **Ask BenchGoblins** — Chat interface for queries
- [x] **Roster Manager** — View/edit rosters manually
- [x] **Decision History** — Past decisions with outcomes
- [x] **Settings** — Risk mode default, notification prefs

### Components
- [x] Player card component
- [x] Decision summary card (expandable)
- [x] Risk mode selector (Floor/Median/Ceiling)
- [x] Sport selector
- [x] Loading/streaming text indicator

### UX Polish
- [x] Skeleton loaders while fetching
- [x] Pull-to-refresh on lists
- [x] Haptic feedback on decisions
- [x] Dark mode support (theme toggle with Dark/Light/System modes)

---

## Phase 4: League Integration (Week 6)
*Goal: Auto-sync rosters from fantasy platforms*

### ESPN Integration
- [x] OAuth flow for ESPN Fantasy (cookie-based auth)
- [x] Fetch user's leagues
- [x] Sync rosters automatically
- [x] Map ESPN player IDs to internal IDs

### Yahoo Integration
- [x] OAuth flow for Yahoo Fantasy
- [x] Fetch user's leagues
- [x] Sync rosters automatically
- [x] Map Yahoo player IDs to internal IDs

### Sleeper Integration
- [x] API client (no OAuth needed)
- [x] Fetch user's leagues
- [x] Sync rosters
- [x] Map Sleeper player IDs
- [x] Trending players endpoint

### Multi-Platform
- [x] Unified roster model across platforms
- [x] Conflict resolution for players on multiple platforms
- [x] Manual roster override option

---

## Phase 5: Notifications & Real-Time (Week 7)
*Goal: Push alerts for injury news, lineup changes, decision updates*

### Push Notifications
- [x] Expo Push Notifications setup (mobile + backend)
- [x] Notification permission flow
- [x] Injury alert triggers
- [x] Lineup lock reminders
- [x] Decision update alerts

### Real-Time Updates
- [x] WebSocket connection for live stat updates (during games)
- [x] Live scoring view during game windows
- [x] In-game decision adjustments ("Player X is questionable to return")

---

## Phase 6: Monetization & Scale (Week 8+)
*Goal: Sustainable business model*

### iOS App Store Setup
- [x] Configure iOS App Store settings (bundle ID, entitlements)
- [x] Add RevenueCat for subscription management
- [x] Create subscription tiers (Weekly, Monthly, Annual)
- [x] Build paywall UI with feature list
- [x] Add premium feature gating logic
- [x] Add privacy policy and terms of service screens
- [x] Add settings screen with subscription management
- [ ] Set up RevenueCat account and configure products
- [ ] Create App Store Connect app listing
- [ ] Configure in-app purchases in App Store Connect
- [ ] Submit for App Store review

### Usage Controls
- [x] Free tier: 5 queries/day
- [x] Premium tier: unlimited queries
- [x] Usage tracking and enforcement
- [ ] Stripe integration for web subscriptions (future)

### Analytics
- [x] Track decision accuracy (did user follow advice? what happened?)
- [x] A/B test different prompt variations
- [x] User engagement metrics

### Infrastructure
- [x] Deploy backend to AWS/GCP/Railway (Railway config + docs)
- [x] Set up CI/CD pipeline (GitHub Actions)
- [x] Database backups (scripts + GitHub Actions + docker-compose)
- [x] Error monitoring (Sentry)
- [x] Performance monitoring (Prometheus metrics + /metrics endpoint)

---

## Backlog / Future Ideas

- [ ] Voice input ("Who should I start at flex?")
- [x] Trade analyzer with multi-player evaluation
- [ ] Draft assistant mode
- [ ] Season-long tracking and analytics
- [ ] Social features (share decisions, league chat)
- [ ] Apple Watch companion app
- [ ] Widgets for iOS/Android home screen
- [ ] Discord bot integration
- [ ] Slack integration for league channels

---

## Current Sprint Focus

**Active:**
- [ ] Set up RevenueCat account and configure products
- [ ] Create App Store Connect app listing
- [x] User engagement metrics (session duration, feature usage, retention)

**Blocked:**
- [ ] Configure in-app purchases in App Store Connect (needs RevenueCat + App Store Connect)
- [ ] Submit for App Store review (needs IAP + listing)

**Completed This Sprint:**
- [x] Unified roster model (ESPN/Yahoo/Sleeper merge, conflict resolution, overrides)
- [x] Decision accuracy tracking (outcomes, metrics by confidence/source/sport)
- [x] Basketball Reference + Pro Football Reference scrapers
- [x] Wire trends + matchup data into scoring engine (OD/MSF now live)
- [x] MLB/NHL scoring functions (SCI, RMI, GIS for all 4 sports)
- [x] Fix missing deps in pyproject.toml (cryptography, cachetools, sentry-sdk, prometheus-client)
- [x] Fix hatch build config for editable installs
- [x] App Store review prep docs
- [x] 778 tests passing
- [x] iOS App Store configuration (bundle ID, entitlements, privacy manifests)
- [x] RevenueCat SDK integration for subscriptions
- [x] Subscription tiers and paywall UI
- [x] Free tier query limits (5/day)
- [x] Sport gating for free users (NBA only)
- [x] Settings screen with subscription management
- [x] Privacy Policy and Terms of Service screens
- [x] App Store setup documentation
- [x] Token usage tracking and cost monitoring (/usage, /budget, Prometheus)
- [x] Cache invalidation on stat updates (sync_stats.py + versioned keys)
- [x] A/B test different prompt variations (ExperimentRegistry, 4 endpoints, 2 prompts)
