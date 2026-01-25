# GameSpace — Development TODO

## Phase 1: Foundation (Week 1-2)
*Goal: Local scoring engine works for simple A vs B comparisons*

### Data Layer
- [x] Set up PostgreSQL schema for players, stats, rosters
- [x] Build ESPN API client for player data
- [ ] Create nightly stats sync job (cron or scheduled task)
- [x] Implement Redis caching layer for hot player data
- [ ] Add Basketball Reference scraper for advanced stats (NBA)
- [ ] Add Pro Football Reference scraper (NFL)

### Core Scoring Engine
- [ ] Implement `Player` data model with all required fields
- [ ] Build Space Creation Index (SCI) calculator
- [ ] Build Role Motion Index (RMI) calculator
- [ ] Build Gravity Impact Score (GIS) calculator
- [ ] Build Opportunity Delta (OD) calculator
- [ ] Build Matchup Space Fit (MSF) calculator
- [ ] Create composite scoring function with risk mode weights
- [ ] Write unit tests for each index calculation

### Basic API
- [ ] FastAPI project setup with proper structure
- [ ] `/health` endpoint
- [ ] `/players/search` endpoint
- [ ] `/decide` endpoint (local scoring only)
- [ ] Request/response Pydantic models
- [ ] Basic error handling middleware

---

## Phase 2: Claude Integration (Week 3)
*Goal: Complex queries route to Claude with proper context*

### Decision Router
- [ ] Implement query complexity classifier
- [ ] Route simple queries to local engine
- [ ] Route complex queries to Claude
- [ ] Add query type detection (start/sit, trade, waiver, explain)

### Claude Integration
- [ ] Create system prompt from SYSTEM_PROMPT.md
- [ ] Build Claude API client with retry logic
- [ ] Context enrichment: inject relevant player stats before calling Claude
- [ ] Response parser: extract structured decision from Claude output
- [ ] Streaming support for faster perceived response
- [ ] Token usage tracking and cost monitoring

### Caching
- [ ] Cache Claude responses for identical queries (TTL: 1 hour)
- [ ] Cache common player comparisons
- [ ] Implement cache invalidation on stat updates

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
- [x] **Ask GameSpace** — Chat interface for queries
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
- [ ] OAuth flow for Yahoo Fantasy
- [ ] Fetch user's leagues
- [ ] Sync rosters automatically
- [ ] Map Yahoo player IDs to internal IDs

### Sleeper Integration
- [x] API client (no OAuth needed)
- [x] Fetch user's leagues
- [x] Sync rosters
- [x] Map Sleeper player IDs
- [x] Trending players endpoint

### Multi-Platform
- [ ] Unified roster model across platforms
- [ ] Conflict resolution for players on multiple platforms
- [ ] Manual roster override option

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
- [ ] WebSocket connection for live stat updates (during games)
- [ ] Live scoring view during game windows
- [ ] In-game decision adjustments ("Player X is questionable to return")

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
- [ ] Track decision accuracy (did user follow advice? what happened?)
- [ ] A/B test different prompt variations
- [ ] User engagement metrics

### Infrastructure
- [x] Deploy backend to AWS/GCP/Railway (Railway config + docs)
- [x] Set up CI/CD pipeline (GitHub Actions)
- [x] Database backups (scripts + GitHub Actions + docker-compose)
- [x] Error monitoring (Sentry)
- [ ] Performance monitoring

---

## Backlog / Future Ideas

- [ ] Voice input ("Who should I start at flex?")
- [ ] Trade analyzer with multi-player evaluation
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
- [ ] Test subscription flow in sandbox environment

**Blocked:**
- *Nothing yet*

**Completed This Sprint:**
- [x] iOS App Store configuration (bundle ID, entitlements, privacy manifests)
- [x] RevenueCat SDK integration for subscriptions
- [x] Subscription tiers and paywall UI
- [x] Free tier query limits (5/day)
- [x] Sport gating for free users (NBA only)
- [x] Settings screen with subscription management
- [x] Privacy Policy and Terms of Service screens
- [x] App Store setup documentation
