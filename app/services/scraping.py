from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


def fetch_page_text(url: str, *, html_override: str | None = None, timeout: int = 15) -> str:
    """Fetch a page and extract readable text content.

    In production this is backed by Playwright; in tests and lightweight local use,
    the helper accepts an injected HTML body to keep the path deterministic.
    """
    if html_override is not None:
        html = html_override
    else:
        import httpx

        try:
            response = httpx.get(url, timeout=timeout)
            response.raise_for_status()
            html = response.text
        except (httpx.HTTPError, ValueError):
            return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def extract_price_candidates(text: str) -> list[str]:
    patterns = [
        r"\$\s?\d+(?:[.,]\d{2})?(?:\s*/\s*month|\s*/\s*mo|\s*USD)?",
        r"\b\d+(?:[.,]\d{2})?\s*(?:USD|dollars?)\b",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    return matches


def build_page_snapshot(url: str, *, html_override: str | None = None) -> dict[str, Any]:
    text = fetch_page_text(url, html_override=html_override)
    return {
        "url": url,
        "text_content": text,
        "prices": extract_price_candidates(text),
        "word_count": len(text.split()),
    }
