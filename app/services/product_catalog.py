from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Product:
    name: str
    category: str
    price: int
    summary: str
    features: tuple[str, ...]


@dataclass(frozen=True)
class ProductRecommendation:
    product: Product
    score: int
    reasons: tuple[str, ...]


_CATALOG: tuple[Product, ...] = (
    Product(
        name="Atlas CX100 Mirrorless Camera",
        category="camera",
        price=899,
        summary="24MP mirrorless camera with dual-band WiFi and stabilization.",
        features=("24mp", "dual-band wifi", "image stabilization", "mirrorless", "creator"),
    ),
    Product(
        name="Atlas Vlog Pro 4K",
        category="camera",
        price=549,
        summary="Ultra-light 4K creator camera with fast autofocus.",
        features=("4k", "fast autofocus", "ultra-light", "creator", "vlogging"),
    ),
    Product(
        name="ZenCore X8 Desktop CPU",
        category="cpu",
        price=359,
        summary="8-core desktop CPU with 16 threads and up to 5.1 GHz boost.",
        features=("8 cores", "16 threads", "5.1 ghz boost", "gaming", "performance"),
    ),
    Product(
        name="ZenCore X12 Creator CPU",
        category="cpu",
        price=519,
        summary="12-core workstation CPU tuned for creator workloads.",
        features=("12 cores", "workstation", "creator", "heavy builds", "multitasking"),
    ),
    Product(
        name="AeroLink AX5400 Router",
        category="router",
        price=229,
        summary="High-speed dual-band router for streaming-focused homes.",
        features=("dual-band", "high-speed", "home streaming", "ax5400", "wifi"),
    ),
    Product(
        name="AeroLink Mesh Router Kit",
        category="router",
        price=299,
        summary="Whole-home mesh router kit with easy app setup.",
        features=("mesh", "whole-home coverage", "easy setup", "wifi", "coverage"),
    ),
    Product(
        name="WaveNet DOCSIS 3.1 Modem",
        category="modem",
        price=189,
        summary="Low-latency DOCSIS 3.1 modem for gigabit cable plans.",
        features=("docsis 3.1", "low-latency", "gigabit", "cable", "stable connection"),
    ),
    Product(
        name="WaveNet Fiber Gateway",
        category="modem",
        price=259,
        summary="Fiber-ready gateway modem with advanced thermal control.",
        features=("fiber-ready", "advanced thermal control", "low-latency", "gateway", "reliability"),
    ),
)

_FEATURE_KEYWORDS: dict[str, str] = {
    "4k": "4k",
    "autofocus": "fast autofocus",
    "stabilization": "image stabilization",
    "stabilized": "image stabilization",
    "creator": "creator",
    "vlog": "vlogging",
    "vlogging": "vlogging",
    "gaming": "gaming",
    "workstation": "workstation",
    "performance": "performance",
    "multitasking": "multitasking",
    "dual-band": "dual-band",
    "dual band": "dual-band",
    "wifi": "wifi",
    "mesh": "mesh",
    "coverage": "coverage",
    "streaming": "home streaming",
    "high-speed": "high-speed",
    "high speed": "high-speed",
    "gigabit": "gigabit",
    "low latency": "low-latency",
    "latency": "low-latency",
    "fiber": "fiber-ready",
    "thermal": "advanced thermal control",
    "reliable": "reliability",
    "reliability": "reliability",
}

_CATEGORY_KEYWORDS: dict[str, str] = {
    "camera": "camera",
    "cameras": "camera",
    "cpu": "cpu",
    "cpus": "cpu",
    "processor": "cpu",
    "processors": "cpu",
    "router": "router",
    "routers": "router",
    "modem": "modem",
    "modems": "modem",
    "wifi modem": "modem",
    "wi-fi modem": "modem",
    "wifi": "modem",
    "wi-fi": "modem",
    "gateway": "modem",
}


def list_catalog_products() -> tuple[Product, ...]:
    return _CATALOG


def find_products_in_text(message: str) -> list[Product]:
    text = _normalize(message)
    matches: list[tuple[int, Product]] = []
    for product in _CATALOG:
        index = text.find(_normalize(product.name))
        if index >= 0:
            matches.append((index, product))
    matches.sort(key=lambda item: item[0])
    return [item[1] for item in matches]


def get_product_by_name(name: str) -> Product | None:
    needle = _normalize(name)
    for product in _CATALOG:
        if _normalize(product.name) == needle:
            return product
    return None


def extract_budget(message: str) -> int | None:
    match = re.search(
        r"\b(?:under|below|less than|up to|max|maximum|budget)\s*\$?\s*(\d{2,5})\b",
        message.lower(),
    )
    if match:
        return int(match.group(1))

    loose_match = re.search(r"\$\s*(\d{2,5})\b", message)
    if loose_match:
        return int(loose_match.group(1))
    return None


def extract_category(message: str) -> str | None:
    lower = message.lower()
    for keyword, category in _CATEGORY_KEYWORDS.items():
        if keyword in lower:
            return category
    return None


def extract_feature_preferences(message: str) -> set[str]:
    lower = message.lower()
    preferences: set[str] = set()
    for keyword, feature in _FEATURE_KEYWORDS.items():
        if keyword in lower:
            preferences.add(feature)
    preferences.update(_extract_dynamic_feature_preferences(lower))
    return preferences


def recommend_products(message: str, *, limit: int = 3) -> list[ProductRecommendation]:
    category = extract_category(message)
    budget = extract_budget(message)
    wanted_features = extract_feature_preferences(message)

    ranked: list[ProductRecommendation] = []
    for product in _CATALOG:
        if category and product.category != category:
            continue

        score = 0
        reasons: list[str] = []
        normalized_features = {_normalize(feature) for feature in product.features}

        for wanted in wanted_features:
            normalized_wanted = _normalize(wanted)
            if any(normalized_wanted in feature for feature in normalized_features):
                score += 3
                reasons.append(f"matches '{wanted}'")

        if budget is not None:
            if product.price <= budget:
                score += 2
                reasons.append(f"within your budget (${budget})")
            else:
                score -= 3
                reasons.append(f"above your budget (${budget})")

        if wanted_features:
            score += 1
        if category and product.category == category:
            score += 1

        ranked.append(ProductRecommendation(product=product, score=score, reasons=tuple(reasons)))

    ranked.sort(key=lambda rec: (-rec.score, rec.product.price))

    filtered = [rec for rec in ranked if rec.score > -2]
    return filtered[:limit]


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _extract_dynamic_feature_preferences(lower: str) -> set[str]:
    dynamic: set[str] = set()

    for match in re.finditer(r"\b(\d{1,2})\s*[- ]?(?:core|cores)\b", lower):
        dynamic.add(f"{int(match.group(1))} cores")

    for match in re.finditer(r"\b(\d{1,3})\s*[- ]?(?:thread|threads)\b", lower):
        dynamic.add(f"{int(match.group(1))} threads")

    for match in re.finditer(r"\b(\d{1,3})\s*mp\b", lower):
        dynamic.add(f"{int(match.group(1))}mp")

    for match in re.finditer(r"\b(\d(?:\.\d)?)\s*ghz\b", lower):
        dynamic.add(f"{match.group(1)} ghz")

    return dynamic
