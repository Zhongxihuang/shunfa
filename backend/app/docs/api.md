# 顺发 API 文档

> 基于 FastAPI + Pydantic v2，JWT 认证（720h 过期）

## 认证

除 `/api/login` 和 `/api/web_login` 外，所有端点需要在 Header 中携带：

```
Authorization: Bearer <token>
```

---

## 端点索引

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/login` | 微信 code 换 JWT |
| POST | `/api/web_login` | 管理员密码登录 |
| GET | `/api/hot_topics/today` | 获取今日推荐热点 |
| POST | `/api/quick_generate` | 快速模式生成初稿 |
| POST | `/api/select_topic` | 选题，创建 CheckIn |
| POST | `/api/confirm_content` | 质量校验 |
| POST | `/api/confirm_publish` | 发布，触发积分+连胜计算 |
| GET | `/api/user_status` | 当前用户状态 |
| GET | `/api/achievements` | 用户成就列表 |
| GET | `/api/checkin/{checkin_id}` | 获取 CheckIn 详情（含 topic/content） |

---

## 核心端点签名

### 1. POST `/api/login`

微信小程序 code 换 JWT。

**Request**

```json
{
  "code": "微信 wx.login() 返回的 code"
}
```

**Response** `200`

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "streak": 3,
    "longest_streak": 7,
    "points": 145,
    "level": 2,
    "diamonds": 4,
    "reminder_time": "21:00",
    "reminder_enabled": true,
    "last_checkin_date": "2026-04-26",
    "today_completed": false,
    "reminder_needed": true
  }
}
```

---

### 2. GET `/api/hot_topics/today`

获取今日 3 个推荐热点（从飞书 Bitable 或本地缓存返回）。

**Response** `200`

```json
{
  "date": "2026-04-26",
  "topics": [
    {
      "id": 12,
      "title": "Claude 4 发布，GPT-4 份额首度下滑",
      "summary": "Anthropic 发布 Claude 4 系列模型...",
      "source": "Hacker News",
      "url": "https://news.ycombinator.com/item?id=...",
      "published_at": "2026-04-26T08:00:00Z",
      "score": 8,
      "category": "ai_model",
      "ai_angle": "模型能力军备竞赛降温，垂直场景成新战场",
      "ai_counter_angle": "Claude 4 在长上下文仍领先，GPT-4 护城河未被动摇"
    }
  ]
}
```

---

### 3. POST `/api/quick_generate`

快速模式：给定话题和角度，直接生成初稿。

**Request**

```json
{
  "hot_topic": "Claude 4 发布",
  "angle": "模型能力军备竞赛降温，垂直场景成新战场",
  "platform": "xiaohongshu",
  "topic_id": 12,
  "checkin_id": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| hot_topic | string | 话题标题 |
| angle | string | 写作角度/立场 |
| platform | string | `xiaohongshu` / `twitter` / `linkedin` |
| topic_id | int? | 关联热点 ID（可选） |
| checkin_id | int? | 关联 CheckIn ID（可选） |

**Response** `200`

```json
{
  "content": "Claude 4 发布了。\n\n最让我意外的不是模型本身...",
  "platform": "xiaohongshu",
  "char_count": 187
}
```

---

### 4. POST `/api/confirm_publish`

质量校验通过后，正式发布。触发积分计算和连胜更新。

**Request**

```json
{
  "checkin_id": 42
}
```

**Response** `200`

```json
{
  "streak": 4,
  "points_earned": 45,
  "total_points": 190,
  "level": 2,
  "diamonds": 4,
  "message": "连胜 4 天，继续保持！",
  "newly_unlocked": [
    {
      "type": "streak_7",
      "name": "一周之约",
      "desc": "连续 7 天发文"
    }
  ]
}
```

**积分计算规则：**

- 每日发文基础 +30
- 连续加成 +5/天（上限 +30）
- 选题完成 +10
- 讨论轮次 +3/轮（上限 +9）
- 按时（提醒时间后 2h 内）+5

---

### 5. GET `/api/user_status`

获取当前登录用户状态。

**Response** `200`

```json
{
  "id": 1,
  "streak": 3,
  "longest_streak": 7,
  "points": 145,
  "level": 2,
  "diamonds": 4,
  "reminder_time": "21:00",
  "reminder_enabled": true,
  "last_checkin_date": "2026-04-26",
  "today_completed": false,
  "reminder_needed": true
}
```

---

## 错误响应格式

所有错误返回标准 HTTP 状态码，body 格式：

```json
{
  "detail": "错误描述"
}
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | Token 无效或已撤销 |
| 403 | 管理员权限不足 |
| 404 | 资源不存在 |
| 422 | Pydantic 校验失败 |
| 503 | 外部服务（微信/DeepSeek）不可用 |
