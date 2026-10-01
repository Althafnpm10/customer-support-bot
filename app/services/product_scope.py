from __future__ import annotations

import re

_SUPPORTED_ALIASES: dict[str, str] = {
    "camera": "camera",
    "cameras": "camera",
    "router": "router",
    "routers": "router",
    "wifi": "wifi",
    "wi-fi": "wifi",
    "modem": "wifi_modem",
    "modems": "wifi_modem",
    "wifi modem": "wifi_modem",
    "wi-fi modem": "wifi_modem",
    "gateway": "wifi_modem",
    "cpu": "cpu",
    "cpus": "cpu",
    "processor": "cpu",
    "processors": "cpu",
}

_UNSUPPORTED_ALIASES: dict[str, str] = {
    "mobile": "mobile phone",
    "phone": "mobile phone",
    "phones": "mobile phone",
    "laptop": "laptop",
    "laptops": "laptop",
    "tablet": "tablet",
    "tablets": "tablet",
    "monitor": "monitor",
    "monitors": "monitor",
    "tv": "tv",
    "tvs": "tv",
    "television": "tv",
    "televisions": "tv",
}

_CANDIDATE_STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "any",
    "are",
    "battery",
    "can",
    "charge",
    "charging",
    "claim",
    "connect",
    "connection",
    "disconnect",
    "disconnecting",
    "do",
    "date",
    "for",
    "help",
    "how",
    "i",
    "in",
    "is",
    "issue",
    "it",
    "left",
    "me",
    "my",
    "need",
    "not",
    "of",
    "on",
    "please",
    "power",
    "problem",
    "purchase",
    "purchased",
    "repair",
    "replace",
    "replacement",
    "return",
    "service",
    "slow",
    "support",
    "that",
    "the",
    "to",
    "warranty",
    "what",
    "when",
    "why",
    "wifi",
    "wi-fi",
    "with",
    "working",
}


def find_unsupported_item(message: str) -> str | None:
    text = message.lower()

    for alias, canonical in _sorted_aliases(_UNSUPPORTED_ALIASES):
        if _contains_alias(text, alias):
            return canonical

    for alias, canonical in _sorted_aliases(_SUPPORTED_ALIASES):
        if _contains_alias(text, alias):
            return None

    candidate = _best_candidate_token(text)
    if not candidate:
        return None
    if candidate in _SUPPORTED_ALIASES:
        return None
    return candidate


def find_explicit_unsupported_item(message: str) -> str | None:
    text = message.lower()
    for alias, canonical in _sorted_aliases(_UNSUPPORTED_ALIASES):
        if _contains_alias(text, alias):
            return canonical
    return None


def unsupported_item_message(item: str) -> str:
    return (
        f"Sorry, we dont deal with {item} right now. "
        "We currently support camera, wifi, wifi modem, router, and cpu."
    )


def _contains_alias(text: str, alias: str) -> bool:
    return bool(re.search(rf"\b{re.escape(alias)}\b", text))


def _sorted_aliases(mapping: dict[str, str]) -> list[tuple[str, str]]:
    return sorted(mapping.items(), key=lambda pair: len(pair[0]), reverse=True)


def _best_candidate_token(text: str) -> str | None:
    for prefix in ("my", "about", "for", "with"):
        for match in re.finditer(rf"\b{prefix}\s+([a-z0-9\-]+)\b", text):
            token = match.group(1)
            if _is_valid_candidate(token):
                return token

    for match in re.finditer(
        r"\b([a-z0-9\-]+)\s+(?:is\s+)?(?:not working|broken|issue|problem|fails|failing)\b",
        text,
    ):
        token = match.group(1)
        if _is_valid_candidate(token):
            return token
    return None


def _is_valid_candidate(token: str) -> bool:
    if len(token) <= 2:
        return False
    if token in _CANDIDATE_STOPWORDS:
        return False
    if any(char.isdigit() for char in token):
        return False
    return True
