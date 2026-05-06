# 顺发 Shunfa

> AI 驱动的发文习惯养成工具 — 通过连胜机制帮科技从业者克服完美主义，建立每日表达习惯。

「写完了再想好不好。」

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](https://fastapi.tiangolo.com) [![Next.js](https://img.shields.io/badge/Frontend-Next.js%2014-black)](https://nextjs.org)

---

## 产品 Insight

顺发解决一个问题：**想写，但总觉得写得不够好，于是永远不发布**。

三步流程：AI 提供选题 → 一对一讨论打磨角度 → 生成初稿一键发布。配合连胜/积分/等级机制，把「开始写」变成不需要意志力的日常习惯。

---

## 技术栈

| 层 | 技术 |
|----|------|
| Web 前端 | Next.js 14（App Router）+ Tailwind CSS |
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
DEEPSEEK_API_KEY=test JWT_SECRET_KEY=supersecretkey123456789 \
  API_KEY_ENCRYPTION_SECRET=testencryptionsecretkey12345678 \
  pytest -v
```

所有测试均 mock AI 调用，无需真实 API Key，全套 152 个测试用例。

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
│   └── tests/              # 152 个测试（全 mock AI）
└── web/
    ├── src/app/            # Next.js App Router 页面（login, topics, discuss, preview, profile, settings）
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
