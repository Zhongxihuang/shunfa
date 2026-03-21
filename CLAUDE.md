# 顺发 (Shunfa) — 开发指南

游戏化发文助手：通过「已连更」机制帮用户克服完美主义、建立每日表达习惯。

## 快速启动

```bash
# 后端
cd backend
pip install -r requirements.txt
cp ../../.env.example .env   # 填入真实 key
uvicorn app.main:app --reload

# 测试（不需要真实 API key）
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v
```

小程序：微信开发者工具打开 `miniprogram/` 目录，修改 `project.config.json` 中的 `appid`。

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
└── miniprogram/
    ├── utils/api.js     # Promise wx.request 封装
    ├── utils/auth.js    # wx.login() → POST /api/login → 存 token
    ├── pages/           # index, topics, discuss, preview, profile, settings
    └── components/      # streak-badge, level-progress, diamond-display, topic-card
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

**加新模型字段**: models.py → schemas.py → 生成迁移（目前直接 drop+create，生产前需 alembic）

**调整 AI 提示词**: `services/topic_service.py`（选题）或 `services/content_service.py`（讨论/初稿）

**小程序调用新接口**: `utils/api.js` 已封装，直接 `api.post('/api/xxx', data)`

## 已知 TODO（v1.1+）

- [ ] Alembic 数据库迁移
- [ ] AsyncSession（目前 sync Session 在 async FastAPI，SQLite WAL 下可接受）
- [ ] JWT refresh token / revocation
- [ ] WeChat 订阅消息（真正的推送提醒）
- [ ] `ConfirmContentRequest.content` 字段长度校验
- [ ] 连续 check-in 防 double-publish 的数据库级唯一约束
