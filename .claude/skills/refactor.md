---
name: refactor
description: 顺发代码安全重构流程。清理技术债、改善代码结构时使用。强制测试保护，禁止行为变更。
---

# 安全重构流程

## 重构的黄金原则

**重构 = 不改变外部行为，只改内部结构。**
如果同时改了行为，那是「修改功能」，不是重构。

---

## Step 1：确认测试覆盖

重构前，全套测试必须通过，这是你的安全网：

```bash
cd /Users/huangzhongxi/shunfa/backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v
```

如果有测试失败，**先修测试，再重构**。

---

## Step 2：确定重构范围

明确边界，**一次只重构一件事**：

```
□ 提取重复逻辑到函数（DRY）
□ 重命名（变量/函数/文件）
□ 拆分过长函数（> 50行）
□ 简化条件分支
□ 移动函数到更合适的模块
□ 删除死代码
```

不允许在同一个 PR 里混合多种重构类型。

---

## Step 3：小步修改

每次只做一个微小的改动，然后立即验证：

```bash
# 改完一小步就跑一次
pytest -v --tb=short -q
```

不要一次改10个地方再统一测试。

---

## Step 4：已知技术债优先级

参考 CLAUDE.md 中的 TODO 列表，当前优先级：

### 🔴 高价值（功能影响大）
- **`ConfirmContentRequest.content` 无长度限制**
  - 位置：`schemas.py`
  - 改法：`content: str = Field(..., min_length=1, max_length=2000)`
  - 测试：加一个超长 content 返回 422 的测试

- **`confirm_publish` 两次 commit 的原子性问题**
  - 位置：`content_service.py` + `points_service.py`
  - 改法：把 `apply_points_and_update_user` 的内部 commit 去掉，让调用方统一 commit
  - 风险：改动涉及两个 service，需要同步修改

### 🟡 中价值（代码质量）
- **`topic_service.py` 中空 topic 的 CheckIn 创建**
  - 位置：`topic_service.py` 约60行
  - 问题：首次获取选题时创建了 topic="" 的 CheckIn
  - 改法：把 CheckIn 创建移到 `select_topic` 时
  - 风险：需要同步修改 `refresh_count` 的追踪逻辑

### ⚪ 低价值（暂不动）
- `sync Session in async FastAPI`：SQLite 低并发下没问题，上 PostgreSQL 再改
- JWT 无撤销：MVP 接受

---

## Step 5：重构后验证

```bash
# 全套测试必须全部通过，没有任何回归
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest -v

# 检查没有意外的行为变更
git diff HEAD -- backend/app/  # 只有结构改动，没有逻辑改动
```

---

## Step 6：提交

重构用独立 commit，不和功能改动混在一起：

```bash
git commit -m "refactor: [描述做了什么结构改变]

不改变任何外部行为。全套 36 个测试通过。"
```

---

## 禁止事项

- ❌ 重构时顺手「改进」一个逻辑（改了行为）
- ❌ 重构时加新功能
- ❌ 重构前没有跑测试就开始改
- ❌ 一次改多个文件的多个地方然后统一测试
