"""Hot topic scoring and angle generation service.

Uses DeepSeek to:
1. Score articles by "discussion space" (1-10)
2. Generate recommended angle and counter-angle for each qualifying topic
3. Categorize topic into predefined categories
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

from ..config import settings
from ..schemas import RawArticle, ScoredTopic, TopicCategory
from .ai_service import chat_completion, get_system_api_key

# Articles older than this are filtered out — keeps only recent hot topics
MAX_ARTICLE_AGE_DAYS = 3

MAX_SUMMARY_CHARS = 150  # Display-friendly summary length

# Boost Chinese sources slightly to prioritize them, but not at the expense of quality
# English articles compete on quality; Chinese articles get a modest edge
SOURCE_BOOST: dict[str, int] = {
    "雷锋网": 5,         # Chinese AI/Tech
    "36Kr": 5,           # Chinese tech news
    "Hacker News": -5,   # English content; push to bottom
    "VentureBeat AI": 0,
    "TechCrunch AI": 0,
    "MIT Tech Review": 0,
    "The Verge": 0,
    "Ars Technica": 0,
}


def _is_recent(article: RawArticle) -> bool:
    """Return True if article was published within MAX_ARTICLE_AGE_DAYS (UTC)."""
    if not article.published_date:
        return False
    try:
        raw = article.published_date.strip()
        # Handle Z-suffix UTC
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        # Handle timezone offsets like +0800
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
    except ValueError:
        return False
    cutoff = datetime.now(UTC) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
    return dt >= cutoff


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


def _fallback_scores(articles: list[RawArticle]) -> list[dict]:
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


async def score_articles(articles: list[RawArticle]) -> list[dict]:
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
        api_key=get_system_api_key(),
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
        api_key=get_system_api_key(),
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


MAX_TITLE_CHARS = 40  # Short, news-style title limit


TRANSLATE_TITLES_PROMPT = """将以下每条英文标题翻译为中文，保留新闻标题风格，{MaxChars}字以内。

规则：
- 英文 → 中文
- 标题风格：简洁、有信息量
- 每条输出为一行：[序号] 翻译后标题
- 不要解释，不要空行，直接输出

原文：
{articles}
"""

TRANSLATE_PROMPT = """将以下每条英文摘要翻译为中文，并压缩到约{MaxChars}字（1-2句）。

规则：
- 英文 → 中文
- 中文摘要 → 压缩保留核心事实
- 每条输出为一行：[序号] 翻译后摘要
- 不要解释，不要空行，直接输出

原文：
{articles}
"""


def _parse_translation_response(response: str, max_chars: int) -> dict[int, str]:
    """Parse line-by-line '[idx] content' format into index→text dict."""
    result: dict[int, str] = {}
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("["):
            continue
        bracket_end = line.index("]")
        idx_str = line[1:bracket_end]
        text = line[bracket_end + 1 :].strip()
        try:
            result[int(idx_str)] = text[:max_chars]
        except ValueError:
            pass
    return result


async def translate_titles(articles: list[RawArticle]) -> dict[int, str]:
    """Batch-translate English titles to Chinese via DeepSeek.

    Returns dict mapping original index → translated title.
    """
    articles_text = "\n".join(
        f"[{i}] {a.title[:100]}" for i, a in enumerate(articles)
    )
    prompt = TRANSLATE_TITLES_PROMPT.format(
        MaxChars=MAX_TITLE_CHARS,
        articles=articles_text,
    )
    try:
        response = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=4000,
            api_key=get_system_api_key(),
        )
        return _parse_translation_response(response, MAX_TITLE_CHARS)
    except Exception:
        return {}


async def translate_summaries(articles: list[RawArticle]) -> dict[int, str]:
    """Batch-translate and truncate English summaries to Chinese via DeepSeek.

    Returns dict mapping original index → translated summary.
    """
    articles_text = "\n".join(
        f"[{i}] {a.summary[:300]}" for i, a in enumerate(articles)
    )
    prompt = TRANSLATE_PROMPT.format(
        MaxChars=MAX_SUMMARY_CHARS,
        articles=articles_text,
    )
    try:
        response = await chat_completion(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=8000,
            api_key=get_system_api_key(),
        )
        return _parse_translation_response(response, MAX_SUMMARY_CHARS)
    except Exception:
        return {}


async def score_and_filter(articles: list[RawArticle]) -> list[ScoredTopic]:
    """Score all articles, filter by threshold, then generate angles for qualifying ones.

    Returns list of ScoredTopic ordered by score descending.
    """
    if not articles:
        return []

    # Filter out articles older than MAX_ARTICLE_AGE_DAYS days (UTC)
    articles = [a for a in articles if _is_recent(a)]
    if not articles:
        return []

    # Step 1: Translate ALL English titles and summaries to Chinese BEFORE scoring
    # This ensures the scoring prompt (in Chinese) evaluates Chinese text,
    # and all stored titles/summaries are Chinese for consistent UX
    translated_titles = await translate_titles(articles)
    for i, article in enumerate(articles):
        if i in translated_titles:
            article.title = translated_titles[i]

    translated_summaries = await translate_summaries(articles)
    for i, article in enumerate(articles):
        if i in translated_summaries:
            article.summary = translated_summaries[i]
        elif len(article.summary) > MAX_SUMMARY_CHARS:
            article.summary = article.summary[:MAX_SUMMARY_CHARS]

    # Step 2: Score articles (now with Chinese summaries)
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

    # Step 3: Generate angles for each qualifying article (summary already Chinese)
    results: list[ScoredTopic] = []
    angles_list = await asyncio.gather(
        *(generate_angles(article.title, article.summary) for _, article, _, _ in qualifying)
    )

    for (i, article, score, category), angles in zip(qualifying, angles_list, strict=False):

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
                published_at=article.published_date,
                topic_category=cat,
                ai_angle=angles["ai_angle"],
                ai_counter_angle=angles["ai_counter_angle"],
                score=score,
            )
        )

    results.sort(key=lambda t: (t.score + SOURCE_BOOST.get(t.hot_source, 0), t.hot_topic), reverse=True)
    return results
