# Coze Header Compatibility Design

**Problem**

`/api/coze/*` currently requires `X-Feishu-User-Id` as a mandatory header. If Coze or the Feishu bot workflow does not inject that header consistently, FastAPI rejects the request with `422`, which surfaces to users as a generic tool failure.

**Approaches**

1. Keep strict header validation and fix Coze workflow config only.
   Trade-off: smallest code change, but brittle and still fails hard if the platform changes header behavior.

2. Make user identity headers optional and add backend fallback resolution.
   Trade-off: slightly more backend logic, but requests no longer fail at the boundary. This is the recommended approach.

3. Redesign plugin auth around explicit body fields or full OpenAPI security rework.
   Trade-off: cleaner long term, but heavier Coze-side migration than needed for the current production issue.

**Chosen Design**

Use approach 2. The backend will keep `X-Coze-Plugin-Token` required, but treat user identity headers as optional input. It will resolve identity from a small set of compatible headers, and if none are present, it will fall back to a shared anonymous Coze user instead of returning `422`.

**Backend Changes**

- Update `get_coze_user()` in `backend/app/routers/coze_plugin.py` to accept optional `X-Feishu-User-Id`.
- Add compatibility resolution for common alternatives such as `X-Lark-User-Id`, `X-User-Id`, open-id style headers, and conversation-style headers.
- Fall back to `coze_anonymous:anonymous` when no user identity header is available.

**OpenAPI Changes**

- Update `backend/coze_plugin_openapi_v2.json` and `backend/coze_plugin_openapi.json` so `X-Feishu-User-Id` is no longer marked as required.
- Clarify in descriptions that the header is preferred, but optional because the backend has compatibility fallback.

**Testing**

- Add regression tests proving `Coze` endpoints no longer fail when the user header is missing.
- Add regression tests proving alternative headers still map to a stable user record.
