# 顺发小程序重构 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an MVP mini-program path that serves structured hot topics from SQLite, generates a draft directly from a selected topic, and reuses the existing publish/streak flow without Coze.

**Architecture:** Add a local `hot_topics` persistence layer and API, then adapt the mini program topic selection flow to select a structured topic and generate a draft into the existing `checkins` workflow.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, SQLite, 微信小程序, DeepSeek API

---

### Task 1: Add local hot topic persistence

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/<new>_add_hot_topics_table.py`
- Create: `backend/app/services/local_hot_topic_store.py`
- Modify: `backend/app/cron/rss_cron.py`

**Step 1:** Add a `HotTopic` SQLAlchemy model for daily structured topics.
**Step 2:** Add an Alembic migration for the `hot_topics` table and indexes.
**Step 3:** Implement local save/query helpers for today’s top topics.
**Step 4:** Update the RSS cron job to persist to SQLite first.

### Task 2: Expose structured hot topic APIs

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/hot_topics.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/topic_service.py`
- Modify: `backend/app/routers/topics.py`

**Step 1:** Add response schemas that include title, summary, source, url, published_at, score, and angle fields.
**Step 2:** Add `/api/hot_topics/today`.
**Step 3:** Make `/api/daily_topics` read from SQLite hot topics instead of AI-generated abstract topics when available.

### Task 3: Persist quick-generate output into checkin

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/content.py`

**Step 1:** Allow `quick_generate` requests to optionally include `checkin_id`.
**Step 2:** If provided, save the generated draft into the matching checkin and move it to `draft_ready`.

### Task 4: Adapt mini program topic flow to MVP

**Files:**
- Modify: `miniprogram/components/topic-card/index.js`
- Modify: `miniprogram/components/topic-card/index.wxml`
- Modify: `miniprogram/components/topic-card/index.wxss`
- Modify: `miniprogram/pages/topics/topics.js`
- Modify: `miniprogram/pages/topics/topics.wxml`
- Modify: `miniprogram/pages/topics/topics.wxss`

**Step 1:** Render source, summary, and link-aware hot topic cards.
**Step 2:** Replace “讨论模式” entry flow with “选择热点 -> 创建 checkin -> quick_generate -> preview”.

### Task 5: Add verification and reminder groundwork

**Files:**
- Modify: `miniprogram/config.js`
- Modify: `miniprogram/pages/settings/settings.js`
- Add tests under `backend/tests/`

**Step 1:** Add config placeholders for production domain and subscribe template ID.
**Step 2:** Add reminder settings UX groundwork for subscribe-message authorization.
**Step 3:** Add backend tests for local hot topics and quick-generate persistence.
