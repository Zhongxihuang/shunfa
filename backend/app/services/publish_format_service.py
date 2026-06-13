"""Multi-platform text formatters + exporters (W1.4 真发布 MVP).

The W1.4 promise is: from "draft ready" to "content on the target platform"
in ≤ 2 steps. This module is what makes step 2 work — given a checkin
and a target platform, produce text the user can paste with one click.

Design rules:
- No LLM call. The formatters are deterministic. Reason: step 2 is meant
  to be < 200ms; calling DeepSeek here would make it a 3+ step UX again
  and re-introduce the very friction we are trying to remove.
- Each formatter is a pure function of (topic, content, tags). No DB
  reads, no side effects, easy to unit-test.
- Hashtag derivation is platform-specific: XHS uses 5-8 tags, Moments
  uses 0-1, WeChat Official uses none. The checkin may carry tags from
  the compose step; we fall back to deriving from the topic.
- Length limits are hard-enforced (Twitter 280, Weibo 140). When the
  formatted output exceeds the cap, we truncate with a marker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Hashtag derivation: split on whitespace + Chinese/English punctuation.
# We keep the raw tokens and let each platform decide how to format them.
_TOKEN_SPLIT = re.compile(r"[\s,，。.!?;:、；：！？」』\"\'「『《》<>(){}\[\]]+")


@dataclass(frozen=True)
class FormattedPost:
    """Result of formatting one checkin for one platform.

    Attributes:
        platform: the platform id (matches `Platform` enum on the checkin
            plus two new ids — `moments` and `wechat_official`).
        title: short title-like line shown above the body when relevant.
        body: the main text.
        tags: list of tags to render (XHS uses #tag, Moments appends inline).
        char_count: total visible chars across title+body+tags (for the UI
            to display "小红书 350 / 1000 字").
        truncated: True if the body was cut to fit a hard limit.
        truncated_marker: short marker appended after a truncation, e.g.
            "…[已截断]". Empty when not truncated.
    """

    platform: str
    title: str
    body: str
    tags: list[str]
    char_count: int
    truncated: bool = False
    truncated_marker: str = ""


# ── Hashtag derivation ───────────────────────────────────────────────────────


def _hashtagify(token: str) -> str:
    """Normalize a free-text tag into something safe for `#tag`.

    Drops whitespace, English-mode punctuation, and any character that
    breaks a hashtag rendering on the major Chinese social apps.
    """
    cleaned = re.sub(r"[\s#@!?.,，。、；：！？」』\"\'「『《》]", "", token)
    return cleaned.strip()


def derive_tags(topic: str, provided: list[str] | None = None, limit: int = 6) -> list[str]:
    """Pick up to `limit` tags.

    Priority:
      1. `provided` (from compose_assets.tags on the checkin), normalized
      2. From the topic itself (split on punctuation/whitespace)

    Dedup is case-insensitive, and we always strip the leading "#".
    """
    seen: set[str] = set()
    out: list[str] = []

    def _add(raw: str) -> None:
        norm = _hashtagify(raw.lstrip("#"))
        if not norm:
            return
        key = norm.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(norm)

    if provided:
        for t in provided:
            _add(t)
    if len(out) < limit:
        for token in _TOKEN_SPLIT.split(topic or ""):
            if not token:
                continue
            _add(token)

    return out[:limit]


# ── Per-platform formatters ──────────────────────────────────────────────────


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Cut `text` to `limit` chars on a clean boundary. Returns (text, truncated)."""
    if len(text) <= limit:
        return text, False
    return text[: limit - 1] + "…", True


def _xhs(topic: str, content: str, provided_tags: list[str] | None) -> FormattedPost:
    """小红书: 标题行 + 多段正文 + 末尾 hashtag 块. Length cap 1000."""
    tags = derive_tags(topic, provided_tags, limit=6)
    title = topic.strip()[:30] if topic else "今日随笔"
    # XHS prefers short paragraphs separated by blank lines.
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", content.strip()) if p.strip()]
    body = "\n\n".join(paragraphs)
    tag_line = " ".join(f"#{t}" for t in tags)
    full = f"{title}\n\n{body}\n\n{tag_line}" if tag_line else f"{title}\n\n{body}"
    full, was_cut = _truncate(full, 1000)
    return FormattedPost(
        platform="xiaohongshu",
        title=title,
        body=body,
        tags=tags,
        char_count=len(full),
        truncated=was_cut,
        truncated_marker="…[已截断]" if was_cut else "",
    )


def _moments(topic: str, content: str, provided_tags: list[str] | None) -> FormattedPost:
    """朋友圈: 1-2 行 + 0-1 末尾 hashtag. Length cap 150 (Momens real limit is higher, but
    short > verbose for Moments engagement)."""
    tags = derive_tags(topic, provided_tags, limit=1)
    title = topic.strip().split("\n")[0][:30] if topic else ""
    body = content.strip()
    full = f"{title}\n{body}" if title else body
    if tags:
        full = f"{full}\n\n# {tags[0]}"
    full, was_cut = _truncate(full, 150)
    return FormattedPost(
        platform="moments",
        title=title,
        body=body,
        tags=tags,
        char_count=len(full),
        truncated=was_cut,
        truncated_marker="…" if was_cut else "",
    )


def _wechat_official(topic: str, content: str, provided_tags: list[str] | None) -> FormattedPost:
    """公众号: 一级标题 + 段落之间空行. No hashtag (公众号无 hashtag 文化)."""
    title = topic.strip() or "今日随笔"
    # 公众号 paragraphs are separated by blank lines, no inline hashtags.
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", content.strip()) if p.strip()]
    body = "\n\n".join(paragraphs)
    full = f"# {title}\n\n{body}"
    full, was_cut = _truncate(full, 20000)  # 公众号 no real cap
    return FormattedPost(
        platform="wechat_official",
        title=title,
        body=body,
        tags=[],
        char_count=len(full),
        truncated=was_cut,
        truncated_marker="…[已截断]" if was_cut else "",
    )


def _twitter(topic: str, content: str, provided_tags: list[str] | None) -> FormattedPost:
    """Twitter: 280 chars, English-mode tags."""
    tags = derive_tags(topic, provided_tags, limit=2)
    tag_line = " ".join(f"#{t}" for t in tags)
    title = topic.strip() if topic else ""
    parts = [p for p in (title, content.strip()) if p]
    body = "\n\n".join(parts)
    if tag_line:
        body = f"{body}\n{tag_line}"
    body, was_cut = _truncate(body, 280)
    return FormattedPost(
        platform="twitter",
        title=title,
        body=body,
        tags=tags,
        char_count=len(body),
        truncated=was_cut,
        truncated_marker="…" if was_cut else "",
    )


def _weibo(topic: str, content: str, provided_tags: list[str] | None) -> FormattedPost:
    """微博: 140 chars, ##双井号#话题."""
    tags = derive_tags(topic, provided_tags, limit=2)
    title = topic.strip() if topic else ""
    parts = [p for p in (title, content.strip()) if p]
    body = "\n\n".join(parts)
    if tags:
        # 微博 style: #话题# inline
        body = f"{body} " + " ".join(f"#{t}#" for t in tags)
    body, was_cut = _truncate(body, 140)
    return FormattedPost(
        platform="weibo",
        title=title,
        body=body,
        tags=tags,
        char_count=len(body),
        truncated=was_cut,
        truncated_marker="…" if was_cut else "",
    )


def _generic(topic: str, content: str, provided_tags: list[str] | None) -> FormattedPost:
    """Generic fallback: 标题 + 段落 + 末尾 #tag 行."""
    tags = derive_tags(topic, provided_tags, limit=3)
    title = topic.strip()
    body = content.strip()
    if title:
        body = f"{title}\n\n{body}"
    if tags:
        body = f"{body}\n\n" + " ".join(f"#{t}" for t in tags)
    return FormattedPost(
        platform="generic",
        title=title,
        body=body,
        tags=tags,
        char_count=len(body),
    )


_FORMATTERS = {
    "xiaohongshu": _xhs,
    "moments": _moments,
    "wechat_official": _wechat_official,
    "twitter": _twitter,
    "weibo": _weibo,
    "generic": _generic,
}

# All platforms the API accepts (subset of Platform + new ones).
SUPPORTED_PLATFORMS: tuple[str, ...] = (
    "xiaohongshu",
    "moments",
    "wechat_official",
    "twitter",
    "weibo",
    "generic",
)


def format_post(
    topic: str,
    content: str,
    platform: str,
    provided_tags: list[str] | None = None,
) -> FormattedPost:
    """Format a checkin's topic+content for one platform.

    Unknown platform falls back to `generic` — we never 500 on a
    frontend typo. The `platform` field on the response echoes what was
    actually used, so the UI can warn ("未知平台，使用通用格式").
    """
    fmt = _FORMATTERS.get(platform, _generic)
    return fmt(topic or "", content or "", provided_tags)


# ── Markdown / plain-text exporters ──────────────────────────────────────────


def export_markdown(topic: str, content: str, tags: list[str] | None = None) -> str:
    """Produce a Markdown file body for download."""
    parts: list[str] = []
    title = (topic or "未命名").strip()
    parts.append(f"# {title}\n")
    parts.append(content.strip())
    parts.append("")
    if tags:
        parts.append("---")
        parts.append(" ".join(f"#{t}" for t in tags))
    return "\n".join(parts).rstrip() + "\n"


def export_plain(topic: str, content: str, tags: list[str] | None = None) -> str:
    """Produce a plain-text file body for download (UTF-8)."""
    parts: list[str] = []
    title = (topic or "未命名").strip()
    parts.append(title)
    parts.append("=" * min(40, len(title)))
    parts.append("")
    parts.append(content.strip())
    parts.append("")
    if tags:
        parts.append("---")
        parts.append(" ".join(f"#{t}" for t in tags))
    return "\n".join(parts).rstrip() + "\n"
