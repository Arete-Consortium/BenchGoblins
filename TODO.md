# GameSpace — Development TODO

## Phase 1: Foundation (Week 1-2)
*Goal: Local scoring engine works for simple A vs B comparisons*

### Data Layer
- [ ] Set up PostgreSQL schema for players, stats, rosters
- [ ] Build ESPN API client for player data
- [ ] Create nightly stats sync job (cron or scheduled task)
- [ ] Implement Redis caching layer for hot player data
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
- [ ] Initialize Expo project
- [ ] Configure navigation (React Navigation)
- [ ] Set up state management (Zustand or Redux Toolkit)
- [ ] API client setup with axios
- [ ] Environment configuration (dev/staging/prod)

### Screens
- [ ] **Dashboard** — Quick actions, recent decisions, league overview
- [ ] **Ask GameSpace** — Chat interface for queries
- [ ] **Roster Manager** — View/edit rosters manually
- [ ] **Decision History** — Past decisions with outcomes
- [ ] **Settings** — Risk mode default, notification prefs

### Components
- [ ] Player card component
- [ ] Decision summary card (expandable)
- [ ] Risk mode selector (Floor/Median/Ceiling)
- [ ] Sport selector
- [ ] Loading/streaming text indicator

### UX Polish
- [ ] Skeleton loaders while fetching
- [ ] Pull-to-refresh on lists
- [ ] Haptic feedback on decisions
- [ ] Dark mode support

---

## Phase 4: League Integration (Week 6)
*Goal: Auto-sync rosters from fantasy platforms*

### ESPN Integration
- [ ] OAuth flow for ESPN Fantasy
- [ ] Fetch user's leagues
- [ ] Sync rosters automatically
- [ ] Map ESPN player IDs to internal IDs

### Yahoo Integration
- [ ] OAuth flow for Yahoo Fantasy
- [ ] Fetch user's leagues
- [ ] Sync rosters automatically
- [ ] Map Yahoo player IDs to internal IDs

### Sleeper Integration
- [ ] API client (no OAuth needed)
- [ ] Fetch user's leagues
- [ ] Sync rosters
- [ ] Map Sleeper player IDs

### Multi-Platform
- [ ] Unified roster model across platforms
- [ ] Conflict resolution for players on multiple platforms
- [ ] Manual roster override option

---

## Phase 5: Notifications & Real-Time (Week 7)
*Goal: Push alerts for injury news, lineup changes, decision updates*

### Push Notifications
- [ ] Firebase Cloud Messaging setup
- [ ] Notification permission flow
- [ ] Injury alert triggers
- [ ] Lineup lock reminders
- [ ] "Your player is trending down" alerts

### Real-Time Updates
- [ ] WebSocket connection for live stat updates (during games)
- [ ] Live scoring view during game windows
- [ ] In-game decision adjustments ("Player X is questionable to return")

---

## Phase 6: Monetization & Scale (Week 8+)
*Goal: Sustainable business model*

### Usage Controls
- [ ] Free tier: 5 Claude queries/day
- [ ] Premium tier: unlimited Claude queries
- [ ] Stripe integration for subscriptions
- [ ] Usage tracking and enforcement

### Analytics
- [ ] Track decision accuracy (did user follow advice? what happened?)
- [ ] A/B test different prompt variations
- [ ] User engagement metrics

### Infrastructure
- [ ] Deploy backend to AWS/GCP/Railway
- [ ] Set up CI/CD pipeline
- [ ] Database backups
- [ ] Error monitoring (Sentry)
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
- [ ] *Next task goes here*

**Blocked:**
- *Nothing yet*

**Completed This Sprint:**
- *Nothing yet*
