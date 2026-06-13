# 粘贴排版成小红书卡片 — 设计文档

**日期：** 2026-06-08
**状态：** 已通过设计评审，待写实现计划
**作者：** 顺发团队

---

## 1. 背景与目标

顺发现有的内容生产链路是「选题 → 讨论 → 生成初稿 → 发布」，面向**从零创作**。
本功能新增一条**前置的、自定义的入口**：用户把**已经写好/已经定稿**的文章粘贴进来，
系统将其自动排版成一组**极具设计感、符合小红书发文美学**的连续卡片图。

### 核心价值
「美观排版」而非「再创作」。输入是用户定稿的文字，价值在于把它变成好看、能直接发的图。

### 目标
- 用户粘贴纯文本 → 选模板 → 实时预览 → 渲染高清卡片图 → 保存到相册。
- 三套可切换的卡片美学模板：A 暖纸编辑 / B 瑞士现代 / C 撞色高定。
- 渲染质量达到「平台原生高级内容」水准（这是第一需求）。

### 非目标（本迭代不做，YAGNI）
- ❌ 微信公众号长图（图片形态差异大，留下一迭代）
- ❌ AI 智能分页 / 金句提炼（后续可按「确定性为主 + 可选 AI 增强」扩展）
- ❌ 图片二进制持久化 / 云存储
- ❌ 自定义字体上传、自定义配色

---

## 2. 关键约束

| 约束 | 说明 |
|------|------|
| **AI 红线** | 分页**纯确定性规则**，一字不改用户原文。本功能**不调用 DeepSeek**。 |
| **解耦** | 独立实体 `ImageJob`，**不进连胜、不计积分、不复用 CheckIn**。 |
| **非商业指标** | 埋点只观察功能使用，不引入 DAU / 转化 / GMV。 |
| **渲染保真** | 后端 HTML/CSS → PNG（headless Chromium），美学优先于轻量。 |
| **技术栈** | 沿用 FastAPI + SQLAlchemy(sync, SQLite WAL) + Alembic + Pydantic v2。 |

---

## 3. 数据模型

新增轻量表 `ImageJob`，与 `CheckIn` 完全解耦：

```
ImageJob:
  id            int       PK
  user_id       int       FK -> users.id
  raw_text      Text      # 用户粘贴的原文，原样存储
  template      str       # 'a' | 'b' | 'c'
  cover_title   str|None  # 用户可覆盖的封面文字；空则取首段
  page_count    int       # 渲染出的卡片总数（含封面），分页后回填
  status        str(enum) # 'draft' | 'rendered' | 'failed'
  created_at    datetime  # CST，用 get_now_cst()
```

- **不存图片二进制**。图片按需渲染后直接返回，需要重看则重渲。
- 需要一支 **Alembic 迁移**新建该表。
- `status` 用与现有 `CheckInStatus` 一致的 Python `enum.Enum` + SQLAlchemy `Enum` 列风格。

---

## 4. 确定性分页规则（核心逻辑）

新增 `services/paginate_service.py`，纯函数、无 AI、可完全单测。

### 输入
`raw_text: str`, `cover_title: str | None`

### 算法
1. **清洗**：按 `\n` 切段，`strip()` 每段，丢弃空段，得到 `paragraphs: list[str]`。
2. **封面页**：
   - `cover_title` 非空 → 用作封面标题；
   - 否则取 `paragraphs[0]` 作封面金句，并将其从正文段落中移除。
   - 封面页只含：标题文字 + 角标（`01 / 0N`）+ 落款「顺发 · 行业洞察」。
3. **内容页填充**：剩余段落顺序灌入卡片，每页容量上限：
   - `MAX_CHARS_PER_PAGE = 240`（按字符数估算）
   - `MAX_PARAS_PER_PAGE = 6`
   - 当前段塞进会超限 → 开新页。
4. **超长单段软切**：单段本身 > `MAX_CHARS_PER_PAGE` → 按句号「。」/ 分号「；」/ 问号「？」/ 感叹号「！」就近软切到下一页。**只断行、不删字**。
5. **页数约束**：`MAX_PAGES = 8`（含封面）。
   - 内容超出 8 页 → 返回结构里带 `overflow=True` 标记，前端提示用户精简。**绝不静默截断**。
6. **角标回填**：所有页确定后，统一回填 `index` 与总页数 `01 / 0N`。

### 输出
```
PaginationResult:
  pages: list[Page]        # Page = {index:int, kind:'cover'|'body', title:str|None, paragraphs:list[str]}
  page_count: int
  overflow: bool
```

**确定性保证**：给定相同 `(raw_text, cover_title)`，输出页数与分配完全一致，无随机。

---

## 5. 渲染管线

新增 `services/render_service.py`。

### 流程
1. 接收 `(pages: list[Page], template: str)`。
2. 用 **Jinja2** 把页面数据灌进对应模板的 HTML（`templates/cards/{a,b,c}.html`，复用已验证的 CSS）。
3. **Playwright** 启动 headless Chromium：
   - 视口 `1080 × 1440`（3:4）
   - `device_scale_factor = 2` → 导出 `2160 × 2880` 高清
   - 逐页 `page.screenshot()` 取 PNG 字节
4. 返回每页 PNG（base64 字符串列表，或临时文件 URL）。

### 关键工程点
- **浏览器实例复用**：进程级单例 `browser`，避免每张图冷启 Chromium。在 FastAPI lifespan 中启动/关闭。
- **字体依赖**：模板声明的中文字体（宋体 / 苹方 / Georgia 等）必须在运行环境可用。
  这是**唯一的部署前提**，标注为「运行依赖」。本地开发机已满足。
- **失败处理**：渲染异常 → `ImageJob.status='failed'`，返回 502 + 可读错误。

### 三套模板（视觉规格，已通过评审）
| 模板 | 气质 | 底色 | 标题字体 | 撞色 |
|------|------|------|----------|------|
| **A 暖纸编辑** | 古典、温暖、文气 | 奶油纸 `#f3ece0` | Georgia / 宋体衬线 | 细金线 `#cdbfa6` |
| **B 瑞士现代** | 冷峻、图形化、当代 | 近白 `#f7f6f3` | Helvetica/苹方 800 无衬线 | 朱红 `#e8401f` + 3px 黑杠 |
| **C 撞色高定** | 戏剧、饱和、大片感 | 深钴蓝渐变 `#1c3f8f→#0d1f4d` | 宋体奶白展示 | 暖金下划线 `#e8b04f` |

三者分别在 **暖/冷/暗**、**衬线/无衬线/衬线展示**、**纸感/图形/色场** 三条轴上拉开区分度。

---

## 6. 接口设计（均挂 `/api` 前缀，需 JWT）

新增 `routers/image_jobs.py`，在 `main.py` 现有 router 注册处挂上。

### `POST /api/image_jobs`
建任务 + 跑分页（**不渲染图**，秒回，供前端做文字预览）。
- **请求**：`{ raw_text: str, template: 'a'|'b'|'c', cover_title?: str }`
- **逻辑**：跑 `paginate_service` → 建 `ImageJob(status='draft', page_count=...)` → 提交。
- **响应**：`{ job_id, pages: [...结构化分页...], page_count, overflow }`

### `POST /api/image_jobs/{id}/render`
跑渲染管线，出高清 PNG。允许切模板重渲。
- **请求**：`{ template?: 'a'|'b'|'c' }`（传了就更新 `ImageJob.template` 后重渲）
- **逻辑**：取任务 → 重跑分页（保证与存的文字一致）→ 渲染 → `status='rendered'`。
- **响应**：`{ job_id, template, images: [base64 或 url, ...], page_count }`
- **鉴权**：任务必须属于当前用户，否则 404。

### `GET /api/image_jobs/{id}`
取回某次任务的分页结构（断网恢复 / 历史）。
- **响应**：`{ job_id, raw_text, template, cover_title, pages, page_count, status }`
- **鉴权**：仅本人可读，否则 404。

**切模板** = 改 `template` 重新 `/render`；分页结构不变，只换皮，预览快。

---

## 7. 小程序入口与流程

- 新增独立页面 `pages/compose-image/`。
- 首页（`pages/index/`）加一个「粘贴排版」入口卡，与现有打卡流程并列、不混入连胜。
- **流程**：
  1. 粘贴文本框（多行 textarea）+ 可选「封面文字」输入
  2. 选模板：A/B/C 三个缩略图 tab
  3. 点「生成预览」→ `POST /image_jobs` → 展示文字分页预览（几页、每页放什么）
  4. 满意 → 点「渲染高清图」→ `POST /render` → 逐张展示 PNG
  5. 切模板 → 即时重渲预览（所见即所得）
  6. 长按单图 / 点保存按钮 → `wx.saveImageToPhotosAlbum` 保存到相册
- `utils/api.js` 已封装 `api.post`，**无需改动**。

---

## 8. 轻量埋点（非商业指标）

复用现有 `track(event, user_id, props)`（best-effort，写 Events 表）：

| 事件 | 触发 | props |
|------|------|-------|
| `paste_compose` | 用户提交粘贴文本（`POST /image_jobs`） | `template`, `char_count`, `page_count` |
| `image_rendered` | 成功渲染（`POST /render`） | `template`, `page_count` |

仅为观察功能是否被使用，**不引入 DAU / 转化 / GMV**。

---

## 9. 文件改动清单

### 后端（新增）
- `backend/app/services/paginate_service.py` — 确定性分页
- `backend/app/services/render_service.py` — HTML→PNG 渲染（Playwright 单例）
- `backend/app/templates/cards/a.html` / `b.html` / `c.html` — 三套 Jinja2 模板
- `backend/app/routers/image_jobs.py` — 三个端点
- `backend/alembic/versions/xxxx_add_image_jobs.py` — 建表迁移

### 后端（修改）
- `backend/app/models.py` — `+ ImageJob` 模型与 `ImageJobStatus` enum
- `backend/app/schemas.py` — `+ ImageJobCreateRequest / RenderRequest / 各响应模型`
- `backend/app/main.py` — 注册 `image_jobs` router；lifespan 启停 Playwright 浏览器单例
- `backend/requirements.txt` — `+ playwright`、`+ jinja2`（标注 `playwright install chromium`）

### 小程序（新增）
- `miniprogram/pages/compose-image/` — 新页面（wxml/wxss/js/json）
- `miniprogram/pages/index/` — 加「粘贴排版」入口卡

---

## 10. 测试约定

沿用项目约定：in-memory SQLite（`sqlite://`），AI 全程 mock（本功能不调 AI，仅需 mock 渲染层）。

- **`test_paginate.py`** — 确定性分页：空文本、单段、多段、超长单段软切、`MAX_PAGES` 溢出、`cover_title` 覆盖。给定输入断言确定页数与分配。
- **`test_image_jobs.py`** — 端点：建任务返回分页、鉴权（非本人 404）、切模板重渲、GET 回读。
- **渲染层**：`render_service` 的 Playwright 调用在测试中 mock 掉（断言传入的 HTML / 模板 / 视口参数正确），不真起 Chromium。

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Chromium 部署 / 字体缺失 | 标注为运行依赖；spec 与 requirements 注明 `playwright install chromium`；字体在目标环境预装 |
| 渲染慢（冷启动） | 进程级 browser 单例，lifespan 内常驻 |
| 超长文章页数爆炸 | `MAX_PAGES=8` + `overflow` 提示，绝不静默截断 |
| 用户原文被「改写」的疑虑 | 纯确定性分页，只断行不删字，从架构上杜绝 |
