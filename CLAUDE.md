# CLAUDE.md — BenchGoblins

## Project Overview

A fantasy sports decision engine that evaluates start/sit, waiver, and trade decisions under uncertainty.

## Current State

- **Language**: Python
- **Files**: 385 across 7 languages
- **Lines**: 116,586

## Architecture

```
BenchGoblins/
├── .github/
│   └── workflows/
├── .vercel/
├── data/
│   └── migrations/
├── docs/
│   └── legal/
├── scripts/
│   └── config/
├── src/
│   ├── api/
│   ├── core/
│   ├── mobile/
│   ├── protocols/
│   └── web/
├── tests/
├── .dockerignore
├── .env.example
├── .gitignore
├── .gitleaks.toml
├── .pre-commit-config.yaml
├── CLAUDE.md
├── DECISIONS.md
├── DEPLOYMENT.md
├── Dockerfile
├── LICENSE
├── README.md
├── docker-compose.yml
├── fly.toml
├── pytest.ini
├── railway.toml
├── requirements-dev.txt
```

## Tech Stack

- **Language**: Python, TypeScript, SQL, HTML, JavaScript, Shell, CSS
- **Runtime**: Docker
- **CI/CD**: GitHub Actions

## Coding Standards

- **Naming**: snake_case
- **Quote Style**: double quotes
- **Type Hints**: present
- **Docstrings**: google style
- **Imports**: absolute
- **Path Handling**: os.path
- **Line Length (p95)**: 79 characters
- **Error Handling**: Custom exception classes present

## Common Commands

```bash
# docker CMD
["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port $PORT"]
```

## Anti-Patterns (Do NOT Do)

- Do NOT commit secrets, API keys, or credentials
- Do NOT skip writing tests for new code
- Do NOT use `any` type — define proper type interfaces
- Do NOT use `var` — use `const` or `let`
- Do NOT use `os.path` — use `pathlib.Path` everywhere
- Do NOT use bare `except:` — catch specific exceptions
- Do NOT use mutable default arguments
- Do NOT use `print()` for logging — use the `logging` module
- Do NOT hardcode secrets in Dockerfiles — use environment variables
- Do NOT use `latest` tag — pin specific versions

## Domain Context

### Key Models/Classes
- `APIClient`
- `AccuracyLeader`
- `AccuracyMetrics`
- `AccuracyResponse`
- `AccuracyTracker`
- `ActivityResponse`
- `AdvancedNBAStats`
- `AdvancedNFLStats`
- `AlertCategory`
- `AlertSeverity`
- `ApplyReferralRequest`
- `ApplyReferralResponse`
- `AuthResponse`
- `AuthServiceError`
- `AuthStatusResponse`

### Domain Terms
- AI
- Basketball Reference
- CEILING
- CONTRIBUTING
- Contributing See
- Core Concepts
- DECISIONS
- Data Layer
- Decision Router
- ESPN

### API Endpoints
- `/`
- `/accuracy`
- `/accuracy/metrics`
- `/accuracy/outcome/{decision_id}`
- `/accuracy/outcomes`
- `/accuracy/reset`
- `/accuracy/sync`
- `/apply`
- `/billing/create-checkout`
- `/billing/create-portal`
- `/billing/prices`
- `/billing/status`
- `/billing/webhook`
- `/budget`
- `/budget/alerts`

### Enums/Constants
- `ACCENT`
- `ADMIN_KEY`
- `AMBIGUOUS`
- `API_BASE`
- `ASC_BASE`
- `AUTH_TOKEN_KEY`
- `BACKGROUND`
- `BBALL_REF_BASE`
- `BENCH`
- `BUNDLE_ID`

### Outstanding Items
- **NOTE**: This file should not be edited (`src/web/next-env.d.ts`)

## Git Conventions

- Commit messages: Conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`)
- Branch naming: `feat/description`, `fix/description`
- Run tests before committing
