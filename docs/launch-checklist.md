# Launch Checklist

## Required Environment

- Backend production flag: `ENVIRONMENT=production`
- Backend required secrets: `JWT_SECRET_KEY`, `API_KEY_ENCRYPTION_SECRET`
- Backend API key posture: `REQUIRE_USER_API_KEY=true`
- Web API base URL example: `NEXT_PUBLIC_API_URL=https://api.shunfa.example`

## Verification Commands

| Check | Command / Steps | Result | Notes |
|---|---|---|---|
| Backend dependencies | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt` | NOT RUN | |
| Backend tests | `pytest -v` | NOT RUN | |
| Ruff check | `ruff check app tests` | NOT RUN | |
| Ruff format | `ruff format --check app tests` | NOT RUN | |
| Mypy | `mypy app --ignore-missing-imports` | NOT RUN | |
| SQLite migration | `pytest tests/test_migrations.py::test_alembic_upgrade_head_on_fresh_sqlite -v` | NOT RUN | |
| Alembic downgrade | `pytest tests/test_migrations.py::test_alembic_downgrade_one_revision_and_upgrade_back_on_sqlite -v` | NOT RUN | |
| PostgreSQL migration | `POSTGRES_TEST_DATABASE_URL=postgresql://shunfa:shunfa@localhost:5432/shunfa_test pytest tests/test_migrations.py::test_alembic_upgrade_head_on_postgresql -v` | NOT RUN | |
| Web lint | `npm run lint` | NOT RUN | |
| Web build | `npm run build` in CI or local non-sandbox environment | NOT RUN | If sandbox blocks Turbopack, keep NOT RUN and record reason. |
| Manual smoke | Register -> save key -> select topic -> generate -> preview -> publish -> profile; repeated publish leaves points/streak unchanged | NOT RUN | |

## Rate Limits

- `RATE_LIMIT_DEFAULT=100/minute`
- `GENERATION_RATE_LIMIT=10/minute`
- `AI_ANALYSIS_RATE_LIMIT=10/minute`
- `PUBLISH_RATE_LIMIT=20/minute`
- Multi-instance deployments must set `RATE_LIMIT_STORAGE_URI=redis://redis:6379/0`; otherwise the launch is single-instance only.

## BYOK Redaction

- API key preview is either `...last4` for sufficiently long keys or omitted.
- `Authorization` and `X-User-Api-Key` must not appear in backend logs, Sentry events, metrics labels, or browser console output.
- Rotating `API_KEY_ENCRYPTION_SECRET` invalidates stored user keys unless key versioning is implemented.

## CST Date Boundary

- `CheckIn.date` is a persisted CST date from `get_today_cst()`.
- Reward uniqueness uses `(user_id, date)`, where `date` is the CST date.
- Do not derive reward uniqueness from UTC timestamp truncation or database server-local time.

## Migration Rollback

- Existing historical migrations should not be rewritten unless a fresh deployment cannot reach `head`.
- New or launch-touched migrations must include tested downgrade behavior.
- Production rollback prefers backup restore, traffic rollback, and forward-compatible migrations over data-destructive downgrade.
- PostgreSQL migration verification must run in CI with a PostgreSQL service container or in staging before production deployment.
