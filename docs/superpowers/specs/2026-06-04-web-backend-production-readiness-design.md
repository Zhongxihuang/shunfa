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

- FastAPI backend with request logging, request IDs, Sentry support, rate limiting, health check, metrics behind a non-production flag, Alembic migrations, Dockerfile, and a production start script.
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

PostgreSQL remains the preferred production option because the Docker Compose file and database layer already support it. SQLite can remain documented for small self-hosted deployments, with a note that production backups and concurrency limits are the operator's responsibility.

### API Behavior

The following endpoint families are launch-critical:

- Auth: register, login, token validation.
- API key: status, save, delete or replace if supported by current routes.
- Hot topics and daily topics.
- Generate content and quick generate.
- Confirm publish.
- User status, profile, drafts, and history views used by the Web app.

Launch-critical API responses must be deterministic enough for the Web app to show useful states:

- Missing API key returns a clear 400 with user-actionable text.
- Invalid or expired token returns 401.
- Unauthorized admin access returns 403.
- Duplicate or invalid publish actions return a client error and do not double-count points or streak.
- Unhandled backend exceptions return a safe 500 with request ID.

### Observability

Keep request ID propagation and request logging. Sentry remains opt-in with `SENTRY_DSN`. Prometheus metrics remain disabled in production by default unless protected by an internal gateway.

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
- Deployment health check and rollback notes.

## Verification Plan

The release cannot be considered ready until these checks have run and their result is recorded:

- Backend dependencies installed in an isolated environment.
- `pytest` for backend tests.
- `ruff check app tests`.
- `ruff format --check app tests`.
- `mypy app --ignore-missing-imports`.
- Alembic fresh database migration smoke test.
- Web `npm run lint`.
- Web `npm run build`.
- Manual or scripted smoke test of the Web + backend loop.

If an external service is required, use mocked AI calls for automated tests. A real DeepSeek key is only needed for a final manual production-like smoke test.

## Acceptance Criteria

The release is ready to enter the final verification stage when:

- The Web + backend core writing loop is implemented and no known launch-blocking bug remains.
- Backend and Web verification commands are documented and pass in the working environment or CI.
- Fresh database migration is verified.
- Production deployment variables and startup steps are documented.
- README and AGENTS.md no longer conflict about the launch architecture.
- Any remaining risks are explicitly listed as non-blocking.

## Implementation Constraints

- Preserve existing uncommitted work unless a change is necessary for the launch path.
- Keep changes scoped to Web + backend launch readiness.
- Prefer existing project patterns over broad rewrites.
- Add focused tests for behavioral fixes.
- Do not make Mini Program readiness a release blocker.
