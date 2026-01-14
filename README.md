# GameSpace

A fantasy sports decision engine that evaluates start/sit, waiver, and trade decisions under uncertainty.

GameSpace is **not** a prediction model. It produces probabilistic decisions using role stability, spatial opportunity, and matchup context — never guarantees.

## Philosophy

- Fantasy is a **decision problem**, not a prediction problem
- Volume ≠ safety
- Matchups are skill-specific, not opponent-wide
- Upside and downside must be explicitly separated
- Transparency > false precision

## Supported Sports

| Sport | Status |
|-------|--------|
| NBA | Primary |
| NFL | Supported |
| MLB | Beta |
| NHL | Beta |

**Not supported:** Betting picks, gambling odds, proprietary tracking data, deterministic predictions.

## Architecture

GameSpace uses a hybrid approach to balance speed, cost, and reasoning quality:

```
┌─────────────────────────────────────────────────────┐
│                 React Native App                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  Dashboard  │  │  GameSpace  │  │   Roster    │  │
│  │             │  │    Chat     │  │   Manager   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                     │
│  ┌─────────────────────────────────────────────┐   │
│  │            Decision Router                   │   │
│  │  ┌─────────────────┐  ┌─────────────────┐   │   │
│  │  │  Local Scoring  │  │   Claude API    │   │   │
│  │  │  (80% queries)  │  │  (20% queries)  │   │   │
│  │  │  - Fast         │  │  - Complex      │   │   │
│  │  │  - Free         │  │  - Nuanced      │   │   │
│  │  │  - Offline OK   │  │  - "Why?" asks  │   │   │
│  │  └─────────────────┘  └─────────────────┘   │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │              Data Layer                      │   │
│  │  ESPN API | Stats APIs | PostgreSQL         │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## Core Concepts

### Qualitative Indices

GameSpace models space and opportunity using five qualitative proxies:

| Index | Purpose | Example |
|-------|---------|---------|
| **Space Creation Index (SCI)** | How a player generates usable space | Drives, route separation, zone entries |
| **Role Motion Index (RMI)** | Dependence on motion/scheme/teammates | High = fragile if game flow changes |
| **Gravity Impact Score (GIS)** | Defensive attention drawn | Double teams, safety shading |
| **Opportunity Delta (OD)** | Change in role (not raw size) | Minutes trending up/down |
| **Matchup Space Fit (MSF)** | Opponent allows exploitable space? | Drop vs switch, zone vs man |

### Risk Modes

Users select one of three modes before receiving recommendations:

- **FLOOR** — Minimize downside. Prioritize role stability. Penalize volatility.
- **MEDIAN** — Maximize expected value. Balance all factors. *(Default)*
- **CEILING** — Maximize upside. Accept volatility for spike potential.

The same inputs produce different recommendations depending on mode.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Mobile App | React Native (iOS + Android) |
| Backend API | Python / FastAPI |
| AI Layer | Claude API (Anthropic) |
| Database | PostgreSQL |
| Cache | Redis |
| Stats Data | ESPN API, Basketball Reference |

## Quick Start

```bash
# Clone
git clone https://github.com/yourusername/GameSpace.git
cd GameSpace

# Backend setup
cd src/api
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your API keys
uvicorn main:app --reload

# Mobile setup (separate terminal)
cd src/mobile
npm install
npx expo start
```

## Project Structure

```
GameSpace/
├── README.md
├── TODO.md
├── DECISIONS.md
├── docs/
│   ├── SYSTEM_PROMPT.md      # Claude prompt specification
│   ├── API.md                # API documentation
│   └── INDICES.md            # Deep dive on qualitative indices
├── src/
│   ├── api/                  # FastAPI backend
│   │   ├── main.py
│   │   ├── routers/
│   │   ├── services/
│   │   └── models/
│   ├── core/                 # Shared logic
│   │   ├── scoring.py        # Local scoring engine
│   │   ├── indices.py        # SCI, RMI, GIS, OD, MSF calculations
│   │   └── data.py           # Stats fetching/caching
│   └── mobile/               # React Native app
│       ├── app/
│       ├── components/
│       └── services/
└── tests/
```

## Environment Variables

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
ESPN_API_KEY=...
DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379
```

## License

MIT

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
