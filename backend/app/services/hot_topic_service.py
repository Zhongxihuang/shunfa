"""Hot topic scoring and angle generation service.

Uses DeepSeek to:
1. Score articles by "discussion space" (1-10)
2. Generate recommended angle and counter-angle for each qualifying topic
3. Categorize topic into predefined categories
"""

import asyncio
import json
from typing import List

from .ai_service import chat_completion
from ..config import settings
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

AI_KEYWORDS = {
    "openai": 9,
    "anthropic": 9,
    "deepseek": 9,
    "gemini": 8,
    "gpt": 8,
    "claude": 8,
    "copilot": 8,
    "microsoft": 8,
    "google": 8,
    "meta": 8,
    "nvidia": 8,
    "ai": 7,
    "llm": 7,
    "model": 7,
    "benchmark": 7,
    "chip": 7,
    "regulation": 7,
    "investigation": 7,
    "startup": 7,
    "funding": 7,
}
MAX_ANGLE_GENERATION_TOPICS = 10


def _heuristic_score(article: RawArticle) -> int:
    haystack = f"{article.title} {article.summary}".lower()
    score = 6
    for keyword, keyword_score in AI_KEYWORDS.items():
        if keyword in haystack:
            score = max(score, keyword_score)
    return min(score, 10)


def _infer_category(article: RawArticle) -> str:
    haystack = f"{article.title} {article.summary}".lower()
    if any(k in haystack for k in ("policy", "regulation", "investigation", "pentagon")):
        return TopicCategory.policy.value
    if any(k in haystack for k in ("startup", "funding", "acquisition")):
        return TopicCategory.startup.value
    if any(k in haystack for k in ("gpt", "claude", "gemini", "deepseek", "model")):
        return TopicCategory.ai_model.value
    if any(k in haystack for k in ("copilot", "product", "app")):
        return TopicCategory.ai_product.value
    if any(k in haystack for k in ("chip", "benchmark", "infra")):
        return TopicCategory.tech.value
    return TopicCategory.industry.value


def _fallback_scores(articles: List[RawArticle]) -> List[dict]:
    return [
        {
            "index": i,
            "score": _heuristic_score(article),
            "category": _infer_category(article),
        }
        for i, article in enumerate(articles)
    ]


def _default_angles(topic: str) -> dict:
    return {
        "ai_angle": f"我更关注「{topic}」背后的行业信号，这通常不只是单点新闻，而是竞争格局在变。",
        "ai_counter_angle": f"另一种看法是，「{topic}」可能只是短期噪音，真正决定结果的还是落地和分发能力。",
    }


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
            return _fallback_scores(articles)
        return scores
    except (json.JSONDecodeError, ValueError):
        return _fallback_scores(articles)


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
        if not isinstance(data, dict):
            return _default_angles(topic)
        return {
            "ai_angle": data.get("ai_angle", ""),
            "ai_counter_angle": data.get("ai_counter_angle", ""),
        }
    except (json.JSONDecodeError, ValueError):
        return _default_angles(topic)


async def score_and_filter(articles: List[RawArticle]) -> List[ScoredTopic]:
    """Score all articles, filter by threshold, then generate angles for qualifying ones.

    Returns list of ScoredTopic ordered by score descending.
    """
    if not articles:
        return []

    scores = await score_articles(articles)
    threshold = settings.topic_score_threshold

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

    if not qualifying:
        fallback_scores = _fallback_scores(articles)
        for i, article in enumerate(articles[: min(5, len(articles))]):
            score_data = fallback_scores[i]
            qualifying.append((i, article, score_data["score"], score_data["category"]))

    qualifying.sort(key=lambda item: item[2], reverse=True)
    qualifying = qualifying[:MAX_ANGLE_GENERATION_TOPICS]

    # Generate angles for each qualifying article
    results: List[ScoredTopic] = []
    angles_list = await asyncio.gather(
        *(generate_angles(article.title, article.summary) for _, article, _, _ in qualifying)
    )

    for (i, article, score, category), angles in zip(qualifying, angles_list):

        try:
            cat = TopicCategory(category)
        except ValueError:
            cat = TopicCategory.other

        results.append(
            ScoredTopic(
                hot_topic=article.title,
                hot_source=article.source,
                hot_url=article.link,
                hot_summary=article.summary,
                topic_category=cat,
                ai_angle=angles["ai_angle"],
                ai_counter_angle=angles["ai_counter_angle"],
                score=score,
            )
        )

    results.sort(key=lambda t: t.score, reverse=True)
    return results
