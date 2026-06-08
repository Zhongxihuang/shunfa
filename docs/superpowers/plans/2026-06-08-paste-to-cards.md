# 粘贴排版成小红书卡片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户粘贴一段已定稿的文章，纯确定性分页后用三套可切换模板渲染成高清小红书卡片图（1080×1440，PNG）。

**Architecture:** 新增独立实体 `ImageJob`（与 CheckIn 解耦，不进连胜/积分）。后端三层：`paginate_service`（纯函数、不调 AI、一字不改原文）→ `render_service`（Jinja2 模板 + 共享 headless Chromium 截图）→ `routers/image_jobs.py`（建任务/读任务/渲染三个端点）。小程序新增 `pages/compose-image` 入口页。

**Tech Stack:** FastAPI + SQLAlchemy(sync, SQLite WAL) + Alembic + Pydantic v2 + Jinja2 + Playwright(Chromium)。TDD，测试用 in-memory SQLite，Playwright 渲染层在测试中 mock。

**Spec:** `docs/superpowers/specs/2026-06-08-paste-to-cards-design.md`

**测试运行约定（本仓库）：**
```bash
cd /Users/huangzhongxi/shunfa/backend
DEEPSEEK_API_KEY=test JWT_SECRET_KEY=test-jwt-secret ADMIN_PASSWORD=test123 \
  python -m pytest tests/<file>::<test> -v
```
（所有任务的 `pytest` 命令均假设已 `cd backend` 且带上上面这串环境变量前缀。下文为简洁省略前缀，只写 `pytest ...`。）

---

## File Structure

**后端新增：**
- `backend/app/services/paginate_service.py` — 确定性分页：`paginate(raw_text, cover_title) -> PaginationResult`
- `backend/app/services/render_service.py` — `render_page_html()` + `render_cards()` + 浏览器单例 `get_browser()/shutdown_browser()`
- `backend/app/templates/cards/a.html` `b.html` `c.html` — 三套 Jinja2 单卡模板
- `backend/app/routers/image_jobs.py` — `POST /api/image_jobs`、`GET /api/image_jobs/{id}`、`POST /api/image_jobs/{id}/render`
- `backend/alembic/versions/b2c3d4e5f6a7_add_image_jobs.py` — 建表迁移
- `backend/tests/test_paginate.py`、`backend/tests/test_render_service.py`、`backend/tests/test_image_jobs.py`

**后端修改：**
- `backend/app/models.py` — `+ ImageJobStatus` enum 与 `ImageJob` 模型
- `backend/app/schemas.py` — `+ ImageJobCreateRequest / ImageJobRenderRequest / PageModel / ImageJobResponse / ImageJobRenderResponse`
- `backend/app/main.py` — import 并注册 `image_jobs` router；lifespan 关停浏览器单例
- `backend/requirements.txt` — `+ playwright`、`+ jinja2`

**小程序新增/修改：**
- `miniprogram/pages/compose-image/` — 新页面（4 个文件）
- `miniprogram/app.json` — pages 数组加入新页面
- `miniprogram/pages/index/index.wxml` — 加「粘贴排版」入口卡

---

## Task 1: ImageJob 模型 + 状态枚举

**Files:**
- Modify: `backend/app/models.py`（在文件末尾追加，约 185 行后）
- Test: `backend/tests/test_image_jobs.py`（新建，本任务只放模型 smoke 测试）

- [ ] **Step 1: Write the failing test**

新建 `backend/tests/test_image_jobs.py`：

```python
"""Tests for the paste-to-cards image job feature."""

from app.models import ImageJob, ImageJobStatus, User


def _make_user(db, openid="ij_user"):
    user = User(openid=openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_image_job_model_defaults(db):
    user = _make_user(db)
    job = ImageJob(user_id=user.id, raw_text="第一段\n第二段", template="a")
    db.add(job)
    db.commit()
    db.refresh(job)

    assert job.id is not None
    assert job.template == "a"
    assert job.status == ImageJobStatus.draft
    assert job.page_count == 0
    assert job.created_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_jobs.py::test_image_job_model_defaults -v`
Expected: FAIL with `ImportError: cannot import name 'ImageJob'`

- [ ] **Step 3: Write minimal implementation**

在 `backend/app/models.py` **文件末尾**追加（紧跟 `Event` 类之后）：

```python
class ImageJobStatus(enum.Enum):
    draft = "draft"
    rendered = "rendered"
    failed = "failed"


class ImageJob(Base):
    """Paste-to-cards job (added 2026-06). Decoupled from CheckIn: this is a
    standalone formatting tool, it does NOT affect streak / points / diamonds.

    We deliberately do NOT store rendered image bytes — images are re-rendered
    on demand from raw_text + template, so the table stays tiny.
    """

    __tablename__ = "image_jobs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_text = Column(Text, nullable=False)  # user's pasted article, stored verbatim
    template = Column(String(8), nullable=False, default="a")  # 'a' | 'b' | 'c'
    cover_title = Column(Text, nullable=True)  # user override; empty -> first paragraph
    page_count = Column(Integer, default=0, nullable=False)  # filled after pagination
    status = Column(SAEnum(ImageJobStatus), default=ImageJobStatus.draft, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

（无需新增 import：`enum`、`Column`、`Integer`、`String`、`Text`、`ForeignKey`、`DateTime`、`SAEnum`、`func` 在 models.py 顶部均已导入。）

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_jobs.py::test_image_job_model_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_image_jobs.py
git commit -m "feat: add ImageJob model for paste-to-cards"
```

---

## Task 2: Alembic 迁移建 image_jobs 表

**Files:**
- Create: `backend/alembic/versions/b2c3d4e5f6a7_add_image_jobs.py`

当前 alembic head 是 `1a2b3c4d5e6f`（add_gamification_override）。新迁移 `down_revision` 指向它。

- [ ] **Step 1: Write the migration file**

新建 `backend/alembic/versions/b2c3d4e5f6a7_add_image_jobs.py`：

```python
"""add image_jobs table (paste-to-cards feature)

Revision ID: b2c3d4e5f6a7
Revises: 1a2b3c4d5e6f
Create Date: 2026-06-08 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'image_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('template', sa.String(length=8), nullable=False, server_default='a'),
        sa.Column('cover_title', sa.Text(), nullable=True),
        sa.Column('page_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'status',
            sa.Enum('draft', 'rendered', 'failed', name='imagejobstatus'),
            nullable=False,
            server_default='draft',
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_image_jobs_id', 'image_jobs', ['id'])
    op.create_index('ix_image_jobs_user_id', 'image_jobs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_image_jobs_user_id', table_name='image_jobs')
    op.drop_index('ix_image_jobs_id', table_name='image_jobs')
    op.drop_table('image_jobs')
```

- [ ] **Step 2: Verify migration applies cleanly**

Run:
```bash
cd backend && DEEPSEEK_API_KEY=test JWT_SECRET_KEY=test-jwt-secret ADMIN_PASSWORD=test123 \
  python -m alembic upgrade head && \
  DEEPSEEK_API_KEY=test JWT_SECRET_KEY=test-jwt-secret ADMIN_PASSWORD=test123 \
  python -m alembic current
```
Expected: 输出包含 `b2c3d4e5f6a7 (head)`，无报错。

- [ ] **Step 3: Verify downgrade works then re-upgrade**

Run:
```bash
cd backend && DEEPSEEK_API_KEY=test JWT_SECRET_KEY=test-jwt-secret ADMIN_PASSWORD=test123 \
  python -m alembic downgrade -1 && \
  DEEPSEEK_API_KEY=test JWT_SECRET_KEY=test-jwt-secret ADMIN_PASSWORD=test123 \
  python -m alembic upgrade head
```
Expected: 两条命令均成功，无报错。

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/b2c3d4e5f6a7_add_image_jobs.py
git commit -m "feat: add alembic migration for image_jobs table"
```

---

## Task 3: 确定性分页 paginate_service

这是功能核心。纯函数、无 AI、无随机、一字不改原文。重测试。

**Files:**
- Create: `backend/app/services/paginate_service.py`
- Test: `backend/tests/test_paginate.py`

- [ ] **Step 1: Write the failing tests**

新建 `backend/tests/test_paginate.py`：

```python
"""Deterministic pagination — no AI, no randomness, never drops characters."""

from app.services.paginate_service import (
    MAX_CHARS_PER_PAGE,
    MAX_PAGES,
    paginate,
)


def test_single_paragraph_no_cover_becomes_cover_only():
    result = paginate("大厂悄悄裁掉 prompt 工程师")
    assert result.page_count == 1
    assert result.pages[0].kind == "cover"
    assert result.pages[0].title == "大厂悄悄裁掉 prompt 工程师"
    assert result.overflow is False


def test_first_paragraph_becomes_cover_rest_become_body():
    result = paginate("封面金句\n正文一\n正文二")
    assert result.pages[0].kind == "cover"
    assert result.pages[0].title == "封面金句"
    assert result.pages[1].kind == "body"
    assert result.pages[1].paragraphs == ["正文一", "正文二"]
    assert result.page_count == 2


def test_explicit_cover_title_keeps_all_paragraphs_in_body():
    result = paginate("正文一\n正文二", cover_title="我的封面")
    assert result.pages[0].title == "我的封面"
    assert result.pages[1].paragraphs == ["正文一", "正文二"]


def test_blank_lines_are_dropped():
    result = paginate("封面\n\n  \n正文")
    assert result.pages[0].title == "封面"
    assert result.pages[1].paragraphs == ["正文"]


def test_paragraphs_per_page_cap_splits_into_new_page():
    # 1 cover + 7 short body paragraphs; cap is 6 paras/page -> 6 then 1
    text = "\n".join(["封面"] + ["短"] * 7)
    result = paginate(text)
    assert result.page_count == 3  # cover + 2 body pages
    assert len(result.pages[1].paragraphs) == 6
    assert len(result.pages[2].paragraphs) == 1


def test_char_cap_splits_into_new_page():
    # two 150-char paragraphs in body: 150+150 > 240 -> two pages
    result = paginate("x", cover_title="封面")  # placeholder, replaced below
    text = "封面占位\n" + ("甲" * 150) + "\n" + ("乙" * 150)
    result = paginate(text, cover_title="封面")
    body = result.pages[1:]
    assert len(body) == 2
    assert body[0].paragraphs == ["甲" * 150]
    assert body[1].paragraphs == ["乙" * 150]


def test_oversize_single_paragraph_is_soft_split_without_losing_chars():
    para = "测试。" * 100  # 300 chars, > MAX_CHARS_PER_PAGE
    result = paginate(para, cover_title="封面")
    # all body text concatenated must equal the original paragraph exactly
    joined = "".join(p for page in result.pages[1:] for p in page.paragraphs)
    assert joined == para
    # each body page must respect the char cap
    for page in result.pages[1:]:
        assert sum(len(p) for p in page.paragraphs) <= MAX_CHARS_PER_PAGE


def test_overflow_flag_set_when_exceeding_max_pages():
    # 20 paragraphs of 200 chars each -> each needs its own page -> >8 pages
    text = "\n".join(["封面"] + [("内容" * 100) for _ in range(20)])
    result = paginate(text)
    assert result.page_count > MAX_PAGES
    assert result.overflow is True
    # never silently truncates: all 20 body paragraphs are still present
    assert len(result.pages) - 1 == 20


def test_deterministic_same_input_same_output():
    text = "封面\n正文一\n正文二\n正文三"
    a = paginate(text)
    b = paginate(text)
    assert [(p.kind, p.title, p.paragraphs) for p in a.pages] == [
        (p.kind, p.title, p.paragraphs) for p in b.pages
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paginate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.paginate_service'`

- [ ] **Step 3: Write the implementation**

新建 `backend/app/services/paginate_service.py`：

```python
"""Deterministic pagination for the paste-to-cards feature.

Pure function, NO AI, NO randomness. The hard guarantee: it never adds, removes,
or rewrites a single character of the user's text — it only decides where to
break it into cards. Given the same (raw_text, cover_title) the output is
byte-for-byte identical.
"""

from dataclasses import dataclass, field

MAX_CHARS_PER_PAGE = 240
MAX_PARAS_PER_PAGE = 6
MAX_PAGES = 8  # including the cover

# Sentence-ending punctuation we prefer to break a too-long paragraph at.
_SOFT_BREAK_CHARS = "。；？！"


@dataclass
class Page:
    index: int
    kind: str  # 'cover' | 'body'
    title: str | None = None
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class PaginationResult:
    pages: list[Page]
    page_count: int
    overflow: bool


def _split_long_paragraph(p: str, limit: int) -> list[str]:
    """Break a paragraph longer than `limit` into <= limit-sized chunks,
    preferring to cut just after a sentence-ending char. Never drops chars."""
    chunks: list[str] = []
    while len(p) > limit:
        window = p[:limit]
        cut = max((window.rfind(c) for c in _SOFT_BREAK_CHARS), default=-1)
        if cut <= 0:
            cut = limit - 1  # no punctuation in window -> hard cut at the limit
        chunks.append(p[: cut + 1])
        p = p[cut + 1 :]
    if p:
        chunks.append(p)
    return chunks


def paginate(raw_text: str, cover_title: str | None = None) -> PaginationResult:
    # 1. clean: split into paragraphs, strip, drop empties
    paragraphs = [line.strip() for line in (raw_text or "").split("\n")]
    paragraphs = [p for p in paragraphs if p]

    # 2. cover: explicit title wins; otherwise the first paragraph is promoted
    cover = (cover_title or "").strip()
    if not cover and paragraphs:
        cover = paragraphs.pop(0)

    # 3. expand any oversize paragraph into chunks
    expanded: list[str] = []
    for p in paragraphs:
        if len(p) > MAX_CHARS_PER_PAGE:
            expanded.extend(_split_long_paragraph(p, MAX_CHARS_PER_PAGE))
        else:
            expanded.append(p)

    # 4. fill body pages respecting char + paragraph caps
    body_pages: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for p in expanded:
        would_overflow_chars = current_len + len(p) > MAX_CHARS_PER_PAGE
        would_overflow_paras = len(current) >= MAX_PARAS_PER_PAGE
        if current and (would_overflow_chars or would_overflow_paras):
            body_pages.append(current)
            current = []
            current_len = 0
        current.append(p)
        current_len += len(p)
    if current:
        body_pages.append(current)

    # 5. assemble pages with 1-based indices
    pages: list[Page] = [Page(index=1, kind="cover", title=cover, paragraphs=[])]
    for group in body_pages:
        pages.append(Page(index=len(pages) + 1, kind="body", title=None, paragraphs=group))

    page_count = len(pages)
    overflow = page_count > MAX_PAGES  # never truncate — just flag it
    return PaginationResult(pages=pages, page_count=page_count, overflow=overflow)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paginate.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paginate_service.py backend/tests/test_paginate.py
git commit -m "feat: add deterministic pagination service for paste-to-cards"
```

---

## Task 4: 三套 Jinja2 卡片模板

每个模板是一张完整 HTML 文档，画布固定 1080×1440，根据 `page.kind` 渲染封面或正文。

**Files:**
- Create: `backend/app/templates/cards/a.html`
- Create: `backend/app/templates/cards/b.html`
- Create: `backend/app/templates/cards/c.html`

模板由 Task 5 的 `render_service` 加载并测试；本任务只创建静态文件，无独立 pytest。

- [ ] **Step 1: Create template A (暖纸编辑)**

新建 `backend/app/templates/cards/a.html`：

```html
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1080px; height: 1440px; }
  .card {
    width: 1080px; height: 1440px; background: #f3ece0;
    padding: 110px 96px; display: flex; flex-direction: column;
    font-family: Georgia, "Songti SC", "Noto Serif SC", serif; color: #23201b;
  }
  .idx { font-size: 30px; letter-spacing: 8px; color: #b08d57; }
  .kicker { font-size: 24px; letter-spacing: 10px; text-transform: uppercase; color: #9a8f7d; margin-top: 12px; }
  .rule { height: 2px; background: #cdbfa6; margin: 48px 0 60px; }
  .ttl { font-size: 84px; line-height: 1.34; font-weight: 700; }
  .body p { font-size: 40px; line-height: 1.9; margin-bottom: 30px; }
  .foot { margin-top: auto; font-size: 28px; color: #9a8f7d; letter-spacing: 3px; }
</style>
</head>
<body>
  <div class="card">
    <div class="idx">{{ "%02d"|format(page.index) }} / {{ "%02d"|format(total) }}</div>
    <div class="kicker">AI INDUSTRY NOTES</div>
    <div class="rule"></div>
    {% if page.kind == 'cover' %}
      <div class="ttl">{{ page.title }}</div>
    {% else %}
      <div class="body">{% for p in page.paragraphs %}<p>{{ p }}</p>{% endfor %}</div>
    {% endif %}
    <div class="foot">顺发 · 行业洞察</div>
  </div>
</body>
</html>
```

- [ ] **Step 2: Create template B (瑞士现代)**

新建 `backend/app/templates/cards/b.html`：

```html
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1080px; height: 1440px; }
  .card {
    width: 1080px; height: 1440px; background: #f7f6f3; color: #111;
    padding: 96px 88px; display: flex; flex-direction: column;
    font-family: "Helvetica Neue", "PingFang SC", Arial, sans-serif;
  }
  .head { display: flex; align-items: center; justify-content: space-between; }
  .head .l { display: flex; align-items: center; gap: 20px; font-size: 28px;
             letter-spacing: 6px; text-transform: uppercase; font-weight: 700; }
  .head .sq { width: 28px; height: 28px; background: #e8401f; }
  .head .n { font-weight: 800; font-size: 40px; }
  .bar { height: 8px; background: #111; margin: 36px 0 0; }
  .ttl { margin-top: auto; font-weight: 800; font-size: 96px; line-height: 1.1; letter-spacing: -2px; }
  .body { margin-top: auto; }
  .body p { font-size: 42px; line-height: 1.75; font-weight: 500; margin-bottom: 28px; }
  .foot { margin-top: 40px; font-size: 26px; letter-spacing: 4px; color: #888; font-weight: 600; }
</style>
</head>
<body>
  <div class="card">
    <div class="head">
      <div class="l"><span class="sq"></span>AI 洞察</div>
      <div class="n">{{ "%02d"|format(page.index) }}</div>
    </div>
    <div class="bar"></div>
    {% if page.kind == 'cover' %}
      <div class="ttl">{{ page.title }}</div>
    {% else %}
      <div class="body">{% for p in page.paragraphs %}<p>{{ p }}</p>{% endfor %}</div>
    {% endif %}
    <div class="foot">顺发 / 行业洞察 · {{ "%02d"|format(page.index) }} / {{ "%02d"|format(total) }}</div>
  </div>
</body>
</html>
```

- [ ] **Step 3: Create template C (撞色高定)**

新建 `backend/app/templates/cards/c.html`：

```html
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8" />
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1080px; height: 1440px; }
  .card {
    width: 1080px; height: 1440px;
    background: linear-gradient(160deg, #1c3f8f 0%, #0d1f4d 100%);
    padding: 112px 100px; display: flex; flex-direction: column;
    font-family: "Songti SC", "Noto Serif SC", Georgia, serif; color: #f1ece1;
  }
  .kicker { font-size: 26px; letter-spacing: 10px; text-transform: uppercase; color: #aebbe0; }
  .ttl { margin-top: auto; font-weight: 600; font-size: 84px; line-height: 1.4; color: #fff; }
  .ttl .u { border-bottom: 4px solid #e8b04f; padding-bottom: 6px; }
  .body { margin-top: auto; }
  .body p { font-size: 42px; line-height: 1.85; margin-bottom: 30px; color: #eee6d8; }
  .foot { margin-top: 48px; display: flex; align-items: center; gap: 22px;
          font-size: 26px; letter-spacing: 4px; color: #9fb0dd; }
  .foot .ln { width: 64px; height: 2px; background: #e8b04f; }
</style>
</head>
<body>
  <div class="card">
    <div class="kicker">Insight · No.{{ "%02d"|format(page.index) }}</div>
    {% if page.kind == 'cover' %}
      <div class="ttl"><span class="u">{{ page.title }}</span></div>
    {% else %}
      <div class="body">{% for p in page.paragraphs %}<p>{{ p }}</p>{% endfor %}</div>
    {% endif %}
    <div class="foot"><span class="ln"></span>顺发 · 行业洞察 · {{ "%02d"|format(page.index) }} / {{ "%02d"|format(total) }}</div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/templates/cards/a.html backend/app/templates/cards/b.html backend/app/templates/cards/c.html
git commit -m "feat: add three Jinja2 card templates for paste-to-cards"
```

---

## Task 5: render_service（Jinja2 + Playwright，测试中 mock）

**Files:**
- Create: `backend/app/services/render_service.py`
- Test: `backend/tests/test_render_service.py`

- [ ] **Step 1: Write the failing tests**

新建 `backend/tests/test_render_service.py`：

```python
"""Render service: HTML templating is tested for real; the Playwright
screenshot path is fully mocked so tests never launch Chromium."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.paginate_service import Page
from app.services.render_service import render_cards, render_page_html


def test_render_page_html_cover_contains_title_and_index():
    page = Page(index=1, kind="cover", title="大厂裁掉 prompt 工程师", paragraphs=[])
    html = render_page_html(page, "a", total=3)
    assert "大厂裁掉 prompt 工程师" in html
    assert "01 / 03" in html


def test_render_page_html_body_contains_paragraphs():
    page = Page(index=2, kind="body", title=None, paragraphs=["正文一", "正文二"])
    html = render_page_html(page, "b", total=2)
    assert "正文一" in html
    assert "正文二" in html


def test_render_page_html_unknown_template_raises():
    page = Page(index=1, kind="cover", title="x", paragraphs=[])
    with pytest.raises(ValueError):
        render_page_html(page, "z", total=1)


@pytest.mark.anyio
async def test_render_cards_screenshots_every_page():
    pages = [
        Page(index=1, kind="cover", title="封面", paragraphs=[]),
        Page(index=2, kind="body", title=None, paragraphs=["正文"]),
    ]

    fake_page = AsyncMock()
    fake_page.screenshot = AsyncMock(return_value=b"PNGDATA")
    fake_browser = AsyncMock()
    fake_browser.new_page = AsyncMock(return_value=fake_page)

    with patch(
        "app.services.render_service.get_browser",
        new=AsyncMock(return_value=fake_browser),
    ):
        images = await render_cards(pages, "a")

    assert images == [b"PNGDATA", b"PNGDATA"]
    assert fake_page.screenshot.await_count == 2


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_render_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.render_service'`

- [ ] **Step 3: Write the implementation**

新建 `backend/app/services/render_service.py`：

```python
"""Render card pages to PNG via Jinja2 templates + a shared headless Chromium.

Why a process-level browser singleton: launching Chromium costs ~300ms, so we
launch once (lazily) and reuse it across requests. The FastAPI lifespan calls
`shutdown_browser()` on exit.

Tests mock `get_browser` so Chromium is never launched in CI.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .paginate_service import Page

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "cards"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

_TEMPLATE_FILES = {"a": "a.html", "b": "b.html", "c": "c.html"}
_VIEWPORT = {"width": 1080, "height": 1440}
_DEVICE_SCALE_FACTOR = 2  # export at 2160x2880 for crisp images

# process-level singletons
_playwright = None
_browser = None


def render_page_html(page: Page, template: str, total: int) -> str:
    """Render one card page to an HTML string. Pure, no browser involved."""
    if template not in _TEMPLATE_FILES:
        raise ValueError(f"unknown template: {template!r}")
    tmpl = _env.get_template(_TEMPLATE_FILES[template])
    return tmpl.render(page=page, total=total)


async def get_browser():
    """Lazily launch (and cache) a shared headless Chromium instance."""
    global _playwright, _browser
    if _browser is None:
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(args=["--no-sandbox"])
    return _browser


async def shutdown_browser() -> None:
    """Close the shared browser. Safe to call when nothing was launched."""
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None


async def render_cards(pages: list[Page], template: str) -> list[bytes]:
    """Render every page to a PNG (bytes), in order."""
    total = len(pages)
    htmls = [render_page_html(p, template, total) for p in pages]

    browser = await get_browser()
    bp = await browser.new_page(
        viewport=_VIEWPORT, device_scale_factor=_DEVICE_SCALE_FACTOR
    )
    images: list[bytes] = []
    try:
        for html in htmls:
            await bp.set_content(html, wait_until="networkidle")
            images.append(await bp.screenshot(type="png"))
    finally:
        await bp.close()
    return images
```

注意：`render_cards` 里 `browser.new_page(...)`、`bp.set_content(...)`、`bp.screenshot(...)`、`bp.close()` 均为 await 调用，对应测试里的 `AsyncMock` 会自动满足。

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_render_service.py -v`
Expected: PASS (4 passed)

如果报 `anyio`/`pytest.mark.anyio` 相关错误，确认 `requirements.txt` 已含 `anyio`（FastAPI 依赖，通常已装）；本测试用 `anyio_backend` fixture 固定为 asyncio，无需额外插件。若环境缺 `pytest-anyio`，改用以下等价写法替换该测试（用 `asyncio.run`）：

```python
def test_render_cards_screenshots_every_page():
    import asyncio
    pages = [
        Page(index=1, kind="cover", title="封面", paragraphs=[]),
        Page(index=2, kind="body", title=None, paragraphs=["正文"]),
    ]
    fake_page = AsyncMock()
    fake_page.screenshot = AsyncMock(return_value=b"PNGDATA")
    fake_browser = AsyncMock()
    fake_browser.new_page = AsyncMock(return_value=fake_page)
    with patch("app.services.render_service.get_browser",
               new=AsyncMock(return_value=fake_browser)):
        images = asyncio.run(render_cards(pages, "a"))
    assert images == [b"PNGDATA", b"PNGDATA"]
    assert fake_page.screenshot.await_count == 2
```
（若用这个写法，删掉 `@pytest.mark.anyio` 那条测试和 `anyio_backend` fixture。两种二选一即可。）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/render_service.py backend/tests/test_render_service.py
git commit -m "feat: add render service (jinja2 + headless chromium) for paste-to-cards"
```

---

## Task 6: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas.py`（文件末尾追加）

- [ ] **Step 1: Write the failing test**

在 `backend/tests/test_image_jobs.py` 追加：

```python
def test_image_job_create_request_rejects_empty_text():
    import pytest
    from pydantic import ValidationError

    from app.schemas import ImageJobCreateRequest

    with pytest.raises(ValidationError):
        ImageJobCreateRequest(raw_text="", template="a")


def test_image_job_create_request_defaults_template_a():
    from app.schemas import ImageJobCreateRequest

    req = ImageJobCreateRequest(raw_text="一些文字")
    assert req.template == "a"
    assert req.cover_title is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_image_jobs.py::test_image_job_create_request_defaults_template_a -v`
Expected: FAIL with `ImportError: cannot import name 'ImageJobCreateRequest'`

- [ ] **Step 3: Write the implementation**

在 `backend/app/schemas.py` **文件末尾**追加（`Literal`、`BaseModel`、`Field` 已在顶部导入）：

```python
# ── Paste-to-cards (image jobs) ──────────────────────────────────────────────


class ImageJobCreateRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=20000)
    template: Literal["a", "b", "c"] = "a"
    cover_title: str | None = Field(default=None, max_length=120)


class ImageJobRenderRequest(BaseModel):
    template: Literal["a", "b", "c"] | None = None


class PageModel(BaseModel):
    index: int
    kind: Literal["cover", "body"]
    title: str | None = None
    paragraphs: list[str] = []


class ImageJobResponse(BaseModel):
    job_id: int
    template: str
    cover_title: str | None
    pages: list[PageModel]
    page_count: int
    overflow: bool
    status: str


class ImageJobRenderResponse(BaseModel):
    job_id: int
    template: str
    images: list[str]  # base64-encoded PNG, one per page
    page_count: int
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_image_jobs.py -k image_job_create_request -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_image_jobs.py
git commit -m "feat: add image job schemas for paste-to-cards"
```

---

## Task 7: image_jobs 路由（建任务 / 读任务 / 渲染）+ 注册

**Files:**
- Create: `backend/app/routers/image_jobs.py`
- Modify: `backend/app/main.py`（import 行 18，注册区 ~166 行，lifespan ~63 行）
- Test: `backend/tests/test_image_jobs.py`（追加端点测试）

- [ ] **Step 1: Write the failing tests**

在 `backend/tests/test_image_jobs.py` 顶部 import 区补一行，并追加端点测试：

```python
from unittest.mock import AsyncMock, patch

from app.routers.user import create_jwt_token


def _auth(user):
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


def test_create_image_job_returns_pagination(client, db):
    user = _make_user(db, openid="ij_create")
    resp = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面金句\n正文一\n正文二", "template": "b"},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["template"] == "b"
    assert body["pages"][0]["kind"] == "cover"
    assert body["pages"][0]["title"] == "封面金句"
    assert body["page_count"] == 2
    assert body["overflow"] is False
    assert body["status"] == "draft"


def test_create_image_job_requires_auth(client, db):
    resp = client.post("/api/image_jobs", json={"raw_text": "x", "template": "a"})
    assert resp.status_code in (401, 403)


def test_get_image_job_returns_404_for_other_users_job(client, db):
    owner = _make_user(db, openid="ij_owner")
    other = _make_user(db, openid="ij_other")
    created = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面\n正文", "template": "a"},
        headers=_auth(owner),
    ).json()
    resp = client.get(f"/api/image_jobs/{created['job_id']}", headers=_auth(other))
    assert resp.status_code == 404


def test_render_image_job_returns_base64_images(client, db):
    user = _make_user(db, openid="ij_render")
    created = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面\n正文一\n正文二", "template": "a"},
        headers=_auth(user),
    ).json()

    with patch(
        "app.routers.image_jobs.render_cards",
        new=AsyncMock(return_value=[b"PNG1", b"PNG2"]),
    ):
        resp = client.post(
            f"/api/image_jobs/{created['job_id']}/render",
            json={"template": "c"},
            headers=_auth(user),
        )

    assert resp.status_code == 200
    body = resp.json()
    import base64

    assert body["template"] == "c"  # template override took effect
    assert body["images"][0] == base64.b64encode(b"PNG1").decode("ascii")
    assert len(body["images"]) == 2


def test_render_image_job_502_on_render_failure(client, db):
    user = _make_user(db, openid="ij_fail")
    created = client.post(
        "/api/image_jobs",
        json={"raw_text": "封面\n正文", "template": "a"},
        headers=_auth(user),
    ).json()

    with patch(
        "app.routers.image_jobs.render_cards",
        new=AsyncMock(side_effect=RuntimeError("chromium boom")),
    ):
        resp = client.post(
            f"/api/image_jobs/{created['job_id']}/render",
            json={},
            headers=_auth(user),
        )
    assert resp.status_code == 502
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_image_jobs.py::test_create_image_job_returns_pagination -v`
Expected: FAIL with 404 (route not registered yet)

- [ ] **Step 3: Create the router**

新建 `backend/app/routers/image_jobs.py`：

```python
"""Paste-to-cards endpoints (added 2026-06).

A standalone formatting tool: paste an article, get back deterministic
pagination, then render the pages to PNG cards with a chosen template.
NOT linked to streak/points — see ImageJob docstring.
"""

import base64

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import ImageJob, ImageJobStatus, User
from ..schemas import (
    ImageJobCreateRequest,
    ImageJobRenderRequest,
    ImageJobRenderResponse,
    ImageJobResponse,
    PageModel,
)
from ..services.analytics import track
from ..services.paginate_service import PaginationResult, paginate
from ..services.render_service import render_cards

router = APIRouter(prefix="/image_jobs", tags=["image_jobs"])


def _pages_to_models(result: PaginationResult) -> list[PageModel]:
    return [
        PageModel(index=p.index, kind=p.kind, title=p.title, paragraphs=p.paragraphs)
        for p in result.pages
    ]


def _get_owned_job(job_id: int, user: User, db: Session) -> ImageJob:
    job = (
        db.query(ImageJob)
        .filter(ImageJob.id == job_id, ImageJob.user_id == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Image job not found")
    return job


@router.post("", response_model=ImageJobResponse)
def create_image_job(
    body: ImageJobCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobResponse:
    result = paginate(body.raw_text, body.cover_title)
    job = ImageJob(
        user_id=current_user.id,
        raw_text=body.raw_text,
        template=body.template,
        cover_title=body.cover_title,
        page_count=result.page_count,
        status=ImageJobStatus.draft,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    track(
        "paste_compose",
        user_id=current_user.id,
        props={
            "template": body.template,
            "char_count": len(body.raw_text),
            "page_count": result.page_count,
        },
    )

    return ImageJobResponse(
        job_id=job.id,
        template=job.template,
        cover_title=job.cover_title,
        pages=_pages_to_models(result),
        page_count=result.page_count,
        overflow=result.overflow,
        status=job.status.value,
    )


@router.get("/{job_id}", response_model=ImageJobResponse)
def get_image_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobResponse:
    job = _get_owned_job(job_id, current_user, db)
    result = paginate(job.raw_text, job.cover_title)
    return ImageJobResponse(
        job_id=job.id,
        template=job.template,
        cover_title=job.cover_title,
        pages=_pages_to_models(result),
        page_count=result.page_count,
        overflow=result.overflow,
        status=job.status.value,
    )


@router.post("/{job_id}/render", response_model=ImageJobRenderResponse)
async def render_image_job(
    job_id: int,
    body: ImageJobRenderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImageJobRenderResponse:
    job = _get_owned_job(job_id, current_user, db)
    if body.template:
        job.template = body.template

    result = paginate(job.raw_text, job.cover_title)
    try:
        images = await render_cards(result.pages, job.template)
    except Exception as exc:
        job.status = ImageJobStatus.failed
        db.commit()
        raise HTTPException(status_code=502, detail="图片渲染失败，请稍后重试") from exc

    job.status = ImageJobStatus.rendered
    job.page_count = result.page_count
    db.commit()

    track(
        "image_rendered",
        user_id=current_user.id,
        props={"template": job.template, "page_count": result.page_count},
    )

    encoded = [base64.b64encode(img).decode("ascii") for img in images]
    return ImageJobRenderResponse(
        job_id=job.id,
        template=job.template,
        images=encoded,
        page_count=result.page_count,
    )
```

- [ ] **Step 4: Register the router in main.py**

在 `backend/app/main.py` **第 18 行**的 routers import 中加入 `image_jobs`：

```python
from app.routers import admin, analytics, content, coze_plugin, hot_topics, image_jobs, reminder, topics, user
```

在 **第 165 行附近**（`app.include_router(my_router, prefix="/api")` 之后、`app.include_router(admin.router)` 之前）加入：

```python
app.include_router(image_jobs.router, prefix="/api")
```

在 **lifespan 的 `yield` 之后**（约第 63-64 行，`logger.info("Shutting down 顺发 API")` 旁）加入浏览器关停：

```python
    yield
    logger.info("Shutting down 顺发 API")
    from app.services.render_service import shutdown_browser

    await shutdown_browser()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_image_jobs.py -v`
Expected: PASS (全部通过，含 create/auth/404/render/502)

- [ ] **Step 6: Run the full backend suite for regressions**

Run: `pytest -q`
Expected: 所有既有测试仍通过，新增测试通过，无回归。

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/image_jobs.py backend/app/main.py backend/tests/test_image_jobs.py
git commit -m "feat: add image_jobs endpoints (create/get/render) for paste-to-cards"
```

---

## Task 8: 依赖声明（playwright + jinja2）

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add dependencies**

在 `backend/requirements.txt` 末尾追加：

```
# Paste-to-cards image rendering
jinja2>=3.1
playwright>=1.40
# NOTE: after `pip install -r requirements.txt`, run `playwright install chromium`
# once per environment to download the headless browser. The target host must
# also have CJK fonts (Songti/PingFang or Noto Serif/Sans CJK) installed for the
# card templates to render correctly.
```

- [ ] **Step 2: Install and verify Chromium is available locally**

Run:
```bash
cd backend && pip install -r requirements.txt && python -m playwright install chromium
```
Expected: 安装成功，Chromium 下载完成。

- [ ] **Step 3: Smoke-test a real render (not in CI; local only)**

Run:
```bash
cd backend && DEEPSEEK_API_KEY=test JWT_SECRET_KEY=test-jwt-secret ADMIN_PASSWORD=test123 python -c "
import asyncio
from app.services.paginate_service import paginate
from app.services.render_service import render_cards, shutdown_browser

async def main():
    result = paginate('大厂悄悄裁掉 prompt 工程师\n不是它没用，是能力被产品吃进系统里。\n这件事的真正信号在别处。')
    for tmpl in ('a', 'b', 'c'):
        imgs = await render_cards(result.pages, tmpl)
        with open(f'/tmp/card_{tmpl}_cover.png', 'wb') as f:
            f.write(imgs[0])
        print(tmpl, 'pages:', len(imgs), 'cover bytes:', len(imgs[0]))
    await shutdown_browser()

asyncio.run(main())
"
```
Expected: 打印每套模板的页数与封面字节数；`/tmp/card_a_cover.png` 等文件可打开，三套视觉明显不同（暖纸 / 瑞士现代 / 撞色高定）。人工肉眼确认美学达标。

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add playwright + jinja2 deps for paste-to-cards rendering"
```

---

## Task 9: 小程序 compose-image 页面 + 首页入口

前端 JS，无 pytest；用微信开发者工具人工验证。

**Files:**
- Create: `miniprogram/pages/compose-image/compose-image.js`
- Create: `miniprogram/pages/compose-image/compose-image.wxml`
- Create: `miniprogram/pages/compose-image/compose-image.wxss`
- Create: `miniprogram/pages/compose-image/compose-image.json`
- Modify: `miniprogram/app.json`（pages 数组）
- Modify: `miniprogram/pages/index/index.wxml`（入口卡）

- [ ] **Step 1: Create the page JSON**

新建 `miniprogram/pages/compose-image/compose-image.json`：

```json
{
  "navigationBarTitleText": "粘贴排版",
  "usingComponents": {}
}
```

- [ ] **Step 2: Create the page WXML**

新建 `miniprogram/pages/compose-image/compose-image.wxml`：

```xml
<view class="page">
  <view class="hint">把你写好的文章粘贴进来，自动排成小红书卡片图。</view>

  <textarea
    class="input"
    placeholder="粘贴正文…（第一段会作为封面金句，也可在下方自定义封面）"
    value="{{ rawText }}"
    bindinput="onTextInput"
    maxlength="20000"
    auto-height
  />

  <input
    class="cover-input"
    placeholder="可选：自定义封面文字"
    value="{{ coverTitle }}"
    bindinput="onCoverInput"
  />

  <view class="templates">
    <view
      wx:for="{{ templates }}"
      wx:key="id"
      class="tpl {{ template === item.id ? 'tpl-active' : '' }}"
      data-id="{{ item.id }}"
      bindtap="onPickTemplate"
    >{{ item.name }}</view>
  </view>

  <button class="btn" bindtap="onPreview" loading="{{ previewing }}">生成预览</button>

  <view wx:if="{{ overflow }}" class="overflow-warn">
    内容较长（{{ pageCount }} 页，建议精简到 8 页内）。
  </view>

  <view wx:if="{{ pages.length }}" class="preview">
    <view wx:for="{{ pages }}" wx:key="index" class="preview-card">
      <text class="pc-idx">{{ item.index }} / {{ pageCount }}</text>
      <text wx:if="{{ item.kind === 'cover' }}" class="pc-title">{{ item.title }}</text>
      <block wx:else>
        <text wx:for="{{ item.paragraphs }}" wx:for-item="p" wx:key="*this" class="pc-p">{{ p }}</text>
      </block>
    </view>
  </view>

  <button
    wx:if="{{ pages.length }}"
    class="btn btn-primary"
    bindtap="onRender"
    loading="{{ rendering }}"
  >渲染高清图</button>

  <view wx:if="{{ images.length }}" class="images">
    <image
      wx:for="{{ images }}"
      wx:key="*this"
      class="result-img"
      src="{{ item }}"
      mode="widthFix"
      bindtap="onSaveImage"
      data-src="{{ item }}"
    />
    <view class="save-tip">点击任意图片保存到相册</view>
  </view>
</view>
```

- [ ] **Step 3: Create the page WXSS**

新建 `miniprogram/pages/compose-image/compose-image.wxss`：

```css
.page { padding: 32rpx; }
.hint { color: #888; font-size: 26rpx; margin-bottom: 24rpx; }
.input {
  width: 100%; min-height: 320rpx; background: #f7f7f7; border-radius: 16rpx;
  padding: 24rpx; font-size: 30rpx; line-height: 1.6; box-sizing: border-box;
}
.cover-input {
  width: 100%; background: #f7f7f7; border-radius: 16rpx; padding: 20rpx 24rpx;
  margin-top: 20rpx; font-size: 28rpx; box-sizing: border-box;
}
.templates { display: flex; gap: 16rpx; margin: 28rpx 0; }
.tpl {
  flex: 1; text-align: center; padding: 20rpx 0; border-radius: 12rpx;
  background: #f0f0f0; font-size: 26rpx; color: #555;
}
.tpl-active { background: #07c160; color: #fff; }
.btn {
  margin-top: 12rpx; background: #f0f0f0; color: #333; border-radius: 44rpx; font-size: 30rpx;
}
.btn-primary { background: #07c160; color: #fff; margin-top: 28rpx; }
.overflow-warn { color: #e8401f; font-size: 26rpx; margin-top: 20rpx; }
.preview { margin-top: 28rpx; }
.preview-card {
  background: #fff; border: 1rpx solid #eee; border-radius: 16rpx;
  padding: 28rpx; margin-bottom: 20rpx; display: flex; flex-direction: column;
}
.pc-idx { color: #b08d57; font-size: 22rpx; letter-spacing: 2rpx; }
.pc-title { font-size: 40rpx; font-weight: 700; margin-top: 16rpx; line-height: 1.4; }
.pc-p { font-size: 28rpx; line-height: 1.7; margin-top: 12rpx; color: #333; }
.images { margin-top: 28rpx; }
.result-img { width: 100%; border-radius: 16rpx; margin-bottom: 20rpx; }
.save-tip { text-align: center; color: #999; font-size: 24rpx; }
```

- [ ] **Step 4: Create the page JS**

新建 `miniprogram/pages/compose-image/compose-image.js`：

```javascript
const api = require('../../utils/api');

Page({
  data: {
    rawText: '',
    coverTitle: '',
    template: 'a',
    templates: [
      { id: 'a', name: '暖纸编辑' },
      { id: 'b', name: '瑞士现代' },
      { id: 'c', name: '撞色高定' }
    ],
    jobId: null,
    pages: [],
    pageCount: 0,
    overflow: false,
    images: [],
    previewing: false,
    rendering: false
  },

  onTextInput(e) {
    this.setData({ rawText: e.detail.value });
  },

  onCoverInput(e) {
    this.setData({ coverTitle: e.detail.value });
  },

  onPickTemplate(e) {
    this.setData({ template: e.currentTarget.dataset.id, images: [] });
  },

  onPreview() {
    const rawText = this.data.rawText.trim();
    if (!rawText) {
      wx.showToast({ title: '请先粘贴正文', icon: 'none' });
      return;
    }
    this.setData({ previewing: true });
    api.post('/api/image_jobs', {
      raw_text: rawText,
      template: this.data.template,
      cover_title: this.data.coverTitle.trim() || null
    }).then((res) => {
      this.setData({
        jobId: res.job_id,
        pages: res.pages,
        pageCount: res.page_count,
        overflow: res.overflow,
        images: [],
        previewing: false
      });
    }).catch(() => {
      this.setData({ previewing: false });
      wx.showToast({ title: '生成失败，请重试', icon: 'none' });
    });
  },

  onRender() {
    if (!this.data.jobId) return;
    this.setData({ rendering: true });
    api.post(`/api/image_jobs/${this.data.jobId}/render`, {
      template: this.data.template
    }).then((res) => {
      const images = (res.images || []).map((b64) => `data:image/png;base64,${b64}`);
      this.setData({ images, rendering: false });
    }).catch(() => {
      this.setData({ rendering: false });
      wx.showToast({ title: '渲染失败，请重试', icon: 'none' });
    });
  },

  onSaveImage(e) {
    const src = e.currentTarget.dataset.src;
    // base64 data URI -> write to a temp file -> save to album
    const fsm = wx.getFileSystemManager();
    const filePath = `${wx.env.USER_DATA_PATH}/card_${Date.now()}.png`;
    const base64 = src.replace(/^data:image\/png;base64,/, '');
    try {
      fsm.writeFileSync(filePath, base64, 'base64');
    } catch (err) {
      wx.showToast({ title: '保存失败', icon: 'none' });
      return;
    }
    wx.saveImageToPhotosAlbum({
      filePath,
      success: () => wx.showToast({ title: '已保存到相册', icon: 'success' }),
      fail: (err) => {
        if (err.errMsg && err.errMsg.indexOf('auth deny') !== -1) {
          wx.showModal({
            title: '需要相册权限',
            content: '请在设置中允许保存图片到相册',
            confirmText: '去设置',
            success: (r) => { if (r.confirm) wx.openSetting(); }
          });
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      }
    });
  }
});
```

- [ ] **Step 5: Register the page and add the home entry**

在 `miniprogram/app.json` 的 `pages` 数组中加入新页面（放在 `"pages/drafts/drafts"` 之后）：

```json
  "pages": [
    "pages/index/index",
    "pages/topics/topics",
    "pages/discuss/discuss",
    "pages/preview/preview",
    "pages/profile/profile",
    "pages/settings/settings",
    "pages/history/history",
    "pages/drafts/drafts",
    "pages/compose-image/compose-image"
  ],
```

在 `miniprogram/pages/index/index.wxml` 中，找一处合适的位置（如主操作区附近）加入入口卡：

```xml
<view class="entry-card" bindtap="goComposeImage">
  <view class="entry-title">粘贴排版</view>
  <view class="entry-desc">把已写好的文章排成小红书卡片图</view>
</view>
```

并在 `miniprogram/pages/index/index.js` 的 `Page({ ... })` 中加入跳转方法（放在已有方法旁）：

```javascript
  goComposeImage() {
    wx.navigateTo({ url: '/pages/compose-image/compose-image' });
  },
```

- [ ] **Step 6: Manual verification in WeChat DevTools**

1. 用微信开发者工具打开 `miniprogram/`，确保后端本地已 `uvicorn app.main:app --reload` 运行。
2. 首页点「粘贴排版」入口 → 进入新页面。
3. 粘贴一段多段落文章 → 选模板 A/B/C → 点「生成预览」→ 看到文字分页预览，页数正确，超 8 页时显示 overflow 提示。
4. 点「渲染高清图」→ 逐张显示 PNG；切模板重新渲染，视觉随之改变。
5. 点任意图片 → 首次弹相册授权 → 同意后提示「已保存到相册」。

Expected: 全流程顺畅；三套模板视觉区分明显；保存成功。

- [ ] **Step 7: Commit**

```bash
git add miniprogram/pages/compose-image miniprogram/app.json miniprogram/pages/index/index.wxml miniprogram/pages/index/index.js
git commit -m "feat: add paste-to-cards miniprogram page and home entry"
```

---

## Self-Review

**1. Spec coverage（逐节核对 spec → 任务）：**
- §3 数据模型 ImageJob → Task 1 + Task 2 ✅
- §4 确定性分页规则（封面/字数/段数/超长软切/MAX_PAGES/overflow/不删字）→ Task 3（含对应测试）✅
- §5 渲染管线（Jinja2 + Playwright + 1080×1440 + scale 2 + 浏览器单例 + 失败 502）→ Task 4/5 + Task 7 渲染端点 ✅
- §5 三套模板（A/B/C 视觉规格）→ Task 4 ✅
- §6 三个接口（POST /image_jobs、POST /{id}/render、GET /{id}，JWT、非本人 404、切模板重渲）→ Task 7 ✅
- §7 小程序入口与流程（粘贴→选模板→预览→渲染→保存相册）→ Task 9 ✅
- §8 埋点 paste_compose / image_rendered（非商业指标）→ Task 7 ✅
- §9 文件改动清单 → 与各任务 Files 一致 ✅
- §10 测试约定（in-memory SQLite、渲染层 mock）→ Task 3/5/7 ✅
- §11 风险（Chromium/字体依赖、单例、overflow 不截断、不改写原文）→ Task 7/8 注释与测试覆盖 ✅
- §1 非目标（公众号长图 / AI 分页 / 图片持久化）→ 计划内均未实现，符合 YAGNI ✅

**2. Placeholder scan：** 无 TBD/TODO（迁移文件名 hash 由约定固定为 `b2c3d4e5f6a7`，非占位）；每个代码步骤均有完整代码；测试均有真实断言。✅

**3. Type consistency：**
- `Page(index, kind, title, paragraphs)` 在 paginate_service 定义，render_service / 路由 / 测试一致引用 ✅
- `PaginationResult(pages, page_count, overflow)` 字段在 Task 3 定义，Task 7 路由读取一致 ✅
- `paginate(raw_text, cover_title)`、`render_cards(pages, template)`、`render_page_html(page, template, total)`、`get_browser()`、`shutdown_browser()` 签名跨任务一致 ✅
- `ImageJobStatus.draft/rendered/failed`（Task 1）与路由状态流转一致 ✅
- schema 字段（`job_id/template/cover_title/pages/page_count/overflow/status`、`images`）在 Task 6 定义、Task 7 构造、测试断言三处一致 ✅
- 路由 `prefix="/image_jobs"` + `include_router(prefix="/api")` → `/api/image_jobs`，与小程序 `api.post('/api/image_jobs')` 一致 ✅
```
