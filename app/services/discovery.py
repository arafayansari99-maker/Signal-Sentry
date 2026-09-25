from urllib.parse import urlparse

DISCOVERY_PATHS = {
    "/pricing": "pricing",
    "/plans": "pricing",
    "/product": "product",
    "/features": "product",
    "/careers": "hiring",
    "/jobs": "hiring",
}


def discover_urls(domain: str) -> list[dict[str, str]]:
    parsed = urlparse(domain)
    hostname = parsed.netloc or parsed.path
    if not hostname:
        return []

    base = f"https://{hostname.strip('/')}"
    candidate_urls: list[dict[str, str]] = []

    for path, page_type in DISCOVERY_PATHS.items():
        candidate_urls.append({"url": f"{base}{path}", "page_type": page_type})

    return candidate_urls
