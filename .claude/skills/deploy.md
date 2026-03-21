---
name: deploy
description: 顺发部署清单。准备上线、更新生产环境时使用。包含后端部署和小程序发布两条流程。
---

# 部署清单

## 后端部署（FastAPI + SQLite）

### 部署前检查

```bash
# 1. 全套测试通过
cd /Users/huangzhongxi/shunfa/backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v

# 2. 检查敏感信息没有提交
git log --oneline -5
git diff HEAD~1 HEAD -- .env  # 不应该有 .env 的改动

# 3. 确认 .env.example 是最新的（新加的配置项有对应占位符）
cat /Users/huangzhongxi/shunfa/.env.example
```

### 生产环境配置

```bash
# .env（服务器上，不提交到 git）
DEEPSEEK_API_KEY=sk-xxx           # 真实 key
WECHAT_APP_ID=wxxxxxxxxxxx        # 小程序 AppID
WECHAT_APP_SECRET=xxxxxxxxxxxxxx  # 小程序 Secret
JWT_SECRET_KEY=<随机32位以上字符串>  # openssl rand -hex 32
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=720
DATABASE_URL=sqlite:///./shunfa.db
ENVIRONMENT=production
```

生成安全的 JWT secret：
```bash
openssl rand -hex 32
```

### 部署命令（基础版，无容器化）

```bash
# 安装依赖
pip install -r requirements.txt

# 数据库初始化（首次部署）
# lifespan 会自动 create_all，启动即可

# 启动（生产用 gunicorn 或 systemd）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# 或用 gunicorn
gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 数据库注意事项

- **当前无迁移工具**（无 Alembic）
- 加字段时：如果是新部署直接 drop + create_all；如果是更新生产需要手动 `ALTER TABLE`
- SQLite WAL 模式已启用，支持并发读，写操作自动串行化
- 备份：定期 `cp shunfa.db shunfa.db.bak`

### CORS 配置（生产前修改）

当前 `main.py` 允许所有来源（`allow_origins=["*"]`）。
上线前改为只允许小程序域名（如果有 H5 版本）或直接限制为内网：

```python
# main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],  # 改这里
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 小程序发布

### 发布前检查

```
□ app.js 中 baseUrl 已改为生产服务器地址（不是 localhost:8000）
□ project.config.json 中 appid 是正式 AppID（不是 your_app_id 占位符）
□ 微信开发者工具 → 详情 → 本地设置 → 不勾选「不校验合法域名」（生产必须合法）
□ 后端服务器域名已在微信小程序后台配置为 request 合法域名（需要 HTTPS）
□ 上传代码前做一次真机预览测试
```

### 修改生产 baseUrl

```javascript
// miniprogram/app.js
App({
  globalData: {
    baseUrl: 'https://api.your-domain.com'  // 改这里，必须 HTTPS
  }
})
```

### 发布流程

```
1. 微信开发者工具 → 上传 → 填写版本号和备注
2. 微信公众平台 → 版本管理 → 提交审核
3. 审核通过后 → 发布
```

### 常见发布问题

**request 不合法域名**：
→ 微信公众平台 → 开发 → 开发设置 → 服务器域名 → 添加 request 合法域名

**openid 获取失败**：
→ 确认 WECHAT_APP_ID / WECHAT_APP_SECRET 是发布版（不是测试版）的

**HTTPS 证书问题**：
→ 微信要求 TLS 1.2+，Let's Encrypt 证书满足要求

---

## 回滚方案

### 后端回滚
```bash
git log --oneline -10  # 找到上个好的 commit
git checkout <commit-hash>  # 回到那个版本
# 重启服务
```

### 小程序回滚
微信公众平台 → 版本管理 → 线上版本 → 回退（只能回到上一个版本）

---

## 上线后验证

```bash
# 检查后端健康
curl https://api.your-domain.com/health

# 检查 Swagger UI（关闭生产环境的 docs？）
# 生产环境可以禁用：FastAPI(docs_url=None, redoc_url=None)
```

小程序端：
```
1. 真机扫码测试版 → 走完完整流程（选题→讨论→发布）
2. 确认积分/连胜正确更新
3. 确认提醒功能正常
```
