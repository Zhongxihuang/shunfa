"""Render service: HTML templating is tested for real; the Playwright
screenshot path is fully mocked so tests never launch Chromium."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.paginate_service import Page
from app.services.render_service import render_cards, render_page_html


def test_render_page_html_cover_contains_title_and_index():
    page = Page(index=1, kind="cover", title="大厂裁掉 prompt 工程师", paragraphs=[])
    html = render_page_html(page, "a", total=3)
    assert "大厂裁掉 prompt 工程师" in html
    assert "01 / 03" in html


def test_render_page_html_body_contains_paragraphs():
    page = Page(index=2, kind="body", title=None, paragraphs=["正文一", "正文二"])
    html = render_page_html(page, "b", total=2)
    assert "正文一" in html
    assert "正文二" in html


def test_render_page_html_unknown_template_raises():
    page = Page(index=1, kind="cover", title="x", paragraphs=[])
    with pytest.raises(ValueError):
        render_page_html(page, "z", total=1)


def test_render_cards_screenshots_every_page():
    pages = [
        Page(index=1, kind="cover", title="封面", paragraphs=[]),
        Page(index=2, kind="body", title=None, paragraphs=["正文"]),
    ]

    fake_page = AsyncMock()
    fake_page.screenshot = AsyncMock(return_value=b"PNGDATA")
    fake_browser = AsyncMock()
    fake_browser.new_page = AsyncMock(return_value=fake_page)

    with patch(
        "app.services.render_service.get_browser",
        new=AsyncMock(return_value=fake_browser),
    ):
        images = asyncio.run(render_cards(pages, "a"))

    assert images == [b"PNGDATA", b"PNGDATA"]
    assert fake_page.screenshot.await_count == 2
