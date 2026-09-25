from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


def fetch_page_text(url: str, *, html_override: str | None = None, timeout: int = 15) -> str | None:
    """Fetch a page and extract readable text content.

    In production this is backed by Playwright; in tests and lightweight local use,
    the helper accepts an injected HTML body to keep the path deterministic.

    Returns None when the page could not be fetched (network error, DNS failure,
    or non-2xx status) so callers can distinguish "fetched, but empty" from
    "could not fetch at all" instead of treating failures as real content.
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
            return None

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
    """Build a snapshot payload, reporting fetch success explicitly.

    Callers must check `fetch_ok` before treating `text_content` as real page
    content: a failed or empty fetch must never be diffed against a prior
    snapshot, or the empty text registers as a bogus "material change".
    """
    try:
        text = fetch_page_text(url, html_override=html_override)
    except Exception as exc:  # defensive: extraction must never crash a cycle
        return {
            "url": url,
            "fetch_ok": False,
            "fetch_error": f"extraction failed: {exc}",
            "text_content": "",
            "prices": [],
            "word_count": 0,
        }

    if text is None:
        return {
            "url": url,
            "fetch_ok": False,
            "fetch_error": "page unreachable or returned an error status",
            "text_content": "",
            "prices": [],
            "word_count": 0,
        }

    if not text.strip():
        return {
            "url": url,
            "fetch_ok": False,
            "fetch_error": "page returned no readable content",
            "text_content": "",
            "prices": [],
            "word_count": 0,
        }

    return {
        "url": url,
        "fetch_ok": True,
        "fetch_error": None,
        "text_content": text,
        "prices": extract_price_candidates(text),
        "word_count": len(text.split()),
    }
