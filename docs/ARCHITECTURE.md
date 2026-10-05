# Architecture

```mermaid
flowchart LR
  U[Patient / pharmacist / health worker<br/>PWA, offline cache] -->|HTTPS| N[nginx / Vercel<br/>static + CSP]
  N -->|/api| A[FastAPI]
  subgraph API
    M[Middleware: CORS → security headers → privacy (IP→keyed pseudonym, then removed) → request context → rate limit]
    V[verify router] --> P[Pack Check / GS1 / GSR 823E parsers]
    V --> B[Batch-alert index]
    V --> L[LASA guard]
    V --> C[Verdict rules + reasons]
    V --> AU[Audit chain]
  end
  A --> M
  V -->|lookups| F[(openFDA)]
  V --> R[(CDSCO bundled SQLite)]
  V -.optional.-> S[(Manufacturer serial service)]
  AU -->|rpc append_audit_record<br/>advisory lock| DB[(PostgreSQL / Supabase)]
  A --> DB
  A --> RD[(Redis: rate limits)]
  OPS[Reviewed CSV → import_regulator_alerts] --> B
```

**Verification flow:** parse code → registry lookups → recalls (FDA + CDSCO, merged so an active recall from any source wins) → batch alerts → Pack Check → serial check (if configured) → `assess_verdict` → LASA → audit append → persist → response with reasons.

**Data stores:** Postgres in production (writes fail closed); SQLite row store in dev/offline demo (`LOCAL_STORE_PATH`).
