# Coze Header Compatibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop Railway production `Coze` tool calls from failing when `X-Feishu-User-Id` is missing or inconsistent.

**Architecture:** Make the backend plugin auth boundary tolerant of missing user headers while keeping the shared plugin token strict. Update both OpenAPI specs to match runtime behavior, then lock the behavior with regression tests.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, static OpenAPI JSON

---

### Task 1: Make Coze user resolution tolerant

**Files:**
- Modify: `backend/app/routers/coze_plugin.py`
- Test: `backend/tests/test_coze_plugin.py`

**Step 1: Write the failing test**

Add a test that calls `/api/coze/get_hot_topics` with only `X-Coze-Plugin-Token` and asserts the response is `200`, not `422`.

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_coze_plugin.py::test_get_hot_topics_without_user_header_returns_list -q`
Expected: FAIL because FastAPI rejects the missing header.

**Step 3: Write minimal implementation**

Make `X-Feishu-User-Id` optional, resolve identity from compatible headers, and fall back to an anonymous Coze user.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_coze_plugin.py::test_get_hot_topics_without_user_header_returns_list -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routers/coze_plugin.py backend/tests/test_coze_plugin.py
git commit -m "fix: tolerate missing coze user headers"
```

### Task 2: Add compatibility coverage

**Files:**
- Modify: `backend/tests/test_coze_plugin.py`

**Step 1: Write the failing test**

Add a test that calls `/api/coze/user_stats` with `X-Lark-User-Id` and verifies a stable user is created.

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_coze_plugin.py::test_coze_endpoint_accepts_lark_user_id_header -q`
Expected: FAIL before compatibility parsing exists.

**Step 3: Write minimal implementation**

Reuse the same resolver added in task 1.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_coze_plugin.py::test_coze_endpoint_accepts_lark_user_id_header -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_coze_plugin.py
git commit -m "test: cover coze user header compatibility"
```

### Task 3: Align OpenAPI with runtime behavior

**Files:**
- Modify: `backend/coze_plugin_openapi.json`
- Modify: `backend/coze_plugin_openapi_v2.json`

**Step 1: Update the specs**

Change `X-Feishu-User-Id` from required to optional and clarify that Coze should send it when available, but the backend has fallback compatibility.

**Step 2: Review spec diffs**

Run: `git diff -- backend/coze_plugin_openapi.json backend/coze_plugin_openapi_v2.json`
Expected: only header requirement and description changes

**Step 3: Commit**

```bash
git add backend/coze_plugin_openapi.json backend/coze_plugin_openapi_v2.json
git commit -m "docs: relax coze user header requirement in openapi"
```

### Task 4: Run regression verification

**Files:**
- Modify: none
- Test: `backend/tests/test_coze_plugin.py`
- Test: `backend/tests`

**Step 1: Run targeted regression**

Run: `cd backend && pytest tests/test_coze_plugin.py -q`
Expected: PASS

**Step 2: Run full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS

**Step 3: Review final diff**

Run: `git diff --stat`
Expected: only the intended router, tests, docs, and spec files changed
