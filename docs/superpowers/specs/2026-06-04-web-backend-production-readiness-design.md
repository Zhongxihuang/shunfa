# Web + Backend Production Readiness Design

Date: 2026-06-04

## Goal

Bring Shunfa's Web + backend path to a launchable, verifiable standard. The release must support a complete user loop: register or log in, configure a DeepSeek API key, choose a hot topic or topic, generate content, preview it, confirm publish, and see points, streak, and profile state update.

## Scope

This release covers:

- FastAPI backend production readiness for the Web product.
- Next.js Web app readiness for the core writing loop.
- BYOK API key flow, including missing-key errors and stored-key behavior.
- Database migration confidence for a fresh deployment.
- CI and local verification commands that can be run before deployment.
- Documentation that matches the current Web + backend architecture.

This release does not cover:

- WeChat Mini Program launch readiness.
- New product surfaces beyond the current Web writing loop.
- A visual redesign of the Web app.
- Real WeChat subscription messages.
- Paid billing, teams, or multi-tenant administration.

Mini Program files may be touched only if they share code with the Web/backend path or if stale documentation would mislead deployment.

## Current Baseline

The repository already includes several production-oriented pieces:

- FastAPI backend with request logging, request IDs, Sentry support, rate limiting, health check, metrics disabled in production by default, Alembic migrations, Dockerfile, and a production start script.
- Web app using Next.js with the current routes for compose, topics, discuss, preview, profile, settings, login, drafts, and history.
- BYOK DeepSeek API key support with request header, stored encrypted key, and optional system fallback.
- Backend tests and migration smoke tests in the repository.
- GitHub Actions for backend test, lint, format, and type check.

Observed gaps from the baseline audit:

- The local backend verification environment is not currently ready: `pytest` and `ruff` are not installed in the active Python interpreter.
- Web `npm run lint` passes.
- Web `npm run build` passes when run outside the sandbox; the sandbox blocks Turbopack process or port binding.
- README reflects the newer Web + backend direction, while AGENTS.md still describes the older Mini Program-centered MVP.
- The working tree contains many existing uncommitted changes, so implementation must avoid unrelated reversions.

## Release Strategy

Use a closure-first approach. Prioritize the smallest set of changes that makes the core Web + backend loop reliable and easy to verify.

Order of work:

1. Establish backend verification so tests, lint, and type checks can run predictably.
2. Fix backend blockers found by those checks.
3. Verify and patch the Web core loop without broad UI redesign.
4. Add or update smoke coverage for the launch path.
5. Align deployment docs and runbook with the actual architecture.
6. Produce a final verification record before calling the release ready.

## Backend Design

### Configuration

Production startup must reject weak secrets:

- `JWT_SECRET_KEY` must be at least 32 characters in production.
- `API_KEY_ENCRYPTION_SECRET` must be changed from the default and at least 32 characters in production.

Production checks are gated by the project's canonical environment flag, currently `ENVIRONMENT=production` mapped to `settings.environment == "production"`. The deployment checklist must document this flag explicitly.

Production CORS must be explicit. Localhost origins should be treated as a release warning at minimum, and the deployment checklist must require a real Web origin. Production CORS must not use wildcard origins when bearer `Authorization` headers or credentials are used.

`REQUIRE_USER_API_KEY=true` is the default launch posture. System-level `DEEPSEEK_API_KEY` remains allowed only when explicitly configured for self-hosted fallback behavior.

### Database And Migrations

Alembic must be the launch path for a fresh database. The backend startup script should run `alembic upgrade head` before serving traffic, and the migration smoke test must prove a fresh SQLite database can upgrade to head.

Rollback is a launch-critical path, not a documentation afterthought. Every launch-critical Alembic revision must have an executable `downgrade()` and must be covered by a downgrade smoke test. The verification flow must prove at least:

- Fresh database can upgrade to `head`.
- Database at `head` can downgrade one revision and then upgrade back to `head`.
- Any new launch-critical migration added during this work has a direct upgrade/downgrade test.

For existing historical migrations, do not rewrite migration history unless required to make a fresh deployment work. Downgrade verification should prioritize new or launch-touched migrations and the latest launch-critical rollback path.

Downgrade smoke tests improve migration confidence, but production rollback should prefer backup restore, traffic rollback, and forward-compatible migrations. Destructive or irreversible migrations must be explicitly marked and require backup verification before deployment. A runnable downgrade is not by itself proof that production data can be safely rolled back after the new app version has written new-schema data.

If `alembic upgrade head` fails during deployment, the runbook must instruct the operator to stop application startup, keep the previous application version serving traffic if possible, capture the Alembic error, and restore from the most recent verified backup or run the tested downgrade path only when the migration reached a known revision. The app must not serve traffic against a partially migrated database.

PostgreSQL remains the preferred production option because the Docker Compose file and database layer already support it. SQLite can remain documented for small self-hosted deployments, with a note that production backups and concurrency limits are the operator's responsibility.

SQLite migration smoke is required for fast local and CI feedback. Production-like migration verification must also run against PostgreSQL before release readiness is claimed because enum behavior, timestamp behavior, JSON fields, transaction semantics, uniqueness constraints, and concurrent publish idempotency can differ from SQLite.

The one-checkin-per-day invariant is based on China Standard Time, not UTC. The uniqueness boundary must use a persisted CST-derived `Date` column, currently `CheckIn.date`, populated only from `get_today_cst()` or an equivalent Asia/Shanghai calculation. The database constraint must be on `(user_id, date)` where `date` is this persisted CST date. Implementations must not derive the unique day from UTC timestamps or database server-local time at publish time.

### BYOK Security Boundary

The user's DeepSeek API key is sensitive user data. The launch design must guarantee:

- `X-User-Api-Key`, stored encrypted API keys, decrypted API keys, and DeepSeek Authorization headers never appear in request logs, exception logs, Sentry events, metrics labels, or frontend console logs.
- Request logging records route, method, status, duration, and request ID, but not sensitive headers or request bodies.
- Sentry configuration must avoid default PII capture and must scrub known sensitive header names if request context is attached later.
- Stored API keys are encrypted at rest with `API_KEY_ENCRYPTION_SECRET`.
- Key rotation is a documented operational limitation for this release unless implemented with key versioning. Without versioning, rotating `API_KEY_ENCRYPTION_SECRET` invalidates previously stored encrypted API keys and requires users to re-save them.
- Safe API key preview means a masked, non-credential-bearing representation such as the last 4 characters. Returning no preview is also acceptable. The preview must never be sufficient to use as a credential, including for unusually short inputs.

### Auth Session Requirements

The current Web app uses bearer JWTs stored in `localStorage` and sent via the `Authorization` header. Launch readiness must make that boundary explicit:

- The Web app must handle expired or invalid tokens by clearing local auth state and redirecting to `/login`.
- Logout must clear client-side auth state, including stored token and any legacy client-side API key cache.
- Production deployment must use HTTPS.
- Bearer tokens and authorization headers must never be logged to the browser console, backend logs, Sentry context, or metrics labels.
- If the implementation switches to cookies later, cookies must be `Secure`, `HttpOnly` where applicable, and configured with an explicit `SameSite` policy.
- The localStorage bearer-token risk is accepted for this launch only if documented in the launch checklist.

### API Behavior

The following endpoint families are launch-critical:

- Auth: register, login, token validation.
- API key: status, save, delete or replace if supported by current routes.
- Hot topics and daily topics.
- Generate content and quick generate.
- Confirm publish.
- User status, profile, drafts, and history views used by the Web app.

Launch-critical API responses must be deterministic enough for the Web app to show useful states:

- Missing API key returns a 400 with `error_code="missing_api_key"` and user-actionable text.
- Invalid or expired token returns a 401 with `error_code="invalid_token"`.
- Unauthorized admin access returns a 403 with `error_code="forbidden"`.
- Duplicate or invalid publish actions return a client error and do not double-count points or streak.
- Unhandled backend exceptions return a safe 500 with request ID.

Use a minimal error response contract for launch-critical endpoints:

```json
{
  "error_code": "missing_api_key",
  "message": "请在设置页面配置您的 DeepSeek API Key",
  "request_id": "optional-request-id"
}
```

Existing FastAPI `detail` responses may remain for non-launch-critical endpoints, but Web launch-path code should normalize backend errors into this contract before rendering.

The Web launch path must consume one normalized error model regardless of the raw backend response. If a backend route still returns FastAPI's native `{"detail": ...}` shape, the Web API layer must map it to an internal `{error_code, message, request_id?}` representation before UI code renders it. UI components should never branch on raw backend error shapes.

### Launch-Critical API Matrix

The implementation plan must inspect and verify each endpoint in this matrix. Endpoint behavior should be tested at the router or service layer, with Web behavior covered by manual or scripted smoke checks.

| Area | Endpoint | Method | Auth | Web page | Success behavior | Failure behavior | Test required |
|---|---|---|---|---|---|---|---|
| Auth | `/api/register` | POST | No | `/login` | Creates a Web user and returns JWT plus user status. | Duplicate username returns client error; weak payload validation returns 422. | Register success and duplicate-user test. |
| Auth | `/api/auth_login` | POST | No | `/login` | Returns JWT plus user status for valid credentials. | Invalid credentials return 401. | Login success and invalid-credentials test. |
| Session | `/api/user_status` | GET | Yes | `/`, `/profile`, auth provider | Returns streak, points, level, diamonds, reminder, and today status. | Invalid token returns 401 and Web clears auth state. | User status success and expired-token Web handling test or smoke step. |
| API key | `/api/user/api_key/status` | GET | Yes | `/settings`, auth provider | Returns configured flag and safe preview only. | Invalid token returns 401; plaintext key is never returned. | Status test proving no plaintext key leakage. |
| API key | `/api/user/api_key` | POST | Yes | `/settings` | Encrypts and stores key; returns configured flag and safe preview. | Invalid token returns 401; invalid body returns 422. | Save-key test and log-redaction check. |
| API key | `/api/user/api_key` | DELETE | Yes | `/settings` | Deletes stored key and returns configured=false. | Invalid token returns 401. | Delete-key test. |
| Hot topics | `/api/hot_topics/today` | GET | Yes | `/topics` | Returns today's topic cards. | Invalid token returns 401; degraded supply remains visible through health/runbook. | Hot topics success test. |
| Hot topics | `/api/hot_topics/{topic_id}` | GET | Yes | `/compose` | Returns today's hot topic detail. | Unknown or non-today topic returns 404. | Detail success and not-found test. |
| Hot topics | `/api/hot_topics/{topic_id}/analysis` | POST | Yes plus API key | `/compose` | Returns analysis for selected topic and angle. | Missing API key returns `missing_api_key`; timeout shows recoverable Web error. | Analysis success with mocked AI and missing-key test. |
| Topic selection | `/api/daily_topics` | POST | Yes plus API key | `/topics` | Returns AI topic suggestions and refresh count. | Missing API key returns `missing_api_key`; refresh limit returns client error. | Success, missing-key, and refresh-limit test. |
| Topic selection | `/api/select_topic` | POST | Yes | `/topics`, `/compose` | Creates or resets today's `CheckIn` and returns `checkin_id`. | Already completed today returns client error; invalid hot topic returns 404. | Select-topic success and completed-day test. |
| Generation | `/api/quick_generate` | POST | Yes plus API key | `/compose` | Generates draft content and persists it when `checkin_id` is supplied. | Missing API key returns `missing_api_key`; completed checkin returns client error; timeout shows recoverable Web error. | Quick-generate success, missing-key, completed-checkin, and timeout behavior test/smoke. |
| Generation | `/api/generate_content` | POST | Yes plus API key | `/discuss` | Advances discussion and may produce a draft. | Missing API key returns `missing_api_key`; invalid checkin state returns client error. | Discussion success, draft-ready transition, missing-key, and invalid-state test. |
| Preview | `/api/checkin/{checkin_id}` | GET | Yes | `/preview` | Returns topic, content, status, feedback, and generation context for the owning user. | Unknown or unauthorized checkin returns 404. | Owner success and cross-user denial test. |
| Preview quality | `/api/confirm_content` | POST | Yes plus API key | `/preview` | Saves edited content, runs quality checks, and moves checkin toward publishable state. | Missing API key returns `missing_api_key`; invalid status returns client error. | Confirm-content success and invalid-state test. |
| Preview quality | `/api/review_content` | POST | Yes plus API key | `/preview` | Reviews content without changing completed status. | Missing API key returns `missing_api_key`; unknown checkin returns 404. | Review-content success test. |
| Preview quality | `/api/revise_content` | POST | Yes plus API key | `/preview` | Revises draft and keeps state safe for publish. | Missing API key returns `missing_api_key`; invalid status returns client error. | Revise-content success and duplicate-state safety test. |
| Compose assets | `/api/compose_post_assets` | POST | Yes plus API key | `/preview` | Generates post pages/title/tags for image rendering. | Missing API key returns `missing_api_key`; unknown checkin returns 404. | Compose-assets success with mocked AI and missing-key test. |
| Publish | `/api/confirm_publish` | POST | Yes | `/preview` | Completes one `CheckIn` and updates points/streak exactly once. | Duplicate publish returns 409 or already-published result without duplicate rewards. | Publish success and concurrent duplicate-publish test. |
| Feedback | `/api/content_feedback` | POST | Yes | `/preview` | Stores feedback on draft/pending/completed content. | Invalid state returns client error. | Feedback success and invalid-state test. |
| Profile/history | `/api/my/checkins` | GET | Yes | `/`, `/drafts`, `/history`, `/profile` | Returns paginated checkins with status filters. | Invalid token returns 401. | Pagination/filter test. |

### Publish State Model

For launch, the publish operation is tied to `CheckIn.id` (`checkin_id`). A generated draft is the `content` field on a `CheckIn`; there is no separate stable `draft_id` or `generation_id` in the current data model.

Launch publish rules:

- A `CheckIn` can be published only once.
- The same user can have at most one reward-bearing completed `CheckIn` for a given CST date.
- The same user may edit, revise, or regenerate the same day's non-completed `CheckIn` before publish.
- Duplicate publish for the same `checkin_id` must return either 409 conflict or the already-published result. In both cases, points, streak, diamonds, achievements, and completed timestamp must not be applied twice.
- The implementation must use a transaction plus a database-level uniqueness constraint or an equivalent idempotency key. A row lock alone is insufficient for SQLite and must be verified against PostgreSQL.
- If future work adds `draft_id` or `generation_id`, the publish object must be revisited and this spec updated.

### State Transition Table

| State | Trigger | Backend result | Web result |
|---|---|---|---|
| Anonymous | Open protected page | No API call or 401 from protected API. | Redirect to `/login`. |
| Authenticated, no API key | Click AI generate/analyze endpoint | 400 `missing_api_key`; no draft, points, streak, or history mutation. | Show settings guidance and link to `/settings`. |
| `topic_selected`, no API key | Quick/deep generation attempted after topic selection | Existing non-completed `CheckIn` remains reusable; no content, points, streak, or publish history mutation. | After saving an API key, user can continue from the same selected topic/checkin without creating a new daily record. |
| API key configured | Save key | Encrypted key stored; status returns configured=true and safe preview. | Settings shows configured state without plaintext key. |
| No checkin today | Select topic or hot topic | `CheckIn` created with `topic_selected`; `checkin_id` returned. | Navigate to `/compose` or `/discuss` with checkin context. |
| `topic_selected` | Deep discussion message | Checkin moves to `discussing`; conversation history updates. | Chat shows assistant reply. |
| `topic_selected` or `discussing` | Quick/deep generation succeeds | Checkin content is saved; status becomes `draft_ready`. | Navigate to or display `/preview`. |
| `draft_ready` | Confirm content | Edited content saved; quality/fact/discussion checks recorded; status becomes `pending`. | Preview shows quality guidance and publish action. |
| `pending` | Confirm publish | Checkin becomes `completed`; points/streak/level/diamonds/achievements update once. | Success screen and profile reflect updated state. |
| `completed` | Repeated publish | No reward mutation; returns 409 or already-published result. | Show already published state; no duplicate reward UI. |
| Any state | Invalid/expired token | 401. | Clear local auth state and redirect to `/login`. |

### Observability

Keep request ID propagation and request logging. Sentry remains opt-in with `SENTRY_DSN`. Prometheus metrics are disabled in production by default and may be enabled only behind an internal gateway or equivalent private network boundary.

The health check must remain available at `/health` and report database connectivity. Deployment verification uses this endpoint before testing the user loop.

If Redis-backed rate limiting, hot topic supply, or DeepSeek reachability become part of deployment verification, they should be reported through a readiness or diagnostics endpoint/runbook section separate from the basic liveness check. Database connectivity is required for `/health`; external dependencies may report `degraded` without marking the process as down unless the deployment gate explicitly requires them.

## Web Design

The Web app remains a functional product surface, not a marketing landing page. The core launch path is:

1. Login or register.
2. Configure DeepSeek API key in settings if required.
3. Choose a topic or hot topic.
4. Generate draft content.
5. Preview generated content.
6. Confirm publish.
7. Return to profile or status views and see updated points and streak.

The implementation should not introduce a new design system. It should keep the existing Next.js App Router structure and patch launch blockers:

- Auth-protected pages redirect unauthenticated users predictably.
- API errors surface clear messages instead of silent failure.
- Loading states prevent duplicate generate or publish clicks.
- API base URL comes from `NEXT_PUBLIC_API_URL`.
- Production build and lint remain green.

Generation calls need explicit user-facing timeout behavior. The Web client should use a documented timeout for AI generation requests, show a recoverable error if the timeout is reached, and avoid automatic retry for publish or other state-changing operations. Backend AI retries may exist only inside service code where they cannot duplicate user-visible state changes.

Generation timeout values must be explicit and configurable. The Web client timeout, backend DeepSeek request timeout, and any retry budget must be documented separately so operators can tune slow-model behavior without code changes.

### AI Generation Abuse And Cost Controls

Launch-critical AI endpoints must protect both user-owned and system fallback DeepSeek usage:

- Generation and analysis endpoints must be rate limited per user and/or IP.
- Launch rate-limit values must be configurable or documented settings, not invisible hardcoded behavior. Defaults should be conservative and cover per-user generation requests per minute/day plus per-IP burst protection; exact values may follow existing project settings if the launch checklist records them.
- In multi-instance production, rate limiting must use a shared backend such as Redis. In-memory per-process rate limiting is acceptable only for a documented single-instance deployment; otherwise each replica gets its own quota and system fallback costs can be bypassed by spreading traffic across replicas.
- If system fallback `DEEPSEEK_API_KEY` is enabled, usage must be explicitly rate limited and documented as operator-funded.
- Client-side timeout is a UI recovery boundary, not a guarantee that backend work has stopped. For generation and analysis calls, backend work may continue and persist results to the same non-completed `CheckIn`; user retry must reuse or refresh that existing state instead of creating duplicate drafts or checkins. For publish and other reward-bearing state changes, the Web client must not automatically retry after timeout.
- Automatic retries must not create duplicate drafts, duplicate checkins, or duplicate user-visible state.
- Generation failures must not update points, streak, publish history, or completed status.
- Repeated generate/revise actions should reuse the same non-completed `CheckIn` unless the user explicitly selects a new topic.

### Rendering Safety

Because the launch session model accepts localStorage bearer-token risk, the Web app must reduce XSS exposure in content rendering:

- User text, AI-generated drafts, topics, and feedback must render as escaped text by default.
- Launch-critical pages must not use `dangerouslySetInnerHTML` for generated content unless the input is sanitized by a reviewed sanitizer.
- Browser console logging must not include JWTs, API keys, Authorization headers, generated prompts containing keys, or raw error objects that may contain sensitive headers.

## Documentation Design

Documentation must match the current launch target:

- README remains the primary setup and deployment guide.
- AGENTS.md must be updated so future agents do not follow obsolete Mini Program-first assumptions.
- Add a concise launch checklist or runbook if the existing docs do not already provide one.

The launch checklist must include:

- Required backend environment variables.
- Required Web environment variables.
- Canonical production environment flag, currently `ENVIRONMENT=production`.
- Backend test, lint, type, and migration commands.
- Web lint and build commands.
- Manual smoke steps for the full Web + backend loop.
- Deployment health check and rollback procedure.
- API key handling and logging redaction rules.
- Auth/session storage and logout behavior.
- AI generation timeout, retry, and cost-control rules.
- CST date uniqueness rule for checkins and rewards.
- XSS rendering rule for user and AI-generated content.
- Configurable or documented rate-limit values for generation and analysis endpoints.
- Safe API key preview behavior.

## Verification Plan

The release cannot be considered ready until these checks have run and their result is recorded:

- Backend dependencies installed in an isolated environment.
- `pytest` for backend tests.
- `ruff check app tests`.
- `ruff format --check app tests`.
- `mypy app --ignore-missing-imports`.
- Alembic fresh database migration smoke test.
- Alembic downgrade and upgrade-back smoke test for launch-critical migrations.
- PostgreSQL production-like migration smoke test in CI with a PostgreSQL service container or in a staging/pre-deploy environment before production deployment.
- Web `npm run lint`.
- Web `npm run build` in CI or a local non-sandbox environment because the Codex sandbox blocks Turbopack process or port binding.
- Manual or scripted smoke test of the Web + backend loop.

If an external service is required, use mocked AI calls for automated tests. A real DeepSeek key is only needed for a final manual production-like smoke test.

## Acceptance Criteria

The release is ready to enter the final verification stage when:

- The Web + backend core writing loop is implemented and no known launch-blocking bug remains.
- Backend and Web verification commands are documented and pass in the working environment or CI.
- Fresh database upgrade is verified.
- Launch-critical Alembic downgrades are executable and covered by downgrade/upgrade-back tests.
- PostgreSQL production-like migration verification has passed in CI with a PostgreSQL service container or in a staging/pre-deploy environment before production deployment. If neither environment is available, readiness is blocked by verification infrastructure rather than application code.
- The deployment runbook defines what to do when migration fails before traffic is shifted.
- BYOK secrets are redacted from logs, Sentry context, metrics, and frontend console output.
- Auth/session storage, logout, expired-token behavior, and HTTPS requirements are documented and verified.
- Publish is backend-idempotent under concurrent requests and cannot double-count points or streak.
- The reward/checkin uniqueness constraint uses a persisted CST date, not UTC-derived dates or server-local timestamp truncation.
- Launch-critical API errors expose a stable error shape or are normalized by the Web client before display.
- AI generation timeout behavior is documented and visible to users.
- AI generation endpoints have launch-appropriate rate limits and cost controls.
- Multi-instance deployments use shared rate-limit storage, or the launch checklist explicitly restricts the deployment to one backend instance.
- Generated content rendering is escaped or sanitized, with no unsafe `dangerouslySetInnerHTML` use on launch-critical pages.
- Production deployment variables and startup steps are documented.
- Production environment detection uses the documented `ENVIRONMENT=production` flag.
- Production CORS uses explicit origins and no wildcard origin when bearer Authorization headers or credentials are used.
- README and AGENTS.md no longer conflict about the launch architecture.
- Any remaining risks are explicitly listed as non-blocking.

## Final Verification Record Template

The final implementation response must include a filled record in this shape:

| Check | Command / Steps | Result | Notes |
|---|---|---|---|
| Backend dependencies | Create/use isolated Python env and install `backend/requirements.txt` plus lint/type tools | PASS/FAIL | |
| Backend tests | `pytest` | PASS/FAIL | |
| Ruff check | `ruff check app tests` | PASS/FAIL | |
| Ruff format | `ruff format --check app tests` | PASS/FAIL | |
| Mypy | `mypy app --ignore-missing-imports` | PASS/FAIL | |
| SQLite migration | Fresh DB `alembic upgrade head` | PASS/FAIL | |
| Alembic downgrade | DB at head, downgrade one revision, upgrade back to head | PASS/FAIL | |
| PostgreSQL migration | Production-like PostgreSQL `alembic upgrade head` | PASS/FAIL | |
| CST uniqueness | Verify `(user_id, CheckIn.date)` uses persisted CST date from `get_today_cst()` | PASS/FAIL | |
| Rate-limit storage | Verify Redis/shared limiter for multi-instance or documented single-instance limit | PASS/FAIL | |
| Concurrent publish | Two concurrent `/api/confirm_publish` requests for one `checkin_id` | PASS/FAIL | |
| BYOK redaction | Verify API keys/tokens absent from logs/Sentry-safe context/browser console | PASS/FAIL | |
| Rendering safety | Verify launch-critical generated content renders escaped/sanitized and does not use unsafe HTML injection | PASS/FAIL | |
| Web lint | `npm run lint` | PASS/FAIL | |
| Web build | `npm run build` in CI or local non-sandbox environment | PASS/FAIL/NOT RUN | If sandbox prevents build, record NOT RUN with the sandbox reason; do not mark PASS. |
| Manual smoke | Register -> save key -> select topic -> generate -> preview -> publish -> profile; repeated publish leaves points/streak unchanged | PASS/FAIL | |

## Implementation Constraints

- Preserve existing uncommitted work unless a change is necessary for the launch path.
- Keep changes scoped to Web + backend launch readiness.
- Prefer existing project patterns over broad rewrites.
- Add focused tests for behavioral fixes.
- Do not make Mini Program readiness a release blocker.
