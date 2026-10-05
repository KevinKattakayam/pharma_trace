# ADR-0002: Verified-identity rate limiting with privacy-preserving client keys

**Status:** accepted · **Context:** audit S4, S5. Limiter keys came from *unverified* JWTs (forgeable), and an IP-stripping middleware ran first, so all anonymous users shared one bucket.

**Decision.** One verified decoder (`services/security.decode_token`) for all JWT use. Authenticated requests are keyed by verified `sub`. A pure-ASGI `PrivacyMiddleware` computes `HMAC(daily_key(purpose), client_ip)` *before* removing the IP and forwarding headers from the request scope. `X-Forwarded-For` is honoured only for `TRUSTED_PROXY_HOPS`. Storage is `RATE_LIMIT_STORAGE_URI` (Redis recommended); memory storage logs a warning in staging/prod.

**Alternatives.** Storing raw IPs (rejected: DPDP/GDPR minimisation); per-user only (rejected: anonymous endpoints are the abuse surface).

**Consequences.** Limits are per client and unforgeable; no IP reaches handlers or logs. Multi-worker deployments need Redis for exact limits.
