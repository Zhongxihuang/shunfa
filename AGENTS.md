# 顺发 (Shunfa) — 开发指南

顺发当前上线目标是 Web + FastAPI 后端闭环：注册/登录、BYOK DeepSeek API Key、热点/选题、生成/讨论、预览发布、积分/连胜、个人页状态更新。

## 快速启动

```bash
# 后端
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # 填入 JWT_SECRET_KEY / API_KEY_ENCRYPTION_SECRET
alembic upgrade head
uvicorn app.main:app --reload --port 8080

# Web
cd ../web
npm install
npm run dev

# 测试（不需要真实 API key）
cd ../backend
DEEPSEEK_API_KEY=test JWT_SECRET_KEY=supersecretkey123456789 \
  API_KEY_ENCRYPTION_SECRET=testencryptionsecretkey12345678 \
  pytest -v
ruff check app tests
ruff format --check app tests
mypy app --ignore-missing-imports
cd ../web
npm run lint
npm run build
```

## 项目结构

```
shunfa/
├── backend/app/
│   ├── main.py          # FastAPI 入口，CORS，lifespan
│   ├── config.py        # pydantic-settings（pydantic-settings BaseSettings）
│   ├── database.py      # SQLAlchemy engine + WAL mode
│   ├── dependencies.py  # get_db(), get_current_user() (HTTPBearer + JWT)
│   ├── models.py        # User, CheckIn, TopicHistory
│   ├── schemas.py       # Pydantic 请求/响应模型
│   ├── routers/         # topics, content, user, reminder（均挂在 /api 前缀）
│   ├── services/        # ai, topic, content, streak, points, reminder
│   └── utils/time_utils.py  # get_today_cst(), is_consecutive_day(), is_reminder_time_active()
├── miniprogram/
    ├── utils/api.js     # Promise wx.request 封装
    ├── utils/auth.js    # wx.login() → POST /api/login → 存 token
    ├── pages/           # index, topics, discuss, preview, profile, settings
    └── components/      # legacy/non-launch mini program components
└── web/
    ├── src/app/         # login, topics, compose, discuss, preview, profile, settings
    ├── src/components/  # Web UI components
    └── src/lib/         # api.ts, auth.tsx
```

## 核心数据模型

```
User: openid, streak, longest_streak, points, level, diamonds, reminder_time, reminder_enabled
CheckIn: user_id, date(CST), topic, content, conversation_history(JSON), status(enum), refresh_count
TopicHistory: user_id, topic, batch_id(UUID), was_used
```

**CheckIn 状态流**: `topic_selected → discussing → draft_ready → pending → completed`

## 关键架构决策

| 决策 | 方案 | 原因 |
|------|------|------|
| 时区 | 硬编码 Asia/Shanghai (pytz) | v1.0 仅中国用户 |
| DeepSeek 接入 | openai SDK，base_url="https://api.deepseek.com" | API 兼容，无需自定义 HTTP |
| 对话状态 | CheckIn.conversation_history (JSON Text 字段) | 对话短(2-4轮)，避免额外表 |
| SQLite 配置 | WAL 模式 + check_same_thread=False | 支持 FastAPI 并发读 |
| 提醒 | App 内轮询（/api/user_status 返回 reminder_needed） | 避免微信订阅消息复杂审批 |
| JWT | HTTPBearer + python-jose，720h 过期 | 无刷新机制，MVP 可接受 |

## 积分规则（confirm_publish 时计算）

- 每日发文 +30
- 连续加成 +5/天，上限 +30（streak × 5，cap 30）
- 选题完成 +10
- 讨论轮次 +3/轮，上限 +9（user messages × 3，cap 9）
- 按时（reminder_time 后 2h 内）+5

等级阈值: `[0, 100, 300, 700, 1500, 3100, 6300]`（7 级）
钻石公式: `diamonds = 3 + floor(total_points / 100)`

## AI 提示词约定

- **选题**: 输出3行，每行15-30字，用 `\n` 分隔
- **讨论/初稿**: 系统提示包含 `{topic}` 占位符；初稿用 `<<<DRAFT_START>>>内容<<<DRAFT_END>>>` 标记
- **最少1轮讨论**才接受 draft 标记（MIN_DISCUSSION_ROUNDS = 1）
- **超过3轮**强制调用 `_force_generate_draft()`

## 测试约定

```bash
pytest tests/test_streak.py   # 连胜边界（7 tests）
pytest tests/test_points.py   # 积分计算（8 tests）
pytest tests/test_topics.py   # 去重+刷新限制（6 tests）
pytest tests/test_content.py  # 状态流+防重复（8 tests）
pytest tests/test_user.py     # JWT+登录（5 tests）
```

- 所有测试用 in-memory SQLite（`sqlite://`）
- AI 调用全部 mock（`patch("app.services.xxx_service.chat_completion")`）
- 日期用 `get_today_cst()` 而非 `date.today()`

## 常见开发任务

**加新 API 端点**: router → schema → service → 在 main.py 已有 router 中注册（无需修改 main.py）

**加新模型字段**: models.py → schemas.py → 生成/检查 Alembic 迁移 → 跑 migration tests

**调整 AI 提示词**: `services/topic_service.py`（选题）或 `services/content_service.py`（讨论/初稿）

**Web 调用新接口**: `web/src/lib/api.ts` 已封装，AI 生成类端点使用 `api.postGeneration()`，发布端点不要自动重试。

**小程序调用新接口**: `miniprogram/utils/api.js` 是 legacy/non-launch 路径，本轮上线不以小程序验收为准。

## 已知 TODO（v1.1+）

- [ ] AsyncSession（目前 sync Session 在 async FastAPI，SQLite WAL 下可接受）
- [ ] JWT refresh token / revocation
- [ ] WeChat 订阅消息（legacy 小程序路径）
- [ ] `ConfirmContentRequest.content` 字段长度校验
