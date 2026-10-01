from __future__ import annotations

from typing import Any

from app.services.product_catalog import Product, list_catalog_products, recommend_products
from app.services.knowledge_base import KnowledgeBaseService
from app.services.product_scope import find_unsupported_item
from app.services.tech_hint_classifier import (
    NoopTechHintClassifier,
    TechHintClassifier,
    TechHintDecision,
)

_FOLLOW_UP_FLAG = "awaiting_tech_attempts"
_LAST_SECTION_KEY = "last_tech_section"
_SECTION_QUERY_HINT = {
    "router": "router",
    "camera": "camera",
    "wifi_modem": "modem",
    "cpu": "cpu",
}
_SECTION_TO_CATEGORY = {
    "router": "router",
    "camera": "camera",
    "wifi_modem": "modem",
    "cpu": "cpu",
}


def handle_tech_support(
    state: dict[str, Any],
    knowledge_base: KnowledgeBaseService,
    tech_hint_classifier: TechHintClassifier | None = None,
) -> dict[str, Any]:
    message = str(state.get("latest_user_message", ""))
    metadata = dict(state.get("metadata", {}))
    classifier = tech_hint_classifier or NoopTechHintClassifier()
    tech_hint = classifier.classify(latest_user_message=message, state=state)
    explicit_section = tech_hint.section if tech_hint.section != "general" else ""
    last_section = str(metadata.get(_LAST_SECTION_KEY, "")).strip().lower()
    section_context = explicit_section or last_section

    llm_hints: dict[str, Any] = {
        "agent": "tech_support",
        "latest_user_message": message,
        "tech_message_hints": _serialize_tech_hint(tech_hint),
    }

    if metadata.get(_FOLLOW_UP_FLAG) and tech_hint.follow_up_attempt:
        section = str(metadata.get(_LAST_SECTION_KEY, "general"))
        attempted_ids = sorted(tech_hint.attempted_step_ids or [])
        attempted_steps = [
            step["label"] for step in _section_steps(section) if step["id"] in set(attempted_ids)
        ]
        remaining_steps = [step for step in _section_steps(section) if step["id"] not in set(attempted_ids)]
        if not remaining_steps:
            llm_hints.update(
                {
                    "status": "troubleshooting_exhausted",
                    "section": section,
                    "attempted_step_ids": attempted_ids,
                    "attempted_steps": attempted_steps,
                    "escalate_to_sales": True,
                    "upsell_context": True,
                    "upsell_reason": "troubleshooting_exhausted",
                    "recommended_products": _build_replacement_recommendations(message=message, section=section),
                }
            )
            metadata[_FOLLOW_UP_FLAG] = False
            metadata["llm_hints"] = llm_hints
            return {"response": "", "metadata": metadata}
        llm_hints.update(
            {
                "status": "follow_up",
                "section": section,
                "attempted_step_ids": attempted_ids,
                "attempted_steps": attempted_steps,
                "next_steps": [step["guidance"] for step in remaining_steps[:2]],
                "ask_for_error_details": True,
            }
        )
        metadata[_FOLLOW_UP_FLAG] = False
        metadata["llm_hints"] = llm_hints
        return {"response": "", "metadata": metadata}

    unsupported_item = find_unsupported_item(message)
    if unsupported_item:
        llm_hints.update({"status": "unsupported_item", "unsupported_item": unsupported_item})
        metadata[_FOLLOW_UP_FLAG] = False
        metadata.pop(_LAST_SECTION_KEY, None)
        metadata["llm_hints"] = llm_hints
        return {"response": "", "metadata": metadata}

    if tech_hint.non_resolvable_issue:
        llm_hints.update(
            {
                "status": "non_resolvable_issue",
                "section": section_context or "general",
                "escalate_to_sales": True,
                "upsell_context": True,
                "upsell_reason": "issue_not_resolvable",
                "recommended_products": _build_replacement_recommendations(message=message, section=section_context),
            }
        )
        metadata[_FOLLOW_UP_FLAG] = False
        if section_context:
            metadata[_LAST_SECTION_KEY] = section_context
        metadata["llm_hints"] = llm_hints
        return {"response": "", "metadata": metadata}

    search_query = _contextualized_search_query(message=message, section_hint=section_context)
    preferred_section = section_context
    match = knowledge_base.search(search_query, preferred_section=preferred_section)
    if match is None:
        llm_hints.update(
            {
                "status": "kb_miss",
                "section": section_context or "general",
                "escalate_to_sales": bool(section_context),
                "upsell_context": bool(section_context),
                "upsell_reason": "no_solution_found" if section_context else "",
                "recommended_products": _build_replacement_recommendations(message=message, section=section_context)
                if section_context
                else [],
            }
        )
        metadata[_FOLLOW_UP_FLAG] = False
        if section_context:
            metadata[_LAST_SECTION_KEY] = section_context
        else:
            metadata.pop(_LAST_SECTION_KEY, None)
        metadata["llm_hints"] = llm_hints
        return {"response": "", "metadata": metadata}

    section = _section_key_from_label(match.section)
    llm_hints.update(
        {
            "status": "kb_match",
            "section": section,
            "knowledge_section": match.section,
            "knowledge_text": match.text,
            "follow_up_expected": True,
        }
    )
    metadata[_FOLLOW_UP_FLAG] = True
    metadata[_LAST_SECTION_KEY] = section
    metadata["llm_hints"] = llm_hints
    return {"response": "", "metadata": metadata}


def is_tech_attempt_follow_up(
    state: dict[str, Any],
    latest_message: str,
    tech_hint_classifier: TechHintClassifier | None = None,
) -> bool:
    metadata = state.get("metadata", {})
    if not metadata.get(_FOLLOW_UP_FLAG):
        return False
    classifier = tech_hint_classifier or NoopTechHintClassifier()
    decision = classifier.classify(latest_user_message=latest_message, state=state)
    return decision.follow_up_attempt


def _section_key_from_label(section: str) -> str:
    lower = section.lower()
    if "router" in lower:
        return "router"
    if "modem" in lower or "gateway" in lower:
        return "wifi_modem"
    if "camera" in lower:
        return "camera"
    if "cpu" in lower or "processor" in lower:
        return "cpu"
    return "general"


def _section_steps(section: str) -> list[dict[str, str]]:
    if section == "router":
        return [
            {"id": "restart", "label": "restarting the router", "guidance": "check for overheating"},
            {"id": "placement", "label": "improving router placement", "guidance": "change Wi-Fi channel and placement"},
            {"id": "firmware", "label": "updating router firmware", "guidance": "update firmware from the admin page"},
            {"id": "reset", "label": "factory reset", "guidance": "perform a 10-second reset and reconfigure"},
        ]
    if section == "camera":
        return [
            {"id": "battery", "label": "battery and charging checks", "guidance": "try a different battery or cable"},
            {"id": "restart", "label": "camera restart", "guidance": "perform a hard reset"},
            {"id": "firmware", "label": "firmware update", "guidance": "update firmware and retry"},
        ]
    if section == "wifi_modem":
        return [
            {"id": "cable", "label": "cable checks", "guidance": "tighten cable connections and bypass splitters"},
            {"id": "restart", "label": "modem restart", "guidance": "power cycle the modem for 60 seconds"},
            {"id": "firmware", "label": "firmware and ISP checks", "guidance": "review modem logs and ask ISP to verify line levels"},
            {"id": "placement", "label": "placement adjustments", "guidance": "move modem to an open central location"},
        ]
    if section == "cpu":
        return [
            {"id": "overheat", "label": "temperature checks", "guidance": "clean heatsinks and verify airflow"},
            {"id": "firmware", "label": "BIOS/firmware checks", "guidance": "review BIOS limits and fan curve"},
            {"id": "reset", "label": "system reset steps", "guidance": "reset BIOS defaults and retest"},
        ]
    return [
        {"id": "restart", "label": "restart", "guidance": "restart the device and related network gear"},
        {"id": "cable", "label": "cable checks", "guidance": "check cable and port connections"},
        {"id": "firmware", "label": "update checks", "guidance": "install latest firmware/software updates"},
    ]


def _contextualized_search_query(*, message: str, section_hint: str) -> str:
    current = str(message or "").strip()
    if not current:
        return current
    section_query = _SECTION_QUERY_HINT.get(str(section_hint or "").strip().lower())
    if not section_query:
        return current
    return f"{section_query} {current}"


def _build_replacement_recommendations(message: str, section: str, *, limit: int = 3) -> list[dict[str, Any]]:
    category = _SECTION_TO_CATEGORY.get((section or "").strip().lower(), "")
    query_parts = [part for part in (category, message) if part]
    query = " ".join(query_parts).strip()

    recommendations: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for rec in recommend_products(query, limit=limit):
        product = rec.product
        if category and product.category != category:
            continue
        if product.name in seen_names:
            continue
        seen_names.add(product.name)
        recommendations.append(_serialize_product(product))
        if len(recommendations) >= limit:
            return recommendations

    fallback = [
        product
        for product in list_catalog_products()
        if not category or product.category == category
    ]
    for product in fallback:
        if product.name in seen_names:
            continue
        recommendations.append(_serialize_product(product))
        if len(recommendations) >= limit:
            break
    return recommendations


def _serialize_product(product: Product) -> dict[str, Any]:
    return {
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "summary": product.summary,
        "features": list(product.features),
    }


def _serialize_tech_hint(decision: TechHintDecision) -> dict[str, Any]:
    return {
        "section": decision.section,
        "follow_up_attempt": decision.follow_up_attempt,
        "attempted_step_ids": list(decision.attempted_step_ids or []),
        "non_resolvable_issue": decision.non_resolvable_issue,
        "confidence": decision.confidence,
    }
