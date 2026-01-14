# GameSpace — Decision Log

This document records architectural and design decisions with rationale. Newest entries at top.

---

## DEC-005: Risk Mode as User-Controlled Parameter
**Date:** 2025-01-14  
**Status:** Accepted  
**Context:** Fantasy decisions have different optimal strategies depending on user's situation (need ceiling to win, or protect a lead).  
**Decision:** Require explicit risk mode (Floor/Median/Ceiling) before any recommendation. Same inputs produce different outputs based on mode.  
**Rationale:** 
- Makes the system's reasoning transparent
- Gives users agency over their strategy
- Avoids one-size-fits-all recommendations
- Aligns with philosophy that fantasy is a decision problem, not prediction

**Consequences:**
- Every API call must include risk_mode parameter
- UI must make mode selection prominent and easy
- Need clear user education on what each mode means

---

## DEC-004: Qualitative Indices Over Raw Tracking Data
**Date:** 2025-01-14  
**Status:** Accepted  
**Context:** Advanced tracking data (Second Spectrum, Next Gen Stats) is proprietary and expensive. Need a way to model spatial opportunity without it.  
**Decision:** Use five qualitative indices (SCI, RMI, GIS, OD, MSF) derived from public box score and play-by-play data.  
**Rationale:**
- Public data is free and accessible
- Qualitative proxies capture the *concept* of space without needing raw coordinates
- Easier to explain to users than black-box ML
- Can improve index calculations over time without changing the interface

**Consequences:**
- Index calculations are heuristic, not precise
- Need clear documentation that these are proxies, not measurements
- Claude can reason about indices in natural language

---

## DEC-003: Hybrid Local + Claude Architecture
**Date:** 2025-01-14  
**Status:** Accepted  
**Context:** Pure Claude-for-everything is expensive ($0.01-0.03/query) and slow (2-5s latency). Pure local is fast but can't handle nuanced reasoning.  
**Decision:** Route 80% of queries (simple A vs B comparisons) to local scoring engine; route 20% (complex trades, explanations, edge cases) to Claude.  
**Rationale:**
- Controls costs at scale
- Sub-second response for common queries
- Claude's reasoning reserved for where it adds value
- Enables offline capability for basic decisions
- Natural upgrade path to premium tier

**Consequences:**
- Two code paths to maintain
- Need robust query classifier
- Must ensure local engine and Claude give consistent recommendations for overlapping cases

---

## DEC-002: React Native for Mobile
**Date:** 2025-01-14  
**Status:** Accepted  
**Context:** Need iOS and Android apps. Options: native (Swift + Kotlin), React Native, Flutter.  
**Decision:** React Native with Expo.  
**Rationale:**
- Single codebase for both platforms
- Existing experience with React Native (GuitarTabGenerator project)
- Large ecosystem and community
- Expo simplifies build/deploy process
- Can eject to bare workflow if needed later

**Alternatives Considered:**
- Native: Better performance but 2x development effort
- Flutter: Good option but less familiar, smaller ecosystem

**Consequences:**
- Some native features may require ejecting from Expo
- Performance may need optimization for real-time features

---

## DEC-001: FastAPI for Backend
**Date:** 2025-01-14  
**Status:** Accepted  
**Context:** Need a backend API to serve mobile app. Options: Node.js, FastAPI (Python), Go.  
**Decision:** FastAPI with Python.  
**Rationale:**
- Python expertise already strong
- FastAPI has excellent async support
- Native Pydantic validation
- Easy integration with data science libraries if needed
- Good documentation generation (OpenAPI)

**Alternatives Considered:**
- Node.js: Would work but less alignment with data processing needs
- Go: Better performance but slower development velocity

**Consequences:**
- Need to manage Python environment carefully
- Async patterns required for Claude API calls

---

## Template for New Decisions

```markdown
## DEC-XXX: [Title]
**Date:** YYYY-MM-DD  
**Status:** Proposed | Accepted | Deprecated | Superseded  
**Context:** What is the issue or question?  
**Decision:** What did we decide?  
**Rationale:** Why this choice?  
**Alternatives Considered:** What else was evaluated?  
**Consequences:** What are the implications?
```
