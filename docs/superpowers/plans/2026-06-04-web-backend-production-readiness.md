# Web Backend Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Shunfa Web + FastAPI backend launch path verifiable, safer under production settings, and ready for final smoke validation.

**Architecture:** Keep the current FastAPI + SQLAlchemy + Alembic backend and Next.js App Router Web app. Add production-readiness behavior at the boundaries: config validation, error normalization, BYOK redaction, idempotent publish, migration verification, Web API normalization, explicit timeouts, and launch runbooks. Do not redesign the product or rewrite historical migrations unless a fresh deployment cannot work without it.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, SQLite/PostgreSQL, SlowAPI, python-jose, Next.js 16, React 18, TypeScript, Tailwind CSS, pytest, ruff, mypy.

---

## File Responsibility Map

- `backend/app/config.py`: Production flags, CORS validation, timeout/rate-limit settings.
- `backend/app/rate_limit.py`: SlowAPI limiter configuration and shared-storage support.
- `backend/app/errors.py`: New backend error-code helpers and response normalization.
- `backend/app/main.py`: Exception handlers, Sentry redaction hook, middleware/router setup.
- `backend/app/middleware.py`: Request logging without sensitive headers, bodies, tokens, or API keys.
- `backend/app/dependencies.py`: API key resolution and missing-key error code.
- `backend/app/routers/user.py`: API key save/status/delete behavior and safe preview.
- `backend/app/routers/content.py`: Publish endpoint error code/status mapping and launch-critical endpoint behavior.
- `backend/app/services/content_service.py`: Atomic/idempotent publish logic.
- `backend/tests/test_config.py`: Production config, CORS, timeout/rate-limit settings tests.
- `backend/tests/test_errors.py`: Error response shape and missing API key tests.
- `backend/tests/test_user.py`: BYOK preview and plaintext non-leakage tests.
- `backend/tests/test_content.py`: Publish idempotency, duplicate publish, CST date uniqueness tests.
- `backend/tests/test_migrations.py`: SQLite upgrade/downgrade/upgrade-back tests and PostgreSQL-gated smoke test.
- `backend/requirements-dev.txt`: Local verification tools not required at runtime.
- `web/src/lib/api.ts`: Normalized frontend error model, timeout handling, no sensitive console logging.
- `web/src/lib/auth.tsx`: Expired token handling and logout cleanup.
- `web/src/app/compose/page.tsx`, `web/src/app/discuss/page.tsx`, `web/src/app/preview/page.tsx`, `web/src/app/settings/page.tsx`, `web/src/app/topics/page.tsx`: Consume normalized API errors and show recoverable timeout/missing-key states.
- `README.md`, `AGENTS.md`: Current Web + backend launch commands and architecture.
- `docs/launch-checklist.md`: Launch checklist, rollback procedure, final verification record template.

## Scope Guardrails

- Do not make Mini Program launch readiness a blocker.
- Do not rewrite historical Alembic revisions unless a fresh deploy cannot reach `head`.
- Prioritize downgrade verification for new or launch-touched migrations and the latest rollback path.
- Treat PostgreSQL migration verification as a required pre-production or CI check; if local Docker/PostgreSQL is unavailable, record it as blocked verification infrastructure, not as a code pass.
- If the Codex sandbox blocks `npm run build`, record Web build as `NOT RUN` with reason. Do not mark it as `PASS`.

---

### Task 1: Backend Verification Environment

**Files:**
- Create: `backend/requirements-dev.txt`
- Modify: `README.md`
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Add dev verification requirements**

Create `backend/requirements-dev.txt`:

```txt
-r requirements.txt
ruff>=0.9.9
mypy>=1.13.0
types-python-dateutil
pytest-cov
```

- [ ] **Step 2: Document local backend verification commands**

In `README.md`, update the backend test section to include:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

DEEPSEEK_API_KEY=test JWT_SECRET_KEY=supersecretkey123456789 \
  API_KEY_ENCRYPTION_SECRET=testencryptionsecretkey12345678 \
  pytest -v

ruff check app tests
ruff format --check app tests
mypy app --ignore-missing-imports
```

- [ ] **Step 3: Add launch checklist verification commands**

Create `docs/launch-checklist.md` with this initial structure:

```markdown
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
```

- [ ] **Step 4: Run documentation scan**

Run:

```bash
rg -n "pytest|ruff|mypy|ENVIRONMENT=production|NEXT_PUBLIC_API_URL" README.md docs/launch-checklist.md
```

Expected: command lists the new verification and environment sections.

- [ ] **Step 5: Commit**

```bash
git add -f backend/requirements-dev.txt README.md docs/launch-checklist.md
git commit -m "docs: add launch verification setup"
```

---

### Task 2: Production Config, CORS, Timeout, And Rate-Limit Settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/rate_limit.py`
- Create: `backend/tests/test_config.py`
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Write config tests first**

Create `backend/tests/test_config.py`:

```python
import pytest

from app.config import Settings


def test_production_rejects_wildcard_cors_with_authorization():
    settings = Settings(
        jwt_secret_key="x" * 32,
        environment="production",
        api_key_encryption_secret="y" * 32,
        cors_allow_origins=["*"],
    )

    with pytest.raises(ValueError, match="CORS"):
        settings.validate_cors()


def test_rate_limit_and_timeout_defaults_are_explicit():
    settings = Settings(jwt_secret_key="test-secret")

    assert settings.rate_limit_default == "100/minute"
    assert settings.generation_rate_limit == "10/minute"
    assert settings.ai_analysis_rate_limit == "10/minute"
    assert settings.publish_rate_limit == "20/minute"
    assert settings.deepseek_request_timeout_seconds == 60
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_config.py -v
```

Expected: FAIL because `rate_limit_default`, `generation_rate_limit`, `ai_analysis_rate_limit`, `publish_rate_limit`, and `deepseek_request_timeout_seconds` do not exist yet, and wildcard CORS does not raise.

- [ ] **Step 3: Add settings**

In `backend/app/config.py`, add fields to `Settings`:

```python
    rate_limit_storage_uri: str = ""
    rate_limit_default: str = "100/minute"
    generation_rate_limit: str = "10/minute"
    ai_analysis_rate_limit: str = "10/minute"
    publish_rate_limit: str = "20/minute"
    deepseek_request_timeout_seconds: int = 60
```

Update `validate_cors()` production logic:

```python
        if self.environment == "production":
            if "*" in origins:
                raise ValueError(
                    "CORS_ALLOW_ORIGINS must not contain '*' in production when Authorization headers are used."
                )
            localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
```

- [ ] **Step 4: Configure SlowAPI shared storage**

Replace `backend/app/rate_limit.py` with:

```python
"""Rate limiter configuration shared across all routers."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import settings


limiter_kwargs = {"key_func": get_remote_address, "default_limits": [settings.rate_limit_default]}
if settings.rate_limit_storage_uri:
    limiter_kwargs["storage_uri"] = settings.rate_limit_storage_uri

limiter = Limiter(**limiter_kwargs)
```

- [ ] **Step 5: Replace hardcoded launch-critical limits**

In `backend/app/routers/content.py`, update decorators:

```python
@limiter.limit(settings.generation_rate_limit)
```

for `/quick_generate`, `/generate_content`, and `/revise_content`. Use:

```python
@limiter.limit(settings.ai_analysis_rate_limit)
```

for `/review_content` and `/compose_post_assets`, and:

```python
@limiter.limit(settings.publish_rate_limit)
```

for `/confirm_publish`.

Import settings:

```python
from ..config import settings
```

In `backend/app/routers/hot_topics.py`, apply `settings.ai_analysis_rate_limit` to `/hot_topics/{topic_id}/analysis`.

- [ ] **Step 6: Update launch checklist**

Add to `docs/launch-checklist.md`:

```markdown
## Rate Limits

- `RATE_LIMIT_DEFAULT=100/minute`
- `GENERATION_RATE_LIMIT=10/minute`
- `AI_ANALYSIS_RATE_LIMIT=10/minute`
- `PUBLISH_RATE_LIMIT=20/minute`
- Multi-instance deployments must set a shared limiter backend such as `RATE_LIMIT_STORAGE_URI=redis://redis:6379/0`; otherwise the launch is single-instance only.
```

- [ ] **Step 7: Run tests and lint**

Run:

```bash
pytest tests/test_config.py -v
ruff check app tests/test_config.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/rate_limit.py backend/app/routers/content.py backend/app/routers/hot_topics.py backend/tests/test_config.py docs/launch-checklist.md
git commit -m "chore: make launch config explicit"
```

---

### Task 3: Backend Error Contract And API Key Missing Error

**Files:**
- Create: `backend/app/errors.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/dependencies.py`
- Create: `backend/tests/test_errors.py`
- Modify: `web/src/lib/api.ts`

- [ ] **Step 1: Write backend error tests first**

Create `backend/tests/test_errors.py`:

```python
from app.models import User
from app.routers.user import create_jwt_token


def test_missing_api_key_returns_error_code(client, db):
    user = User(openid="missing_api_key_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    response = client.post(
        "/api/daily_topics",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "missing_api_key"
    assert "DeepSeek" in response.json()["message"]


def test_invalid_token_returns_error_code(client):
    response = client.get("/api/user_status", headers={"Authorization": "Bearer invalid"})

    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_token"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_errors.py -v
```

Expected: FAIL because responses use FastAPI `detail` shape.

- [ ] **Step 3: Add backend error helper**

Create `backend/app/errors.py`:

```python
from fastapi import HTTPException, Request


def raise_api_error(status_code: int, error_code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "message": message},
    )


def request_id_from(request: Request) -> str | None:
    return request.headers.get("X-Request-ID")


def normalize_http_error(request: Request, exc: HTTPException) -> dict:
    detail = exc.detail
    if isinstance(detail, dict) and "error_code" in detail and "message" in detail:
        payload = {
            "error_code": str(detail["error_code"]),
            "message": str(detail["message"]),
        }
    else:
        message = str(detail)
        payload = {
            "error_code": _default_error_code(exc.status_code, message),
            "message": message,
        }
    request_id = request_id_from(request)
    if request_id:
        payload["request_id"] = request_id
    return payload


def _default_error_code(status_code: int, message: str) -> str:
    if status_code == 401:
        return "invalid_token"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 409:
        return "conflict"
    if status_code == 422:
        return "validation_error"
    if "DeepSeek API Key" in message:
        return "missing_api_key"
    return "request_failed"
```

- [ ] **Step 4: Register exception handlers**

In `backend/app/main.py`, import:

```python
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from app.errors import normalize_http_error
```

Add before the global `Exception` handler:

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=normalize_http_error(request, exc),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID")
    content = {
        "error_code": "validation_error",
        "message": "请求参数不正确",
    }
    if request_id:
        content["request_id"] = request_id
    return JSONResponse(status_code=422, content=content)
```

- [ ] **Step 5: Update missing API key dependency**

In `backend/app/dependencies.py`, import:

```python
from .errors import raise_api_error
```

Replace the final `HTTPException` raised by `get_resolved_api_key()` with:

```python
    raise_api_error(
        status_code=400,
        error_code="missing_api_key",
        message="请在设置页面配置您的 DeepSeek API Key（https://platform.deepseek.com/api_keys）",
    )
```

- [ ] **Step 6: Add frontend normalization**

In `web/src/lib/api.ts`, add:

```typescript
export interface ApiErrorData {
  error_code: string;
  message: string;
  request_id?: string;
}

export class ApiError extends Error {
  status: number;
  data: ApiErrorData;

  constructor(status: number, data: ApiErrorData) {
    super(data.message);
    this.status = status;
    this.data = data;
  }
}

function normalizeError(status: number, raw: unknown): ApiErrorData {
  if (raw && typeof raw === 'object') {
    const data = raw as { error_code?: unknown; message?: unknown; detail?: unknown; request_id?: unknown };
    if (typeof data.error_code === 'string' && typeof data.message === 'string') {
      return {
        error_code: data.error_code,
        message: data.message,
        request_id: typeof data.request_id === 'string' ? data.request_id : undefined,
      };
    }
    if (typeof data.detail === 'string') {
      return {
        error_code: status === 401 ? 'invalid_token' : 'request_failed',
        message: data.detail,
      };
    }
  }
  return {
    error_code: status === 401 ? 'invalid_token' : 'request_failed',
    message: '请求失败，请稍后重试',
  };
}

export function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.data.message;
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}
```

Update the `!res.ok` branch:

```typescript
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, normalizeError(res.status, err));
```

Update 401 branch to throw `new ApiError(401, { error_code: 'invalid_token', message: '登录已失效，请重新登录' })`.

- [ ] **Step 7: Run tests and lint**

Run:

```bash
pytest tests/test_errors.py -v
npm run lint
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/errors.py backend/app/main.py backend/app/dependencies.py backend/tests/test_errors.py web/src/lib/api.ts
git commit -m "feat: normalize launch API errors"
```

---

### Task 4: BYOK Preview, Redaction, And Logging Safety

**Files:**
- Modify: `backend/app/routers/user.py`
- Modify: `backend/app/middleware.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_user.py`
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Add API key preview tests**

Append to `backend/tests/test_user.py`:

```python
def test_api_key_status_returns_masked_preview_only(client, db):
    user = User(openid="preview_key_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    save_response = client.post(
        "/api/user/api_key",
        json={"api_key": "sk-test-secret-123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    status_response = client.get(
        "/api/user/api_key/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert save_response.status_code == 200
    assert save_response.json()["preview"] == "...3456"
    assert status_response.json()["preview"] == "...3456"
    assert "sk-test-secret" not in str(save_response.json())
    assert "sk-test-secret" not in str(status_response.json())


def test_short_api_key_status_returns_no_usable_preview(client, db):
    user = User(openid="short_key_user")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_jwt_token(user.id)

    response = client.post(
        "/api/user/api_key",
        json={"api_key": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["preview"] is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_user.py::test_api_key_status_returns_masked_preview_only tests/test_user.py::test_short_api_key_status_returns_no_usable_preview -v
```

Expected: second test FAIL because short keys currently return a last-four preview.

- [ ] **Step 3: Add preview helper**

In `backend/app/routers/user.py`, add near `_build_login_response()`:

```python
def _safe_api_key_preview(plaintext: str) -> str | None:
    key = plaintext.strip()
    if len(key) < 8:
        return None
    return f"...{key[-4:]}"
```

Replace the preview construction in `get_api_key_status()` and `save_api_key()` with `_safe_api_key_preview(plaintext)` and `_safe_api_key_preview(request.api_key.strip())`.

- [ ] **Step 4: Remove exception message from request logging**

In `backend/app/middleware.py`, replace the exception log line:

```python
                f"{method} {path} - 500 - {duration_ms:.1f}ms - EXCEPTION: {type(e).__name__}: {str(e)}"
```

with:

```python
                f"{method} {path} - 500 - {duration_ms:.1f}ms - EXCEPTION: {type(e).__name__}"
```

- [ ] **Step 5: Add Sentry scrubber**

In `backend/app/main.py`, inside the `if os.getenv("SENTRY_DSN")` block before the existing `sentry_sdk.init` call, add:

```python
        def before_send(event, hint):
            request = event.get("request") or {}
            headers = request.get("headers") or {}
            for key in list(headers.keys()):
                if key.lower() in {"authorization", "x-user-api-key"}:
                    headers[key] = "[Filtered]"
            return event
```

and pass `before_send=before_send` into the existing `sentry_sdk.init()` call.

- [ ] **Step 6: Update checklist**

Add to `docs/launch-checklist.md`:

```markdown
## BYOK Redaction

- API key preview is either `...last4` for sufficiently long keys or omitted.
- `Authorization` and `X-User-Api-Key` must not appear in backend logs, Sentry events, metrics labels, or browser console output.
- Rotating `API_KEY_ENCRYPTION_SECRET` invalidates stored user keys unless key versioning is implemented.
```

- [ ] **Step 7: Run tests and lint**

Run:

```bash
pytest tests/test_user.py -v
ruff check app tests/test_user.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/user.py backend/app/middleware.py backend/app/main.py backend/tests/test_user.py docs/launch-checklist.md
git commit -m "fix: protect byok preview and logs"
```

---

### Task 5: Publish Idempotency And CST-Date Reward Boundary

**Files:**
- Modify: `backend/app/services/content_service.py`
- Modify: `backend/app/routers/content.py`
- Modify: `backend/tests/test_content.py`
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Add duplicate publish tests**

Append to `backend/tests/test_content.py`:

```python
def test_duplicate_publish_does_not_double_count_rewards(user, checkin, client, db):
    token = create_jwt_token(user.id)
    checkin.status = CheckInStatus.pending
    checkin.content = "准备发布的内容"
    db.commit()

    first = client.post(
        "/api/confirm_publish",
        json={"checkin_id": checkin.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    second = client.post(
        "/api/confirm_publish",
        json={"checkin_id": checkin.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    db.refresh(user)
    db.refresh(checkin)
    assert user.points == first.json()["total_points"]
    assert checkin.points_earned == first.json()["points_earned"]


def test_checkin_date_uses_persisted_cst_date(user, db):
    today = get_today_cst()
    checkin = CheckIn(
        user_id=user.id,
        date=today,
        topic="CST boundary topic",
        status=CheckInStatus.topic_selected,
        refresh_count=0,
    )
    db.add(checkin)
    db.commit()

    assert checkin.date == today
```

- [ ] **Step 2: Run duplicate tests to verify current behavior**

Run:

```bash
pytest tests/test_content.py::test_duplicate_publish_does_not_double_count_rewards tests/test_content.py::test_checkin_date_uses_persisted_cst_date -v
```

Expected: duplicate publish test should FAIL until the endpoint returns 409 for already completed checkins.

- [ ] **Step 3: Add publish exception and conditional publish claim**

In `backend/app/services/content_service.py`, add above `confirm_publish()`:

```python
class AlreadyPublishedError(ValueError):
    """Raised when a checkin has already been published."""
```

Change the start of `confirm_publish()` to keep the existing completed guard and then claim a pending checkin with a conditional update before rewards are calculated:

```python
    if checkin.status == CheckInStatus.completed:
        raise AlreadyPublishedError("今日已完成发布，请勿重复提交")
    if checkin.status != CheckInStatus.pending:
        raise ValueError("请先确认内容后再发布")
```

After `today = get_today_cst()` and before `calculate_and_update_streak(...)`, add:

```python
        publish_started_at = get_now_cst()
        claimed = (
            db.query(CheckIn)
            .filter(
                CheckIn.id == checkin.id,
                CheckIn.user_id == user.id,
                CheckIn.status == CheckInStatus.pending,
            )
            .update(
                {
                    CheckIn.status: CheckInStatus.completed,
                    CheckIn.completed_at: publish_started_at,
                },
                synchronize_session=False,
            )
        )
        if claimed != 1:
            db.rollback()
            current = (
                db.query(CheckIn)
                .filter(CheckIn.id == checkin.id, CheckIn.user_id == user.id)
                .first()
            )
            if current and current.status == CheckInStatus.completed:
                raise AlreadyPublishedError("今日已完成发布，请勿重复提交")
            raise ValueError("请先确认内容后再发布")
        db.flush()
        db.refresh(checkin)
```

Remove the duplicate status assignment block:

```python
        checkin.status = CheckInStatus.completed
        checkin.completed_at = get_now_cst()
        db.flush()
```

Keep the existing single final `db.commit()` after achievements are checked. This preserves rollback if points or achievements fail after the conditional claim.

- [ ] **Step 4: Return 409 from publish endpoint**

In `backend/app/routers/content.py`, import:

```python
from ..services.content_service import AlreadyPublishedError, confirm_publish
```

Update `confirm_publish_endpoint()`:

```python
    try:
        result = await confirm_publish(checkin, db, current_user)
        return PublishResponse(**result)
    except AlreadyPublishedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
```

- [ ] **Step 5: Add CST uniqueness checklist**

Add to `docs/launch-checklist.md`:

```markdown
## CST Date Boundary

- `CheckIn.date` is a persisted CST date from `get_today_cst()`.
- Reward uniqueness uses `(user_id, date)`, where `date` is the CST date.
- Do not derive reward uniqueness from UTC timestamp truncation or database server-local time.
```

- [ ] **Step 6: Run tests**

Run:

```bash
pytest tests/test_content.py::test_duplicate_publish_does_not_double_count_rewards tests/test_content.py::test_checkin_date_uses_persisted_cst_date -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/content_service.py backend/app/routers/content.py backend/tests/test_content.py docs/launch-checklist.md
git commit -m "fix: make publish duplicate-safe"
```

---

### Task 6: Alembic Downgrade And PostgreSQL Migration Verification

**Files:**
- Modify: `backend/tests/test_migrations.py`
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Add SQLite downgrade/upgrade-back test**

Replace `backend/tests/test_migrations.py` with:

```python
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import settings


ALEMBIC_INI = str(Path(__file__).resolve().parents[1] / "alembic.ini")


def _alembic_config(database_url: str) -> Config:
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _assert_head_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    inspector = inspect(engine)
    checkin_columns = {column["name"] for column in inspector.get_columns("checkins")}

    assert "hot_topics" in inspector.get_table_names()
    assert "reminder_deliveries" in inspector.get_table_names()
    assert {"topic_source", "topic_url", "topic_summary", "topic_published_at"} <= checkin_columns


def test_alembic_upgrade_head_on_fresh_sqlite(tmp_path):
    db_path = tmp_path / "migration_smoke.db"
    database_url = f"sqlite:///{db_path}"
    original_database_url = settings.database_url
    settings.database_url = database_url

    try:
        command.upgrade(_alembic_config(database_url), "head")
        _assert_head_schema(database_url)
    finally:
        settings.database_url = original_database_url


def test_alembic_downgrade_one_revision_and_upgrade_back_on_sqlite(tmp_path):
    db_path = tmp_path / "migration_downgrade_smoke.db"
    database_url = f"sqlite:///{db_path}"
    cfg = _alembic_config(database_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")

    _assert_head_schema(database_url)


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL"),
    reason="POSTGRES_TEST_DATABASE_URL is required for production-like migration verification",
)
def test_alembic_upgrade_head_on_postgresql():
    database_url = os.environ["POSTGRES_TEST_DATABASE_URL"]
    command.upgrade(_alembic_config(database_url), "head")
    _assert_head_schema(database_url)
```

- [ ] **Step 2: Run migration tests**

Run:

```bash
pytest tests/test_migrations.py -v
```

Expected: SQLite tests PASS; PostgreSQL test SKIPPED unless `POSTGRES_TEST_DATABASE_URL` is set.

- [ ] **Step 3: Update launch checklist migration section**

Add:

```markdown
## Migration Rollback

- Existing historical migrations should not be rewritten unless a fresh deployment cannot reach `head`.
- New or launch-touched migrations must include tested downgrade behavior.
- Production rollback prefers backup restore, traffic rollback, and forward-compatible migrations over data-destructive downgrade.
- PostgreSQL migration verification must run in CI with a PostgreSQL service container or in staging before production deployment.
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_migrations.py docs/launch-checklist.md
git commit -m "test: verify launch migration paths"
```

---

### Task 7: Web API Timeout And Error Consumption

**Files:**
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/app/compose/page.tsx`
- Modify: `web/src/app/discuss/page.tsx`
- Modify: `web/src/app/preview/page.tsx`
- Modify: `web/src/app/settings/page.tsx`
- Modify: `web/src/app/topics/page.tsx`
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Add configurable timeout to API client**

In `web/src/lib/api.ts`, add:

```typescript
const DEFAULT_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS ?? 30000);
const GENERATION_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_GENERATION_TIMEOUT_MS ?? 90000);

interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}
```

Change `request<T>` signature:

```typescript
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
```

Inside `request`, before `fetch`:

```typescript
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
```

Replace fetch with:

```typescript
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...options, headers, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, {
        error_code: 'request_timeout',
        message: '生成时间较长，请稍后刷新草稿或重试。',
      });
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
```

Update `api.post`:

```typescript
  post: <T>(path: string, data?: unknown, options: RequestOptions = {}) =>
    request<T>(path, { ...options, method: 'POST', body: data ? JSON.stringify(data) : undefined }),
  postGeneration: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: data ? JSON.stringify(data) : undefined, timeoutMs: GENERATION_TIMEOUT_MS }),
```

- [ ] **Step 2: Use generation timeout for AI endpoints**

In Web pages, replace `api.post` with `api.postGeneration` for:

- `/api/hot_topics/{topic_id}/analysis`
- `/api/daily_topics`
- `/api/quick_generate`
- `/api/generate_content`
- `/api/confirm_content`
- `/api/review_content`
- `/api/revise_content`
- `/api/compose_post_assets`

Do not use `postGeneration` for `/api/confirm_publish`.

- [ ] **Step 3: Use normalized error messages**

Import `getErrorMessage` where needed:

```typescript
import { api, getErrorMessage } from '@/lib/api';
```

Replace catch blocks shaped like:

```typescript
const err = e as { data?: { detail?: string } };
setError(err?.data?.detail ?? '发布失败，请重试');
```

with:

```typescript
setError(getErrorMessage(e, '发布失败，请重试'));
```

- [ ] **Step 4: Update launch checklist timeout section**

Add:

```markdown
## Timeout Policy

- `NEXT_PUBLIC_API_TIMEOUT_MS=30000`
- `NEXT_PUBLIC_GENERATION_TIMEOUT_MS=90000`
- `DEEPSEEK_REQUEST_TIMEOUT_SECONDS=60`
- Client timeout does not prove backend work stopped. Generation retries must reuse the existing non-completed `CheckIn`.
- Publish is not automatically retried after timeout.
```

- [ ] **Step 5: Run Web lint and build**

Run:

```bash
npm run lint
npm run build
```

Expected: PASS in CI or local non-sandbox environment. If sandbox blocks build, record build as NOT RUN with sandbox reason.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/api.ts web/src/app/compose/page.tsx web/src/app/discuss/page.tsx web/src/app/preview/page.tsx web/src/app/settings/page.tsx web/src/app/topics/page.tsx docs/launch-checklist.md
git commit -m "feat: add web timeout and error normalization"
```

---

### Task 8: Rendering Safety And Launch-Path Smoke Documentation

**Files:**
- Modify: `docs/launch-checklist.md`
- Modify: `AGENTS.md`
- Modify: `README.md`

- [ ] **Step 1: Verify unsafe HTML usage**

Run:

```bash
rg -n "dangerouslySetInnerHTML|innerHTML" web/src
```

Expected: no launch-critical generated-content rendering uses `dangerouslySetInnerHTML` or raw `innerHTML`. If matches exist, inspect and replace with text rendering or a reviewed sanitizer.

- [ ] **Step 2: Add rendering safety checklist**

Add to `docs/launch-checklist.md`:

```markdown
## Rendering Safety

- Generated content renders as escaped React text.
- Launch-critical pages do not use `dangerouslySetInnerHTML` for generated content.
- Browser console logging must not include JWTs, API keys, Authorization headers, or raw sensitive error objects.
```

- [ ] **Step 3: Update `AGENTS.md` architecture summary**

Replace Mini Program-first launch instructions with this Web + backend summary, preserving only sections that still describe current backend models, points, and AI prompt behavior:

    # 顺发 (Shunfa) — 开发指南

    顺发当前上线目标是 Web + FastAPI 后端闭环：注册/登录、BYOK DeepSeek API Key、热点/选题、生成/讨论、预览发布、积分/连胜、个人页状态更新。

    ## 快速启动

    后端：
    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements-dev.txt
    alembic upgrade head
    uvicorn app.main:app --reload --port 8080

    Web：
    cd web
    npm install
    npm run dev

    验证：
    cd backend
    pytest -v
    ruff check app tests
    ruff format --check app tests
    mypy app --ignore-missing-imports
    cd ../web
    npm run lint
    npm run build

Remove Mini Program-only launch instructions from `AGENTS.md`. Keep Mini Program references only if they are explicitly marked as non-launch or legacy.

- [ ] **Step 4: Update README launch checklist pointer**

Add to `README.md` deployment section:

```markdown
Before production deployment, complete [docs/launch-checklist.md](docs/launch-checklist.md). The checklist includes migration rollback, PostgreSQL verification, BYOK redaction, timeout policy, rate limits, Web build, and manual smoke validation.
```

- [ ] **Step 5: Commit**

```bash
git add -f docs/launch-checklist.md AGENTS.md README.md
git commit -m "docs: align launch runbook with web backend"
```

---

### Task 9: Final Verification Pass

**Files:**
- Modify: `docs/launch-checklist.md`

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
pytest -v
```

Expected: PASS. If backend dependencies are missing, create `.venv` and install `requirements-dev.txt` first.

- [ ] **Step 2: Run backend lint and types**

Run:

```bash
cd backend
ruff check app tests
ruff format --check app tests
mypy app --ignore-missing-imports
```

Expected: PASS.

- [ ] **Step 3: Run migration verification**

Run:

```bash
cd backend
pytest tests/test_migrations.py -v
```

Expected: SQLite upgrade and downgrade/upgrade-back PASS. PostgreSQL test PASS if `POSTGRES_TEST_DATABASE_URL` is set; otherwise SKIPPED and checklist records staging/CI requirement.

- [ ] **Step 4: Run Web verification**

Run:

```bash
cd web
npm run lint
npm run build
```

Expected: lint PASS. Build PASS in CI or local non-sandbox environment. If sandbox blocks build, checklist records NOT RUN with sandbox reason.

- [ ] **Step 5: Fill final verification record**

Update `docs/launch-checklist.md` final verification table with real results from this task. Use only:

- `PASS` when the command ran and passed.
- `FAIL` when the command ran and failed.
- `SKIPPED` when a test intentionally skipped, such as PostgreSQL URL not set.
- `NOT RUN` when environment prevented running a command.

- [ ] **Step 6: Commit verification record**

```bash
git add -f docs/launch-checklist.md
git commit -m "docs: record launch verification results"
```

---

## Plan Self-Review

Spec coverage:

- Endpoint matrix: Tasks 3, 5, 7, and 9.
- Publish state model and CST uniqueness: Task 5.
- Migration rollback and PostgreSQL verification: Task 6 and Task 9.
- BYOK security boundary: Task 4.
- Auth/session behavior: Task 3 and Task 7 rely on existing `auth.tsx`; Task 8 documents it.
- AI timeout, rate limits, cost controls: Task 2 and Task 7.
- Error normalization: Task 3 and Task 7.
- Rendering safety: Task 8.
- Final verification record: Task 9.

Implementation boundaries:

- Historical migrations are not rewritten.
- Mini Program readiness is not part of this plan.
- Web design is not redesigned.
- Web build cannot be marked PASS unless it actually runs and passes.
