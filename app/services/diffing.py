import re
from difflib import SequenceMatcher, ndiff


def has_material_change(previous_text: str, current_text: str, min_delta: float = 0.08) -> bool:
    if not previous_text and not current_text:
        return False

    similarity = SequenceMatcher(None, previous_text.lower(), current_text.lower()).ratio()
    delta = 1.0 - similarity
    return delta >= min_delta


def summarize_changed_tokens(previous_text: str, current_text: str) -> list[str]:
    delta = list(ndiff((previous_text or "").lower().split(), (current_text or "").lower().split()))
    changes = []
    for item in delta:
        if item.startswith("- ") or item.startswith("+ "):
            changes.append(item[2:])
    return changes


def detect_page_type(url: str) -> str:
    normalized = url.lower()
    if any(token in normalized for token in ["pricing", "/plans", "/pricing"]):
        return "pricing"
    if any(token in normalized for token in ["careers", "/jobs", "hiring"]):
        return "hiring"
    if any(token in normalized for token in ["product", "/features", "/solutions"]):
        return "product"
    return "other"


def detect_pricing_shift(previous_text: str, current_text: str) -> bool:
    prev_numbers = re.findall(r"\$?\d+(?:\.\d+)?", previous_text)
    curr_numbers = re.findall(r"\$?\d+(?:\.\d+)?", current_text)
    if prev_numbers and curr_numbers and prev_numbers != curr_numbers:
        return True
    return any(token in (previous_text + current_text).lower() for token in ["pricing", "plan", "monthly", "yearly"])


def build_change_summary(previous_text: str, current_text: str, url: str) -> dict:
    page_type = detect_page_type(url)
    price_shift = detect_pricing_shift(previous_text, current_text)
    material_change = has_material_change(previous_text, current_text) or (page_type == "pricing" and price_shift)
    changed_tokens = summarize_changed_tokens(previous_text, current_text)

    category = "pricing" if page_type == "pricing" or price_shift else page_type
    if not material_change:
        return {
            "material_change": False,
            "page_type": page_type,
            "category": category,
            "confidence": 0.0,
            "summary": "No material change detected.",
            "changed_tokens": changed_tokens,
        }

    confidence = 0.75 if price_shift else 0.6
    summary = "Pricing changed significantly." if price_shift else "Content drift detected on tracked page."

    return {
        "material_change": True,
        "page_type": page_type,
        "category": category,
        "confidence": confidence,
        "summary": summary,
        "changed_tokens": changed_tokens[:10],
    }
