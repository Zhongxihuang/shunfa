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

Production CORS must be explicit. Localhost origins should be treated as a release warning at minimum, and the deployment checklist must require a real Web origin.

`REQUIRE_USER_API_KEY=true` is the default launch posture. System-level `DEEPSEEK_API_KEY` remains allowed only when explicitly configured for self-hosted fallback behavior.

### Database And Migrations

Alembic must be the launch path for a fresh database. The backend startup script should run `alembic upgrade head` before serving traffic, and the migration smoke test must prove a fresh SQLite database can upgrade to head.

Rollback is a launch-critical path, not a documentation afterthought. Every launch-critical Alembic revision must have an executable `downgrade()` and must be covered by a downgrade smoke test. The verification flow must prove at least:

- Fresh database can upgrade to `head`.
- Database at `head` can downgrade one revision and then upgrade back to `head`.
- Any new launch-critical migration added during this work has a direct upgrade/downgrade test.

If `alembic upgrade head` fails during deployment, the runbook must instruct the operator to stop application startup, keep the previous application version serving traffic if possible, capture the Alembic error, and restore from the most recent verified backup or run the tested downgrade path only when the migration reached a known revision. The app must not serve traffic against a partially migrated database.

PostgreSQL remains the preferred production option because the Docker Compose file and database layer already support it. SQLite can remain documented for small self-hosted deployments, with a note that production backups and concurrency limits are the operator's responsibility.

### BYOK Security Boundary

The user's DeepSeek API key is sensitive user data. The launch design must guarantee:

- `X-User-Api-Key`, stored encrypted API keys, decrypted API keys, and DeepSeek Authorization headers never appear in request logs, exception logs, Sentry events, metrics labels, or frontend console logs.
- Request logging records route, method, status, duration, and request ID, but not sensitive headers or request bodies.
- Sentry configuration must avoid default PII capture and must scrub known sensitive header names if request context is attached later.
- Stored API keys are encrypted at rest with `API_KEY_ENCRYPTION_SECRET`.
- Key rotation is a documented operational limitation for this release unless implemented with key versioning. Without versioning, rotating `API_KEY_ENCRYPTION_SECRET` invalidates previously stored encrypted API keys and requires users to re-save them.

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

Confirm publish must be backend-idempotent. Frontend loading states are useful but insufficient because users can double-click, refresh, or send concurrent requests. The backend must protect publish with a transaction plus either a database-level uniqueness constraint or an equivalent idempotency mechanism. Concurrent publish attempts for the same user/date/checkin must result in one successful points/streak calculation and all other attempts returning a client error or the already-completed result without applying rewards again.

### Observability

Keep request ID propagation and request logging. Sentry remains opt-in with `SENTRY_DSN`. Prometheus metrics are disabled in production by default and may be enabled only behind an internal gateway or equivalent private network boundary.

The health check must remain available at `/health` and report database connectivity. Deployment verification uses this endpoint before testing the user loop.

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

## Documentation Design

Documentation must match the current launch target:

- README remains the primary setup and deployment guide.
- AGENTS.md must be updated so future agents do not follow obsolete Mini Program-first assumptions.
- Add a concise launch checklist or runbook if the existing docs do not already provide one.

The launch checklist must include:

- Required backend environment variables.
- Required Web environment variables.
- Backend test, lint, type, and migration commands.
- Web lint and build commands.
- Manual smoke steps for the full Web + backend loop.
- Deployment health check and rollback procedure.
- API key handling and logging redaction rules.

## Verification Plan

The release cannot be considered ready until these checks have run and their result is recorded:

- Backend dependencies installed in an isolated environment.
- `pytest` for backend tests.
- `ruff check app tests`.
- `ruff format --check app tests`.
- `mypy app --ignore-missing-imports`.
- Alembic fresh database migration smoke test.
- Alembic downgrade and upgrade-back smoke test for launch-critical migrations.
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
- The deployment runbook defines what to do when migration fails before traffic is shifted.
- BYOK secrets are redacted from logs, Sentry context, metrics, and frontend console output.
- Publish is backend-idempotent under concurrent requests and cannot double-count points or streak.
- Launch-critical API errors expose a stable error shape or are normalized by the Web client before display.
- AI generation timeout behavior is documented and visible to users.
- Production deployment variables and startup steps are documented.
- README and AGENTS.md no longer conflict about the launch architecture.
- Any remaining risks are explicitly listed as non-blocking.

## Implementation Constraints

- Preserve existing uncommitted work unless a change is necessary for the launch path.
- Keep changes scoped to Web + backend launch readiness.
- Prefer existing project patterns over broad rewrites.
- Add focused tests for behavioral fixes.
- Do not make Mini Program readiness a release blocker.
