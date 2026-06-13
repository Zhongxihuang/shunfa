"""Deterministic pagination — no AI, no randomness, never drops characters."""

from app.services.paginate_service import (
    MAX_CHARS_PER_PAGE,
    MAX_PAGES,
    paginate,
)


def test_single_paragraph_no_cover_becomes_cover_only():
    result = paginate("大厂悄悄裁掉 prompt 工程师")
    assert result.page_count == 1
    assert result.pages[0].kind == "cover"
    assert result.pages[0].title == "大厂悄悄裁掉 prompt 工程师"
    assert result.overflow is False


def test_first_paragraph_becomes_cover_rest_become_body():
    result = paginate("封面金句\n正文一\n正文二")
    assert result.pages[0].kind == "cover"
    assert result.pages[0].title == "封面金句"
    assert result.pages[1].kind == "body"
    assert result.pages[1].paragraphs == ["正文一", "正文二"]
    assert result.page_count == 2


def test_explicit_cover_title_keeps_all_paragraphs_in_body():
    result = paginate("正文一\n正文二", cover_title="我的封面")
    assert result.pages[0].title == "我的封面"
    assert result.pages[1].paragraphs == ["正文一", "正文二"]


def test_blank_lines_are_dropped():
    result = paginate("封面\n\n  \n正文")
    assert result.pages[0].title == "封面"
    assert result.pages[1].paragraphs == ["正文"]


def test_paragraphs_per_page_cap_splits_into_new_page():
    # 1 cover + 7 short body paragraphs; cap is 6 paras/page -> 6 then 1
    text = "\n".join(["封面"] + ["短"] * 7)
    result = paginate(text)
    assert result.page_count == 3  # cover + 2 body pages
    assert len(result.pages[1].paragraphs) == 6
    assert len(result.pages[2].paragraphs) == 1


def test_char_cap_splits_into_new_page():
    # two 150-char paragraphs in body: 150+150 > 240 -> two pages
    text = ("甲" * 150) + "\n" + ("乙" * 150)
    result = paginate(text, cover_title="封面")
    body = result.pages[1:]
    assert len(body) == 2
    assert body[0].paragraphs == ["甲" * 150]
    assert body[1].paragraphs == ["乙" * 150]


def test_oversize_single_paragraph_is_soft_split_without_losing_chars():
    para = "测试。" * 100  # 300 chars, > MAX_CHARS_PER_PAGE
    result = paginate(para, cover_title="封面")
    # all body text concatenated must equal the original paragraph exactly
    joined = "".join(p for page in result.pages[1:] for p in page.paragraphs)
    assert joined == para
    # each body page must respect the char cap
    for page in result.pages[1:]:
        assert sum(len(p) for p in page.paragraphs) <= MAX_CHARS_PER_PAGE


def test_overflow_flag_set_when_exceeding_max_pages():
    # 20 paragraphs of 200 chars each -> each needs its own page -> >8 pages
    text = "\n".join(["封面"] + [("内容" * 100) for _ in range(20)])
    result = paginate(text)
    assert result.page_count > MAX_PAGES
    assert result.overflow is True
    # never silently truncates: all 20 body paragraphs are still present
    assert len(result.pages) - 1 == 20


def test_deterministic_same_input_same_output():
    text = "封面\n正文一\n正文二\n正文三"
    a = paginate(text)
    b = paginate(text)
    assert [(p.kind, p.title, p.paragraphs) for p in a.pages] == [
        (p.kind, p.title, p.paragraphs) for p in b.pages
    ]
