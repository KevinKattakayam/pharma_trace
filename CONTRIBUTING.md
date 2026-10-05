# Contributing

1. `make setup`, then branch from `main`.
2. Every change ships with tests; `make test lint security` must pass (CI enforces it).
3. Safety-critical modules (`services/confidence.py`, `audit.py`, `security.py`, `pack_check.py`, `batch_alerts.py`, `gs1.py`) need ≥80 % coverage and reviewer sign-off.
4. **Never** weaken a safety control to make a test pass. Never add code that labels a pack genuine without an authoritative serial check, changes doses, or diagnoses.
5. Clinical/regulatory text must cite a source; sample data must be labelled `SAMPLE`.
6. Significant design changes need an ADR in `docs/adr/`; update `CHANGELOG.md`.
7. Legacy lint debt may only go down (`scripts/lint_ratchet.sh`); lower `backend/.ruff-baseline` when you fix some.
