# Launch Checklist

## Required Environment

- Backend production flag: `ENVIRONMENT=production`
- Backend required secrets: `JWT_SECRET_KEY`, `API_KEY_ENCRYPTION_SECRET`
- Backend API key posture: `REQUIRE_USER_API_KEY=true`
- Backend DeepSeek URL: `DEEPSEEK_BASE_URL=https://api.deepseek.com` in production; local smoke may use `http://127.0.0.1:1081/v1`
- Web API base URL example: `NEXT_PUBLIC_API_URL=https://api.shunfa.example`

## Verification Commands

| Check | Command / Steps | Result | Notes |
|---|---|---|---|
| Backend dependencies | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt` | PASS | Verified with `/private/tmp/shunfa-backend-venv` and `requirements-dev.txt`. |
| Backend tests | `pytest -v` | PASS | `186 passed, 1 skipped`; PostgreSQL migration test intentionally skipped in local full test run. |
| Ruff check | `ruff check app tests` | PASS | |
| Ruff format | `ruff format --check app tests` | PASS | |
| Mypy | `mypy app --ignore-missing-imports` | PASS | Uses `backend/mypy.ini`; SQLAlchemy model typing remains a future hardening area. |
| SQLite migration | `pytest tests/test_migrations.py::test_alembic_upgrade_head_on_fresh_sqlite -v` | PASS | Also covered by full `tests/test_migrations.py`. |
| Alembic downgrade | `pytest tests/test_migrations.py::test_alembic_downgrade_one_revision_and_upgrade_back_on_sqlite -v` | PASS | Downgrade one revision and upgrade back passed on SQLite. |
| PostgreSQL migration | `POSTGRES_TEST_DATABASE_URL=postgresql://shunfa:shunfa@localhost:5432/shunfa_test pytest tests/test_migrations.py::test_alembic_upgrade_head_on_postgresql -v` | CI CONFIGURED / LOCAL SKIPPED | `.github/workflows/backend-test.yml` now provides a PostgreSQL service container and `POSTGRES_TEST_DATABASE_URL`. Local run remains skipped because the variable was unset and Docker daemon was not running. CI/staging must produce the final PASS before production. |
| Web lint | `npm run lint` | PASS | Also configured in `.github/workflows/web-test.yml`. |
| Web build | `npm run build` in CI or local non-sandbox environment | PASS | Ran successfully in this environment with Next.js/Turbopack; also configured in `.github/workflows/web-test.yml`. |
| Scripted launch smoke | `pytest tests/test_launch_smoke.py -v` | PASS | Covers register -> save key -> select topic -> generate -> preview -> compose assets -> publish -> profile with mocked AI providers; duplicate publish leaves points/streak unchanged. |
| Mock DeepSeek service | `python -m scripts.mock_deepseek_server --port 1081`, then POST `/v1/chat/completions` | PASS | Verified locally with HTTP 200 and OpenAI-compatible `choices[0].message.content`; sandbox required elevated local loopback access. Use `DEEPSEEK_BASE_URL=http://127.0.0.1:1081/v1` for local smoke. |
| Browser smoke with mock DeepSeek | Start mock DeepSeek on `1081`, backend on `8080`, Web on `3000`, run `npx playwright install chromium`, then run `TARGET_URL=http://127.0.0.1:3000 npm run smoke:browser` from `web/` | PASS / CI CONFIGURED | Verified locally through the Playwright runner and configured in `.github/workflows/launch-smoke.yml`, which installs Chromium before running. Flow: register -> save key -> select topic -> generate -> preview -> compose assets -> publish -> profile. Console error count: 0. Local direct npm-script rerun requires a completed Playwright browser install. |
| Real DeepSeek browser smoke | Register -> save key -> select topic -> generate -> preview -> publish -> profile; repeated publish leaves points/streak unchanged | NOT RUN | Requires browser/API smoke against a configured runtime and real/sandbox DeepSeek key. |

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

## Timeout Policy

- `NEXT_PUBLIC_API_TIMEOUT_MS=30000`
- `NEXT_PUBLIC_GENERATION_TIMEOUT_MS=90000`
- `DEEPSEEK_REQUEST_TIMEOUT_SECONDS=60`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com` by default; only point it at the mock server for local/CI smoke.
- Client timeout does not prove backend work stopped. Generation retries must reuse the existing non-completed `CheckIn`.
- Publish is not automatically retried after timeout.

## Rendering Safety

- Generated content renders as escaped React text.
- Launch-critical pages do not use `dangerouslySetInnerHTML` for generated content.
- Browser console logging must not include JWTs, API keys, Authorization headers, or raw sensitive error objects.
