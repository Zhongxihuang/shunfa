# Quality Review Soft Signal Design

**Date:** 2026-04-10

**Context**

The current project mixes three different concepts into one field and one flow:
- AI quality review output
- publish gating
- user satisfaction / feedback

That creates incorrect behavior in the backend state machine, misleading naming, and frontends that treat the AI check as both a blocker and a non-blocker.

**Approved Direction**

Use quality review as a soft signal, not a hard gate.

- The AI quality check should return tips and issues.
- The user must still be allowed to publish even when the AI thinks the draft is weak.
- User feedback should be captured separately from AI review, so future tuning can rely on actual user sentiment instead of inferred approval.

**Design**

1. Backend semantics

- Keep publish flow as `draft_ready -> pending -> completed`.
- `confirm_content` should still move the draft into `pending`.
- AI review result should be stored as review metadata, not as a publish gate.
- `confirm_publish` should only require `pending`, not AI pass/fail.

2. Data model

- Preserve backward compatibility for existing rows.
- Reinterpret `content_approved` as a temporary legacy AI signal only where needed.
- Add explicit user feedback fields on `CheckIn`:
  - `content_feedback`: nullable string enum-like value such as `up` / `down`
  - `content_feedback_at`: nullable timestamp
- This lets the product show “觉得这版一般” without conflating it with AI review.

3. API shape

- `POST /api/confirm_content` should return:
  - `quality_pass`
  - `quality_issues`
  - `message`
  - `status`
- The response should clearly indicate that low quality is only a reminder.
- Add a lightweight endpoint for user feedback on the draft, separate from publish:
  - `POST /api/content_feedback`
  - body: `checkin_id`, `feedback`

4. Frontend behavior

- Web and miniprogram preview pages should show quality issues as hints.
- Publish button remains available even when quality review is negative.
- Add optional thumbs-down feedback in preview/result flow when the user thinks the draft is weak.
- Draft recovery should use backend `checkin.content` as source of truth, with storage only as a cache.

5. Related fixes bundled with this work

- Fix topic refresh quota bug.
- Exclude auto angle sentinel messages from points and achievement accounting.
- Reset stale checkin state when the topic/session is restarted.
- Fix web reminder payload mismatch.
- Make tests hermetic by overriding config-dependent auth values in test setup.

**Error Handling**

- If AI review parsing fails, treat the review as unavailable, not as automatic pass.
- The UI should show a neutral fallback like “本次质量提示暂不可用，可直接发布”.
- User feedback submission failure must not block publish.

**Testing**

- Add regression tests for:
  - soft quality review not blocking publish
  - sentinel messages excluded from rewards/achievements
  - refresh quota increments correctly
  - restarting a topic clears stale draft/history
  - web reminder request payload matches backend contract
  - config-dependent auth tests no longer rely on local `.env`
