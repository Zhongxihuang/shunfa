---
name: debug-backend
description: 顺发后端调试流程。遇到 API 报错、测试失败、业务逻辑问题时使用。
---

# 顺发后端调试流程

## 快速诊断

### 1. 先跑测试，看哪里失败

```bash
cd /Users/huangzhongxi/shunfa/backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v --tb=short
```

### 2. 启动开发服务器（需要真实 .env）

```bash
cd /Users/huangzhongxi/shunfa/backend
uvicorn app.main:app --reload --port 8000
# 访问 http://localhost:8000/docs 查看 Swagger UI
```

### 3. 手动测试端点

```bash
# 健康检查
curl http://localhost:8000/health

# 登录（需要小程序 code，或用 mock）
curl -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"code": "test_code"}'
```

## 常见问题

### 400 Bad Request
- 检查 schemas.py 的 validation（min_length, max_length, 类型）
- 看 response body 里的 `detail` 字段

### 401 Unauthorized
- 请求头是否有 `Authorization: Bearer <token>`？
- JWT 是否过期（720h，约30天）？
- `JWT_SECRET_KEY` 环境变量是否设置？

### 422 Unprocessable Entity
- Pydantic validation 失败
- 检查请求 body 字段名和类型是否匹配 schema

### 500 Internal Server Error
- 看 uvicorn 控制台输出
- 常见原因：DB session 未关闭、模型字段不存在（忘删 db 重建）

### 测试失败：`sqlalchemy.exc.OperationalError: no such column`
```bash
# 模型加了字段但 in-memory DB 是旧的
# 检查：db_engine fixture 是否有 Base.metadata.create_all(bind=engine)
```

### 测试失败：日期/时区不匹配
- 测试里用了 `date.today()` 而不是 `get_today_cst()`
- 替换为：`from app.utils.time_utils import get_today_cst; today = get_today_cst()`

### 测试失败：SQLAlchemy 返回缓存数据
```python
db.expire_all()  # 强制下次查询刷新
updated = db.query(User).filter(User.id == user.id).first()
```

### AI 服务调用失败（真实环境）
- 检查 `DEEPSEEK_API_KEY` 是否正确
- 检查 `ai_service.py` 中 `base_url="https://api.deepseek.com"` 和 `model="deepseek-chat"`

## 状态机调试

CheckIn 状态流：`topic_selected → discussing → draft_ready → pending → completed`

```bash
# 直接查看 DB 状态（SQLite）
sqlite3 /Users/huangzhongxi/shunfa/backend/shunfa.db \
  "SELECT id, topic, status, refresh_count FROM checkins ORDER BY id DESC LIMIT 5;"
```

## 积分/连胜问题

```python
# 在 Python shell 里快速验证
cd backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=test python3
>>> from app.services.points_service import calculate_level, calculate_diamonds, calculate_points_earned
>>> calculate_level(350)  # → 3
>>> calculate_diamonds(250)  # → 5
```
