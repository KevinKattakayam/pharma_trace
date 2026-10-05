# Security policy

**Reporting a vulnerability:** email the maintainers privately (set a security contact before launch) with steps to reproduce. Do not open public issues for vulnerabilities. We aim to acknowledge within 3 working days.

**In scope:** authentication/authorisation bypass, audit-chain tampering, data exposure, injection, anything that could make the app show a false "verified" or hide a recall.

**Controls in place:** verified-JWT auth with roles; tenant guards; keyed client pseudonyms; Redis-backed rate limits; strict config validation in staging/prod; escaped upstream queries; append-only audit chain with DB triggers; security headers and CSP; CI with Bandit, pip-audit, npm audit, gitleaks and Trivy.
