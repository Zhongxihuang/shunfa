# 顺发 Shunfa

> AI 驱动的发文习惯养成工具 — 通过连胜机制帮科技从业者克服完美主义，建立每日表达习惯。

「写完了再想好不好。」

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com) [![Next.js](https://img.shields.io/badge/Frontend-Next.js%2016-black)](https://nextjs.org)

**在线 Demo：** _待补充_ · **上线清单：** [docs/launch-checklist.md](docs/launch-checklist.md)

---

## 目录

- [产品 Insight](#产品-insight)
- [项目亮点](#项目亮点)
- [在线 Demo 与截图](#在线-demo-与截图)
- [技术栈](#技术栈)
- [BYOK（Bring Your Own Key）](#byokbring-your-own-key)
- [快速启动](#快速启动)
- [核心流程](#核心流程)
- [项目结构](#项目结构)
- [游戏化机制](#游戏化机制)
- [部署](#部署)
- [主要 API 端点](#主要-api-端点)
- [开源说明](#开源说明)

---

## 产品 Insight

顺发解决一个问题：**想写，但总觉得写得不够好，于是永远不发布**。

三步流程：AI 提供选题 → 一对一讨论打磨角度 → 生成初稿一键发布。配合连胜/积分/等级机制，把「开始写」变成不需要意志力的日常习惯。

---

## 项目亮点

- 🧩 **三端一体** — FastAPI 后端 + Next.js 14 Web + 微信小程序，共享同一套 API 与业务逻辑。
- 🔑 **BYOK 安全模型** — 用户自带 DeepSeek Key，Fernet 加密存储，作者无法查看明文，AI 费用用户自付。
- 📊 **可度量的留存** — 内建埋点 → 漏斗 → 北极星指标（≥3 天连胜占发布者比例），运营靠数据而非感觉。
- 🗞️ **自动化选题供给** — RSS 抓取 → 事实增强 → 网络检索的热点管线，降低「今天写什么」的摩擦。
- ✅ **工程纪律** — 293 个测试函数（359 passed，含参数化）、4 条 CI 流水线、16 个 Alembic 迁移、可勾选的上线检查清单。
- 🚀 **可落地** — 一键部署 Vercel + Railway，Fork 后改 `.env` 即可启动，无需改代码。

---

## 在线 Demo 与截图

> 🚧 占位区：截图与录屏待补充。建议把静态图放在 `docs/assets/` 下，引用相对路径即可在 GitHub 与 Vercel 正常渲染。

| 入口 | 链接 |
|------|------|
| Web 应用（线上） | _待部署后补充 Vercel 链接_ |
| 后端 API（线上） | _待部署后补充 Railway 链接_ |
| 演示录屏（30s） | _待补充 YouTube / Bilibili 链接_ |

**界面截图**

<!-- 替换为真实截图：把图片放到 docs/assets/ 后改用 ![描述](docs/assets/xxx.png) -->

| 选题 | AI 讨论 | 初稿预览 | 个人主页 |
|:----:|:------:|:-------:|:-------:|
| _截图待补充_ | _截图待补充_ | _截图待补充_ | _截图待补充_ |

| 漏斗 / 北极星看板（Admin） | 连胜 / 等级 / 钻石 |
|:------------------------:|:-----------------:|
| _截图待补充_ | _截图待补充_ |

---

## 技术栈

| 层 | 技术 |
|----|------|
| Web 前端 | Next.js 16（App Router）+ Tailwind CSS |
| 后端 | FastAPI + SQLAlchemy（同步 Session，SQLite WAL） |
| AI | DeepSeek API（OpenAI SDK 兼容，用户自带 Key） |
| 数据库 | SQLite（开发） / PostgreSQL（生产可选） |
| 部署 | Vercel（前端）+ Railway（后端） |

---

## BYOK（Bring Your Own Key）

顺发采用用户自带 DeepSeek API Key 模式：

1. 注册账号后在 **设置页面** 粘贴你的 DeepSeek API Key
2. Key 加密存储在你的账号下，作者无法查看明文
3. 所有 AI 调用使用你自己的 Key，费用由你的 DeepSeek 账户承担
4. 可随时在设置页面更换或删除 Key

自行部署时，也可以在 `.env` 中设置 `DEEPSEEK_API_KEY` 作为系统级 fallback，并将 `REQUIRE_USER_API_KEY=false`。

---

## 快速启动

### 前置条件

- Python 3.11+
- Node.js 18+
- [DeepSeek API Key](https://platform.deepseek.com/api_keys)（使用时需要）

### 1. 后端

```bash
cd backend
pip install -r requirements.txt

# 复制环境变量模板并填写
cp ../.env.example .env
# 必填：JWT_SECRET_KEY（随机字符串）、API_KEY_ENCRYPTION_SECRET（随机字符串）
# 可选：DEEPSEEK_API_KEY（系统级 fallback，默认不需要）
# 可选：DEEPSEEK_BASE_URL（默认 https://api.deepseek.com）

# 运行数据库迁移
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload --port 8080
```

### 2. Web 前端

```bash
cd web
npm install

# 复制环境变量模板
cp .env.example .env.local
# 如后端不在 8080 端口，修改 NEXT_PUBLIC_API_URL

npm run dev
# 访问 http://localhost:3000
```

### 3. 运行测试

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

DEEPSEEK_API_KEY=test JWT_SECRET_KEY=supersecretkey123456789 \
  API_KEY_ENCRYPTION_SECRET=testencryptionsecretkey12345678 \
  pytest -v

ruff check app tests
ruff format --check app tests
mypy app --ignore-missing-imports
```

所有自动化测试均 mock AI 调用或使用本地替身服务，无需真实 API Key。

本地跑完整 AI HTTP 形状 smoke 时，可以启动 DeepSeek 兼容 mock：

```bash
cd backend
python -m scripts.mock_deepseek_server --port 1081

# 另一个终端启动后端时设置：
DEEPSEEK_BASE_URL=http://127.0.0.1:1081/v1
```

---

## 核心流程

```
注册/登录 → 设置 DeepSeek API Key → 选题 → AI 讨论 → 生成初稿 → 发布 → 积分+连胜
```

**CheckIn 状态流**

```
topic_selected → discussing → draft_ready → pending → completed
```

---

## 项目结构

```
shunfa/
├── backend/
│   ├── app/
│   │   ├── routers/        # API 路由（user, topics, content, hot_topics）
│   │   ├── services/       # 业务逻辑（ai, topic, discussion, draft, streak, points）
│   │   ├── utils/          # crypto.py（Fernet 加密）、time_utils.py
│   │   ├── models.py       # User, CheckIn, TopicHistory, HotTopic
│   │   ├── schemas.py      # Pydantic 请求/响应模型
│   │   ├── config.py       # pydantic-settings 配置
│   │   ├── dependencies.py # JWT 鉴权 + get_resolved_api_key（BYOK 三级解析）
│   │   └── database.py     # engine + WAL 模式
│   ├── alembic/versions/   # 数据库迁移历史
│   └── tests/              # 后端自动化测试（mock AI / 本地 AI 替身）
└── web/
    ├── src/app/            # Next.js App Router 页面（login, topics, discuss, preview, compose, drafts, history, profile, settings, image-cards）
    ├── src/components/     # 共用组件（Navbar, StreakBadge, LevelProgress, DiamondDisplay）
    └── src/lib/            # api.ts（自动注入 X-User-Api-Key）、auth.tsx（AuthContext）
```

---

## 游戏化机制

| 指标 | 计算规则 |
|------|---------|
| 每日积分 | 基础 +30，连续加成 +5/天（上限 +30），选题 +10，讨论轮次 +3/轮（上限 +9），按时 +5 |
| 等级 | 7 级阈值：0 / 100 / 300 / 700 / 1500 / 3100 / 6300 积分 |
| 钻石 | 3 + floor(总积分 / 100) |
| 连胜 | 连续发文天数；断开超过 1 天清零 |

---

## 部署

Before production deployment, complete [docs/launch-checklist.md](docs/launch-checklist.md). The checklist includes migration rollback, PostgreSQL verification, BYOK redaction, timeout policy, rate limits, Web build, and manual smoke validation.

### Vercel（前端）

```bash
cd web
vercel --prod
# 设置环境变量：NEXT_PUBLIC_API_URL=https://your-backend.railway.app
```

### Railway（后端）

将 `backend/` 目录部署到 Railway，设置以下环境变量：

```
JWT_SECRET_KEY=<随机 32 字符>
API_KEY_ENCRYPTION_SECRET=<随机 32 字符>
REQUIRE_USER_API_KEY=true
DATABASE_URL=sqlite:///./shunfa.db
CORS_ORIGINS=https://your-app.vercel.app
```

---

## 主要 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/register` | 注册账号（username + password） |
| POST | `/api/auth_login` | 登录，返回 JWT |
| GET | `/api/user/api_key/status` | 查询 API Key 配置状态 |
| POST | `/api/user/api_key` | 保存（加密存储）用户 API Key |
| GET | `/api/hot_topics/today` | 获取今日 3 个推荐热点 |
| POST | `/api/select_topic` | 选题，创建 CheckIn |
| POST | `/api/daily_topics` | 获取 AI 生成选题（需 API Key） |
| POST | `/api/generate_content` | 讨论 + 生成初稿（需 API Key） |
| POST | `/api/confirm_publish` | 发布，触发积分 + 连胜计算 |
| GET | `/api/user_status` | 当前用户状态 |

---

## 开源说明

- 仓库中不含任何真实 API Key 或用户数据
- 微信 AppID 已替换为 `YOUR_WECHAT_APPID` 占位符
- Fork 后只需修改 `.env` 即可启动，无需改动代码
- 线上 Demo 强制 BYOK（`REQUIRE_USER_API_KEY=true`），作者不承担 AI 调用费用
