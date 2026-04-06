"""Hot topic scoring and angle generation service.

Uses DeepSeek to:
1. Score articles by "discussion space" (1-10)
2. Generate recommended angle and counter-angle for each qualifying topic
3. Categorize topic into predefined categories
"""

import json
from typing import List

from .ai_service import chat_completion
from ..schemas import RawArticle, ScoredTopic, TopicCategory


SCORE_PROMPT = """你是一个社交媒体内容策略师，专注于AI行业内容。

给定以下AI/科技新闻列表，请为每条新闻评估"讨论空间"分数（1-10分）。

评分标准：
- 高分（7-10）：有明确观点空间，普通用户能表达立场，有争议性或洞察性
- 中分（4-6）：有一定讨论价值，但角度不够明显
- 低分（1-3）：纯事实陈述（招聘/财报/学术论文/产品小更新），难以形成观点

新闻列表（JSON格式）：
{articles_json}

请以JSON数组格式返回，每项包含：
- index: 原列表的索引（从0开始）
- score: 讨论空间分数（1-10）
- category: 分类（ai_model/ai_product/startup/policy/tech/industry/other）

只返回JSON数组，不要有其他文字。"""


ANGLE_PROMPT = """你是一个AI行业内容顾问，帮助用户经营"AI洞察者"人设。

热点：{topic}
来源摘要：{summary}

请生成：
1. 推荐角度（ai_angle）：普通AI从业者/关注者能蹭的立场，100字以内
2. 反驳角度（ai_counter_angle）：与推荐角度对立的观点，增加讨论深度，80字以内

以JSON格式返回：
{{"ai_angle": "...", "ai_counter_angle": "..."}}

只返回JSON，不要有其他文字。"""


async def score_articles(articles: List[RawArticle]) -> List[dict]:
    """Batch score articles for discussion potential. Returns list of {index, score, category}."""
    if not articles:
        return []

    articles_data = [
        {"index": i, "title": a.title, "source": a.source, "summary": a.summary[:200]}
        for i, a in enumerate(articles)
    ]
    articles_json = json.dumps(articles_data, ensure_ascii=False)

    prompt = SCORE_PROMPT.format(articles_json=articles_json)
    response = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1000,
    )

    try:
        scores = json.loads(response)
        if not isinstance(scores, list):
            return []
        return scores
    except (json.JSONDecodeError, ValueError):
        return []


async def generate_angles(topic: str, summary: str = "") -> dict:
    """Generate recommended angle and counter-angle for a hot topic."""
    prompt = ANGLE_PROMPT.format(topic=topic, summary=summary[:300])
    response = await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )

    try:
        data = json.loads(response)
        return {
            "ai_angle": data.get("ai_angle", ""),
            "ai_counter_angle": data.get("ai_counter_angle", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return {"ai_angle": "", "ai_counter_angle": ""}


async def score_and_filter(articles: List[RawArticle]) -> List[ScoredTopic]:
    """Score all articles, filter by threshold, then generate angles for qualifying ones.

    Returns list of ScoredTopic ordered by score descending.
    """
    if not articles:
        return []

    scores = await score_articles(articles)
    threshold = 6

    # Build map: index → score data
    score_map = {item["index"]: item for item in scores if "index" in item and "score" in item}

    qualifying = []
    for i, article in enumerate(articles):
        score_data = score_map.get(i)
        if not score_data:
            continue
        score = int(score_data.get("score", 0))
        if score < threshold:
            continue
        qualifying.append((i, article, score, score_data.get("category", "other")))

    # Generate angles for each qualifying article
    results: List[ScoredTopic] = []
    for i, article, score, category in qualifying:
        angles = await generate_angles(article.title, article.summary)

        try:
            cat = TopicCategory(category)
        except ValueError:
            cat = TopicCategory.other

        results.append(
            ScoredTopic(
                hot_topic=article.title,
                hot_source=article.source,
                topic_category=cat,
                ai_angle=angles["ai_angle"],
                ai_counter_angle=angles["ai_counter_angle"],
                score=score,
            )
        )

    results.sort(key=lambda t: t.score, reverse=True)
    return results
