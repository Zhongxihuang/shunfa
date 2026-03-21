---
name: fix-bug
description: 顺发 bug 修复流程。遇到报错、测试失败、线上问题时使用。强制先复现再修复。
---

# Bug 修复流程

## 原则：永远先复现，再修复

不允许「看代码猜问题然后改」。必须先有一个失败的测试或可复现的步骤，才开始改代码。

---

## Step 1：定位问题

### A. 如果是测试失败

```bash
cd /Users/huangzhongxi/shunfa/backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest --lf -v --tb=long
```

读完整的 traceback，记录：
- 哪个文件哪一行
- 期望值 vs 实际值
- 是断言失败还是异常？

### B. 如果是 API 报错

先看 uvicorn 控制台的完整错误栈，再对应到：
- `400` → schema validation 或 ValueError 转 HTTPException
- `401/403` → JWT 或 auth
- `404` → 查询返回 None，未加 or_404
- `422` → Pydantic 类型错误
- `500` → 未捕获的异常，看 traceback

### C. 如果是小程序问题

```
微信开发者工具 → 控制台 → Network 面板
看请求 URL、请求体、响应体
```

---

## Step 2：写一个失败的测试（如果还没有）

```python
def test_bug_reproduction():
    """复现 issue: [描述问题]"""
    # 构造触发 bug 的最小场景
    # assert 预期的正确行为
    pass  # 现在会失败
```

运行确认它确实失败：
```bash
pytest tests/test_xxx.py::test_bug_reproduction -v
```

---

## Step 3：修复

根据问题类型找对位置：

| 问题类型 | 先看这里 |
|---------|---------|
| 状态转换错误 | `services/content_service.py` |
| 积分/连胜计算错 | `services/streak_service.py` / `services/points_service.py` |
| 时区问题 | `utils/time_utils.py`，确认用 CST 而非 UTC |
| 选题去重/刷新限制 | `services/topic_service.py` |
| Auth 问题 | `dependencies.py` / `routers/user.py` |
| 小程序 API 调用 | `miniprogram/utils/api.js` |

**最小化修改**：只改导致 bug 的那几行，不要顺手重构。

---

## Step 4：验证

```bash
# 确认复现测试通过
pytest tests/test_xxx.py::test_bug_reproduction -v

# 确认全套测试不回归
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v
```

---

## Step 5：提交

```bash
git add -p  # 只 stage 修复相关的改动
git commit -m "fix: [一句话描述问题和修复]

问题: [为什么会发生这个 bug]
修复: [做了什么修改]
测试: 新增 test_bug_reproduction"
```

---

## 常见 Bug 速查

### 「积分没有算连续加成」
检查 `confirm_publish` 里 streak 更新和积分计算的顺序：
必须先 `calculate_and_update_streak`，再 `apply_points_and_update_user`。

### 「选题刷新次数不对」
注意：**第一次获取选题不消耗刷新次数**（`is_first_load` 判断）。
3次刷新 = 第1次(免费) + 3次(收费)，共可调用 4 次 API。

### 「draft 在预览页面消失」
draft 通过 `wx.setStorageSync('current_draft', ...)` 传递，不是 URL 参数。
检查 `discuss.js` 是否写入了 Storage，`preview.js` 是否从 Storage 读取。

### 「用户打卡后连胜没更新」
`confirm_publish` → `content_service.py` → 调用了 `streak_service`？
检查 `is_consecutive_day()` 的参数顺序：`is_consecutive_day(last_date, today)`，第一个是旧日期。
