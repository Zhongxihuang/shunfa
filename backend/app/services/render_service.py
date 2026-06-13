"""Render card pages to PNG via Jinja2 templates + a shared headless Chromium.

Why a process-level browser singleton: launching Chromium costs ~300ms, so we
launch once (lazily) and reuse it across requests. The FastAPI lifespan calls
`shutdown_browser()` on exit.

Tests mock `get_browser` so Chromium is never launched in CI.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .paginate_service import Page

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "cards"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

_TEMPLATE_FILES = {"a": "a.html", "b": "b.html", "c": "c.html"}
_VIEWPORT = {"width": 1080, "height": 1440}
_DEVICE_SCALE_FACTOR = 2  # export at 2160x2880 for crisp images

# process-level singletons
_playwright = None
_browser = None


def render_page_html(page: Page, template: str, total: int) -> str:
    """Render one card page to an HTML string. Pure, no browser involved."""
    if template not in _TEMPLATE_FILES:
        raise ValueError(f"unknown template: {template!r}")
    tmpl = _env.get_template(_TEMPLATE_FILES[template])
    return tmpl.render(page=page, total=total)


async def get_browser():
    """Lazily launch (and cache) a shared headless Chromium instance."""
    global _playwright, _browser
    if _browser is None:
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(args=["--no-sandbox"])
    return _browser


async def shutdown_browser() -> None:
    """Close the shared browser. Safe to call when nothing was launched."""
    global _playwright, _browser
    if _browser is not None:
        await _browser.close()
        _browser = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None


async def render_cards(pages: list[Page], template: str) -> list[bytes]:
    """Render every page to a PNG (bytes), in order."""
    total = len(pages)
    htmls = [render_page_html(p, template, total) for p in pages]

    browser = await get_browser()
    bp = await browser.new_page(viewport=_VIEWPORT, device_scale_factor=_DEVICE_SCALE_FACTOR)
    images: list[bytes] = []
    try:
        for html in htmls:
            await bp.set_content(html, wait_until="networkidle")
            images.append(await bp.screenshot(type="png"))
    finally:
        await bp.close()
    return images
