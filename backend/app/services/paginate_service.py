"""Deterministic pagination for the paste-to-cards feature.

Pure function, NO AI, NO randomness. The hard guarantee: it never adds, removes,
or rewrites a single character of the user's text — it only decides where to
break it into cards. Given the same (raw_text, cover_title) the output is
byte-for-byte identical.
"""

from dataclasses import dataclass, field

MAX_CHARS_PER_PAGE = 240
MAX_PARAS_PER_PAGE = 6
MAX_PAGES = 8  # including the cover

# Sentence-ending punctuation we prefer to break a too-long paragraph at.
_SOFT_BREAK_CHARS = "。；？！"


@dataclass
class Page:
    index: int
    kind: str  # 'cover' | 'body'
    title: str | None = None
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class PaginationResult:
    pages: list[Page]
    page_count: int
    overflow: bool


def _split_long_paragraph(p: str, limit: int) -> list[str]:
    """Break a paragraph longer than `limit` into <= limit-sized chunks,
    preferring to cut just after a sentence-ending char. Never drops chars."""
    chunks: list[str] = []
    while len(p) > limit:
        window = p[:limit]
        cut = max((window.rfind(c) for c in _SOFT_BREAK_CHARS), default=-1)
        if cut <= 0:
            cut = limit - 1  # no punctuation in window -> hard cut at the limit
        chunks.append(p[: cut + 1])
        p = p[cut + 1 :]
    if p:
        chunks.append(p)
    return chunks


def paginate(raw_text: str, cover_title: str | None = None) -> PaginationResult:
    # 1. clean: split into paragraphs, strip, drop empties
    paragraphs = [line.strip() for line in (raw_text or "").split("\n")]
    paragraphs = [p for p in paragraphs if p]

    # 2. cover: explicit title wins; otherwise the first paragraph is promoted
    cover = (cover_title or "").strip()
    if not cover and paragraphs:
        cover = paragraphs.pop(0)

    # 3. expand any oversize paragraph into chunks
    expanded: list[str] = []
    for p in paragraphs:
        if len(p) > MAX_CHARS_PER_PAGE:
            expanded.extend(_split_long_paragraph(p, MAX_CHARS_PER_PAGE))
        else:
            expanded.append(p)

    # 4. fill body pages respecting char + paragraph caps
    body_pages: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for p in expanded:
        would_overflow_chars = current_len + len(p) > MAX_CHARS_PER_PAGE
        would_overflow_paras = len(current) >= MAX_PARAS_PER_PAGE
        if current and (would_overflow_chars or would_overflow_paras):
            body_pages.append(current)
            current = []
            current_len = 0
        current.append(p)
        current_len += len(p)
    if current:
        body_pages.append(current)

    # 5. assemble pages with 1-based indices
    pages: list[Page] = [Page(index=1, kind="cover", title=cover, paragraphs=[])]
    for group in body_pages:
        pages.append(Page(index=len(pages) + 1, kind="body", title=None, paragraphs=group))

    page_count = len(pages)
    overflow = page_count > MAX_PAGES  # never truncate — just flag it
    return PaginationResult(pages=pages, page_count=page_count, overflow=overflow)
