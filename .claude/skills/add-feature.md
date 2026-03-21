---
name: add-feature
description: 为顺发添加新功能的完整流程。包含后端 + 小程序的端到端开发步骤、测试要求、提交规范。
---

# 顺发新功能开发流程

## 步骤 1：理解需求

确认以下内容再动手：
- [ ] 是否需要新数据库字段？（如果是，需要删 db 重建）
- [ ] 是否需要新 API 端点，还是复用现有端点？
- [ ] 影响哪些现有测试？
- [ ] 小程序哪个页面需要改动？

## 步骤 2：后端实现（TDD）

### 2a. 先写测试（RED）

在 `backend/tests/test_xxx.py` 写失败的测试：

```python
def test_new_feature(user, client, db):
    token = create_jwt_token(user.id)
    response = client.post("/api/new_endpoint",
        json={"param": "value"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["key"] == "expected_value"
```

运行确认失败：
```bash
cd backend && DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest tests/test_xxx.py -v
```

### 2b. 实现（GREEN）

按顺序：
1. `app/models.py` — 加模型字段（如需）
2. `app/schemas.py` — 加 Request/Response schema
3. `app/services/xxx_service.py` — 核心业务逻辑
4. `app/routers/xxx.py` — HTTP 层（薄，只做参数校验）

### 2c. 验证全套测试通过

```bash
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v
```

**全部 36+ 测试必须通过**，不允许现有测试回归。

## 步骤 3：小程序实现

### 3a. 调用新端点

```javascript
// utils/api.js 已封装，直接用
api.post('/api/new_endpoint', { param: value })
  .then(data => this.setData({ result: data }))
  .catch(err => wx.showToast({ title: err.data?.detail || '请求失败', icon: 'none' }));
```

### 3b. UI 规范

- 操作按钮加防重复提交（`loading` 标志 + `disabled`）
- 加载状态用 `.loading-spinner` 全局 CSS class
- 错误用 `wx.showToast({ icon: 'none' })`
- 成功用 `wx.showToast({ icon: 'success' })`

## 步骤 4：提交

```bash
git add backend/app/... backend/tests/... miniprogram/pages/...
git commit -m "feat: 功能描述

- 后端：xxx
- 小程序：xxx
- 测试：N tests，all passing"
```

## 检查清单

- [ ] 后端：新端点需要认证（`Depends(get_current_user)`）
- [ ] 后端：业务逻辑在 service 层，不在 router 层
- [ ] 后端：ValueError → HTTPException 在 router 层转换
- [ ] 后端：所有新业务逻辑有测试覆盖
- [ ] 小程序：防止重复提交
- [ ] 小程序：网络错误有用户反馈
- [ ] 全套测试通过
