# Quality Review Soft Signal Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert quality review into a soft signal with separate user feedback while fixing the highest-priority review regressions in backend, web, and miniprogram.

**Architecture:** Keep the existing publish state machine, but remove semantic coupling between AI quality review and publish gating. Store user feedback separately, recover drafts from persisted checkin state, and patch accounting/test regressions around sentinel messages, topic refresh, and config-dependent auth.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, pytest, Next.js, WeChat Mini Program

---

### Task 1: Add persistence for explicit content feedback

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/alembic/versions/*.py` (new migration)
- Test: `backend/tests/test_content.py`

**Step 1: Write the failing test**

Add a test that stores explicit thumbs-down feedback on a checkin and verifies it is persisted independently from AI review state.

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_content.py -k feedback -v`
Expected: FAIL because the model/endpoint does not exist yet.

**Step 3: Write minimal implementation**

- Add nullable feedback fields to `CheckIn`.
- Add request schema for content feedback.
- Add migration.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_content.py -k feedback -v`
Expected: PASS

### Task 2: Make quality review a soft signal

**Files:**
- Modify: `backend/app/services/content_service.py`
- Modify: `backend/app/routers/content.py`
- Test: `backend/tests/test_content.py`

**Step 1: Write the failing test**

Add a test showing that a failed AI quality review still allows publish, but returns review issues and does not mark it as a hard pass.

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_content.py -k quality -v`
Expected: FAIL on old gating/semantics.

**Step 3: Write minimal implementation**

- Parse review failures into a neutral “review unavailable” result instead of auto-pass.
- Keep `confirm_content` as transition to `pending`.
- Keep `confirm_publish` gated only by workflow state.
- Return clearer soft-signal messaging.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_content.py -k quality -v`
Expected: PASS

### Task 3: Exclude system-generated angle messages from rewards

**Files:**
- Modify: `backend/app/services/content_service.py`
- Modify: `backend/app/services/points_service.py`
- Modify: `backend/app/services/achievement_service.py`
- Test: `backend/tests/test_points.py`
- Test: `backend/tests/test_achievements.py`

**Step 1: Write the failing tests**

Add tests proving auto angle suggestion messages do not count toward discussion bonus or `quality_writer`.

**Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_points.py backend/tests/test_achievements.py -k angle -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Add one canonical helper for counting real user rounds.
- Reuse it in content, points, and achievements services.
- Clean old angle suggestion assistant messages correctly.

**Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_points.py backend/tests/test_achievements.py -k angle -v`
Expected: PASS

### Task 4: Fix topic refresh and stale session reuse

**Files:**
- Modify: `backend/app/services/topic_service.py`
- Modify: `backend/app/routers/topics.py`
- Modify: `backend/app/routers/coze_plugin.py`
- Test: `backend/tests/test_topics.py`
- Test: `backend/tests/test_coze_plugin.py`

**Step 1: Write the failing tests**

Add tests covering:
- refresh count increments after first free load
- restarting a same-day topic clears stale draft/history/review state

**Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_topics.py backend/tests/test_coze_plugin.py -k 'refresh or restart' -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Correct first-load logic.
- Reset stale checkin fields when topic/session restarts.

**Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_topics.py backend/tests/test_coze_plugin.py -k 'refresh or restart' -v`
Expected: PASS

### Task 5: Fix web and miniprogram preview/reminder regressions

**Files:**
- Modify: `web/src/app/settings/page.tsx`
- Modify: `web/src/app/preview/page.tsx`
- Modify: `web/src/lib/api.ts`
- Modify: `web/src/lib/auth.tsx`
- Modify: `miniprogram/pages/preview/preview.js`

**Step 1: Write the failing tests or narrow repro assertions**

For web, add or document reproducible checks for:
- reminder payload field mismatch
- draft recovery from backend state
- dev preview mode not self-destructing on authenticated pages

**Step 2: Run the relevant checks**

Run the smallest available verification for web/backend integration.

**Step 3: Write minimal implementation**

- Send `reminder_enabled`.
- Fetch persisted checkin content when preview mounts.
- Avoid global 401 redirect breakage for local dev preview token.

**Step 4: Run checks to verify behavior**

Run targeted app or test verification and confirm fixed behavior.

### Task 6: Make auth tests hermetic

**Files:**
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_web_login.py`
- Modify: `backend/tests/test_coze_plugin.py`

**Step 1: Write the failing expectation**

Capture the current failure mode where local config leaks into tests.

**Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_web_login.py backend/tests/test_coze_plugin.py -v`
Expected: FAIL in current environment.

**Step 3: Write minimal implementation**

- Override settings values in test fixtures instead of assuming local `.env`.
- Keep test secrets local to the suite.

**Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_web_login.py backend/tests/test_coze_plugin.py -v`
Expected: PASS

### Task 7: Run end-to-end verification

**Files:**
- Modify: none unless verification exposes regressions

**Step 1: Run targeted suites**

Run:
- `pytest backend/tests/test_content.py backend/tests/test_points.py backend/tests/test_achievements.py backend/tests/test_topics.py backend/tests/test_web_login.py backend/tests/test_coze_plugin.py -q`

**Step 2: Run full backend suite**

Run:
- `pytest backend -q`

**Step 3: Record outcomes**

- Summarize what passed.
- Note any remaining gaps, especially for frontend runtime verification.
