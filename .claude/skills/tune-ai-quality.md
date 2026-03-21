---
name: tune-ai-quality
description: 评估和提升顺发 AI 对话质量。当选题太无聊、讨论引导效果差、初稿风格不对时使用。包含评估框架和调优循环。
---

# AI 质量调优流程

## 三个质量维度

### 1. 选题质量（`services/topic_service.py`）

**好选题的标准**：
- ✅ 具体：「上周一次让我改变想法的对话」而非「沟通的重要性」
- ✅ 普通人有话说：不需要专业知识
- ✅ 适合公开分享：不太私密，不太无聊
- ✅ 15-30 字，能直接作为文章开头
- ❌ 不要：「我对工作的看法」「关于成长」（太泛）
- ❌ 不要：三个选题方向雷同

**评估方法**：
```bash
# 临时脚本快速评估（需要真实 API key）
cd /Users/huangzhongxi/shunfa/backend
python3 -c "
import asyncio
from app.services.topic_service import _generate_topics_via_ai

async def test():
    topics = await _generate_topics_via_ai([])
    for i, t in enumerate(topics, 1):
        print(f'{i}. {t} ({len(t)}字)')
    print('---')
    print('多样性：', len(set(t[:4] for t in topics)) == 3 and '通过' or '相似')

asyncio.run(test())
" 2>/dev/null
```

---

### 2. 讨论引导质量（`services/content_service.py`）

**好的引导问题标准**：
- ✅ 聚焦用户的具体经历，而非观点（「你当时是怎么做的」>「你怎么看这件事」）
- ✅ 一次只问一个问题
- ✅ 让用户觉得「有东西可说」
- ❌ 不要开放式到没有边界（「你觉得呢」）
- ❌ 不要诱导用户说预设答案

**判断是否可以生成草稿**：
- 用户说了具体的事件/人物/时间/感受中的至少2个
- 有 140-300 字的素材空间
- 不需要再问更多问题

---

### 3. 初稿质量（生成后检查）

**好初稿的标准**：
- ✅ 第一人称，口语化，像朋友发朋友圈
- ✅ 140-300 字（不超不少）
- ✅ 有具体细节（人名用「朋友/同事」代替，事件清晰）
- ✅ 有一个清晰的「观点/感悟」
- ❌ 不要：「这让我深刻认识到…」「总的来说…」（套话结尾）
- ❌ 不要：AI 腔（「作为一个现代人…」「在这个快节奏的时代…」）

---

## 调优循环

### 发现问题

```
用户反馈 / 自测发现
    ↓
归类：是选题问题？引导问题？还是初稿问题？
    ↓
找到对应的提示词位置
```

### 修改提示词

```python
# 选题提示词 → topic_service.py _generate_topics_via_ai()
# 讨论提示词 → content_service.py SYSTEM_PROMPT_DISCUSS
# 强制生成提示词 → content_service.py _force_generate_draft()
```

**调优原则**：
1. 每次只改一件事（温度 OR 提示词文字）
2. 改之前记录原始版本
3. 对比至少 5 组输出再判断好坏

### 常用调优手段

| 问题 | 调法 |
|------|------|
| 选题太泛 | 提示词加「请提供具体的事件或场景，而非抽象概念」|
| 选题相似 | 提示词加「三个选题必须属于不同的生活/工作/思考维度」|
| 讨论问题太多 | 系统提示加「每次只提一个问题，不要超过一个」|
| 不触发生成草稿 | 降低 MAX_DISCUSSION_ROUNDS（从3到2）|
| 草稿太像 AI 写的 | 提示词加 few-shot 示例（人写的例子）|
| 草稿字数不对 | 加「字数控制在140-300字，超出请删减」|

### 验证修改没破坏逻辑

```bash
cd /Users/huangzhongxi/shunfa/backend
DEEPSEEK_API_KEY=test WECHAT_APP_ID=test WECHAT_APP_SECRET=test JWT_SECRET_KEY=supersecretkey123456789 pytest tests/test_topics.py tests/test_content.py -v
```

测试全 mock，只验证逻辑（状态流、标记解析、轮次控制），不验证 AI 输出质量。
真实质量需要用有效 key 人工测试。

### 提交调优

```bash
git commit -m "tune: 优化[选题/讨论/初稿]提示词

问题: [描述原来的问题]
修改: [修改了什么]
效果: [主观评估：对比 N 组输出，好/差/持平]"
```

---

## Few-shot 示例库（可加入提示词）

### 好选题示例

```
- 昨天同事无意说了一句话，让我重新思考了自己的工作方式
- 我终于弄明白为什么自己总是在最后一刻才开始工作
- 一件小事让我意识到我低估了坚持的力量
```

### 好初稿示例

```
上周和一个老朋友聊天，他问我最近在忙什么。
我说了一堆，却发现我说不清楚「自己在做什么」。

这让我有点慌。
不是因为没在干活，而是因为我在用忙碌掩盖方向感的缺失。

后来我花了半小时，把最近做的事写下来，按「值得继续」和「可以停了」分两列。
列完就清楚多了。

有时候不是你不知道答案，只是你需要一张纸。
```
