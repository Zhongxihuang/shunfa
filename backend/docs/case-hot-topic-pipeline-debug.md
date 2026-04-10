# 案例：分布式内容流水线的静默失败与数据质量治理

## 背景

顺发（AI洞察者）有一个热点内容推送流水线：

```
RSS 源抓取 → DeepSeek AI 评分筛选 → 写入飞书 Bitable（热点库）
                                              ↓
                              Coze 工作流触发 → 飞书机器人回复"今日热点"
```

用户反馈：向飞书机器人发送"今日热点"，回复"热点工具调用暂时失败"，且给出的选题与当下热点不符。

---

## 问题拆解

### 表面现象

1. 飞书机器人回复"热点工具调用暂时失败"
2. 给出的选题内容陈旧（3-7天前的 AI 新闻）

### 深层根因（3个独立问题同时存在）

#### 问题 1：Bitable 存在脏数据 — 查询结果为空

**现象**：`/api/coze/get_hot_topics` 查询过滤条件为：

```
status = "pending" AND date = 今天日期
```

Bitable 里实际数据状态：

| 日期 | 状态 | 数量 |
|------|------|------|
| 04-03 | expired | 24 |
| 04-04 | expired | 1 |
| 04-06 | expired | 25 |
| 04-07 | expired | 38 |
| 04-08 | expired | 2 |
| 04-10 | pending | 0（**今天没有任何数据**）|

**为什么没有今天的 pending 数据？**

- RSS cron 从未自动化执行（系统 crontab 为空，仅手动触发）
- 历史上多次 cron 运行后，pending 记录积累了大量历史数据，但从未被清理
- `get_pending_topics` 严格按日期过滤，历史 pending 记录永远无法被匹配到
- 结果：Coze 查询返回空列表 → 工作流捕获异常 → 显示"工具调用失败"

**经验教训**：时间序列数据如果只按"当天"过滤，必须确保定时清理历史状态。状态机的生命周期管理缺失是最常见的静默失败根因。

---

#### 问题 2：异常被静默吞没

**代码**（`coze_plugin.py`）：

```python
try:
    topics = await get_pending_topics(limit=limit)
except Exception:
    # Bitable 不可用时返回空列表
    topics = []
```

这是一个防御性编程的典型反模式：

- **表面**：接口永远返回 200，用户看到的是 Coze 工作流层的"工具调用失败"提示
- **掩盖**：真实的 Bitable 连接错误、权限错误、字段名不匹配等严重问题全部被隐藏
- **代价**：问题被延迟发现，数据在 Bitable 里积累到 100+ 条时才暴露

**正确做法**：

```python
try:
    topics = await get_pending_topics(limit=limit)
except BitableError as e:
    logger.error(f"Bitable query failed: {e}")
    raise HTTPException(503, "热点服务暂时不可用，请稍后重试")
```

**经验教训**：防御性编程要保留可观测性。吞掉异常时，至少要写日志和返回可区分的错误码，否则故障会从一层隐藏到另一层，最终在用户界面以混淆的形式出现。

---

#### 问题 3：热点内容陈旧 — RSS cron 缺乏自动触发

**现状**：cron 脚本 `app/cron/rss_cron.py` 需要手动执行：

```bash
cd backend && python -m app.cron.rss_cron
```

系统 crontab 为空，没有定时任务。

**影响**：
- 热点数据依赖人工触发，频率不可控
- 历史上 cron 曾多次运行，但每次都只写入新数据，从未清理旧数据
- 旧 pending 记录积累 → 数据膨胀 → 问题 1 的根源

**经验教训**：数据管道必须配套监控（数据新鲜度告警）和自动化执行。即使 MVP 阶段，也要记录"上次运行时间"并在接口里暴露。

---

## 修复方案

### 修复 1：清理脏数据，建立数据生命周期

一次性清理脚本：
1. 扫描 Bitable 所有记录
2. 将历史 pending 记录标记为 `expired`
3. 删除空记录（早期测试产物）

```
结果：清理 90 条过期记录，删除 10 条空记录
```

### 修复 2：补齐 BitableClient 的 CRUD 能力

原有 `BitableClient` 只有记录 CRUD，缺少：
- `list_fields()` — 查询表字段（验证列名是否匹配）
- `add_field()` — 程序化建列（替代手动操作飞书后台）
- `batch_delete_records()` — 清理无效记录

```python
# 新增方法
async def add_field(self, table_id, field_name, field_type=1) -> str: ...
async def list_fields(self, table_id) -> list[dict]: ...
async def batch_delete_records(self, table_id, record_ids) -> None: ...
```

### 修复 3：完善 RSS cron 的数据刷新逻辑

原 cron 只管写入，不管清理。补充：
- 运行前将当天旧 pending 标记为 expired
- 防止重复写入同一日期的数据

### 修复 4：新增字段透传

本次修复同时发现：`hot_url`（原文链接）和 `hot_summary`（摘要）字段在 `ScoredTopic` 构造时被丢弃，导致推送热点没有链接，用户无法验证可信度。

修复：
```
RawArticle.link        → ScoredTopic.hot_url       ✓
RawArticle.summary     → ScoredTopic.hot_summary   ✓
                         → Bitable hot_url 列       ✓（新增列）
                         → Coze API 响应           ✓
```

---

## 技术债务总结

| 债务项 | 风险等级 | 根因 |
|--------|----------|------|
| pending 记录无过期机制 | 高 | 状态机缺少"到期清理"步骤 |
| 异常被静默吞没 | 高 | 防御性编程但无可观测性 |
| cron 缺乏自动化 | 高 | MVP 阶段跳过运维设计 |
| BitableClient 能力残缺 | 中 | 仅实现最小 CRUD，运维操作靠手动 |
| `hot_url` 字段丢失 | 中 | 服务层构造时未透传已有字段 |

---

## 面试价值

### 展现的工程能力

1. **分布式系统可观测性**：知道"接口返回空"不等于"数据不存在"，需要追踪数据在各层的状态
2. **状态机设计**：pending → pushed / expired 的生命周期必须配套清理逻辑
3. **防御性编程的正确姿势**：保留可诊断性，不是简单 try/except pass
4. **数据质量治理**：定期扫描数据资产，识别"沉睡数据"和"孤儿记录"
5. **API 设计的可组合性**：BitableClient 作为基础设施类，需要覆盖运维场景（建列、删记录、查字段）

### 反模式警示

- ❌ "接口不报错就是没问题" → 异常被吞没，数据问题在其他层暴露
- ❌ "手动清理一次就够了" → 数据会随时间积累，必须自动化
- ❌ "先跑通再优化" → 跳过数据生命周期管理的 MVP 会变成技术债

### 架构决策复盘

- **为什么用 Bitable 作为热点存储**：快速迭代、飞书生态集成、无需自建 DB
- **为什么用 Coze 做对话编排**：workflow 即配置，运营可调整 prompt
- **为什么 RSS cron 没有自动化**：早期聚焦内容质量验证，手动触发可控性更高
- **是否应该一开始就用独立数据库**：Bitable 的查询能力有限（filter 公式不灵活），对于需要排序、聚合的数据需求，关系型 DB 更合适

---

*文档生成时间：2026-04-10*
*相关文件：`app/clients/bitable_client.py`、`app/services/hot_topic_store.py`、`app/routers/coze_plugin.py`、`app/cron/rss_cron.py`*
