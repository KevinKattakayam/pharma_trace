# ADR-0001: Environment-driven security posture

**Status:** accepted · **Context:** audit S3, S11. `debug=True` was the default and controlled security checks; `HMAC_DAILY_SECRET` defaulted to a public string.

**Decision.** `ENVIRONMENT` (dev/test/staging/prod) decides strictness. Staging/prod refuse to start with missing, short, low-diversity or publicly known secrets, wildcard CORS, debug on, or the demo-user bypass. Dev/test replace empty secrets with per-process random values and warn. `debug` defaults to `False` and no longer gates security.

**Consequences.** A misconfigured production deploy fails fast instead of running with forgeable keys. Dev tokens do not survive restarts unless `JWT_SECRET` is set.
