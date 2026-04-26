# 顺发 Shunfa

> AI 驱动的发文习惯养成工具 — 通过连胜机制帮科技从业者克服完美主义，建立每日表达习惯。

「写完了再想好不好」。

---

## 核心价值

顺发解决一个问题：**想写，但总觉得写得不够好，于是永远不发布**。

通过游戏化机制（连胜、积分、等级）和 AI 初稿生成，把「开始写」变成一个不需要意志力的日常习惯。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | 微信小程序（原生） |
| 后端 | FastAPI + SQLAlchemy（同步 Session，SQLite WAL） |
| AI | DeepSeek API（OpenAI SDK 兼容） |
| 任务队列 | Celery + Redis |
| 数据库 | SQLite（开发） / PostgreSQL（生产） |
| 推送 | 微信订阅消息（可选） |
| 数据同步 | 飞书 Bitable（可选） |
| 监控 | Prometheus + Sentry |
| 容器 | Docker + docker-compose |

---

## 快速启动

### 1. 后端

```bash
cd backend
pip install -r requirements.txt

# 复制并填写环境变量
cp ../.env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 和 WECHAT_APP_ID/WECHAT_APP_SECRET

# 启动开发服务器
uvicorn app.main:app --reload --port 8080
```

### 2. 小程序

1. 下载并打开微信开发者工具
2. 导入项目目录选择 `miniprogram/`
3. 修改 `project.config.json` 中的 `appid` 为你的小程序 AppID
4. 填入后端地址（在 `utils/api.js` 的 `baseUrl` 中）

### 3. 测试（无需真实 key）

```bash
cd backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test \
  JWT_SECRET_KEY=supersecretkey123456789 \
  pytest -v
```

---

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     微信小程序                              │
│  首页  选题  讨论/预览  历史  我的                         │
└──────────┬──────────────────────────────────┬─────────────┘
           │  HTTP + JWT (720h)               │
           ▼                                  ▼
┌─────────────────────────────────────────────────────────────┐
│                 FastAPI (:8080)                            │
│                                                             │
│   user ── content ── topics ── hot_topics ── reminder  │
│         routers/          services/           middleware/  │
│         schemas/         ai_service/         celery_tasks/│
└──────────┬──────────────────┬─────────────────┬────────────┘
           │                  │                  │
     ┌─────▼─────┐   ┌──────▼──────┐  ┌──────▼──────┐
     │  SQLite    │   │  DeepSeek   │  │   Redis      │
     │  WAL 模式  │   │  API         │  │  (Celery)    │
     └────────────┘   └─────────────┘  └──────────────┘
```

**CheckIn 状态流**

```
topic_selected → discussing → draft_ready → pending → completed
```

---

## 主要 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/login` | 微信 code 换 JWT |
| GET | `/api/hot_topics/today` | 获取今日 3 个推荐热点 |
| POST | `/api/select_topic` | 选题，创建 CheckIn |
| POST | `/api/quick_generate` | 快速模式生成初稿 |
| POST | `/api/confirm_content` | 质量校验 |
| POST | `/api/confirm_publish` | 发布，触发积分+连胜计算 |
| GET | `/api/user_status` | 当前用户状态 |
| POST | `/api/revoke_token` | 撤销用户 token（管理员） |

---

## 游戏化机制

| 指标 | 计算规则 |
|------|---------|
| 每日积分 | 基础 +30，连续加成 +5/天（上限 +30），选题 +10，讨论轮次 +3/轮（上限 +9），按时 +5 |
| 等级 | 7 级：0 / 100 / 300 / 700 / 1500 / 3100 / 6300 积分 |
| 钻石 | 3 + floor(points / 100) |
| 连胜 | 连续发文；断开超过 1 天清零 |

---

## 截图

| 页面 | 说明 |
|------|------|
| `drafts-preview.png` | 草稿箱 |
| `history-preview.png` | 历史记录 |
| `profile-preview-1.png` | 个人中心 + 成就 |

（更多截图待补充）

---

## 项目结构

```
shunfa/
├── backend/
│   ├── app/
│   │   ├── routers/       # API 路由（user, topics, content, hot_topics, reminder）
│   │   ├── services/      # 业务逻辑（ai, topic, content, streak, points, achievement）
│   │   ├── models.py      # SQLAlchemy 模型
│   │   ├── schemas.py     # Pydantic 请求/响应模型
│   │   ├── config.py      # pydantic-settings 配置
│   │   ├── database.py    # engine + WAL 模式
│   │   ├── dependencies.py # JWT 鉴权
│   │   ├── middleware.py  # RequestID + RequestLogging
│   │   └── metrics.py     # Prometheus 自定义指标
│   ├── tests/             # 140+ 测试（mock AI 调用）
│   ├── scripts/           # backup.sh, migrate_to_postgresql.sh
│   ├── celery_app.py     # Celery 实例
│   ├── Dockerfile         # 多阶段构建
│   └── docker-compose.yml # PostgreSQL + Redis + Backend + Celery
└── miniprogram/
    ├── pages/             # 8 个页面（index, topics, discuss, preview, profile, settings, history, drafts）
    ├── components/        # 4 个组件（topic-card, streak-badge, level-progress, diamond-display）
    └── utils/             # api.js, auth.js
```

---

## 数据备份

```bash
# 每天凌晨 3 点自动备份（crontab）
0 3 * * * bash /path/to/shunfa/backend/scripts/backup.sh

# 手动恢复
bash scripts/restore.sh shunfa_backup_YYYYMMDD_HHMMSS.db
```

---

## 生产部署

```bash
cd backend
docker-compose up -d
# 访问 http://localhost:8080/docs 查看 API 文档
```
