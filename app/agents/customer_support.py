from __future__ import annotations

from datetime import UTC, date, datetime
import re
from typing import Any

from app.services.product_catalog import Product, list_catalog_products, recommend_products
from app.services.customer_hint_classifier import (
    CustomerHintClassifier,
    CustomerHintDecision,
    NoopCustomerHintClassifier,
)
from app.services.product_scope import find_unsupported_item
from app.services.tool_registry import ToolRegistry

_REQUIRED_BY_INTENT: dict[str, list[str]] = {
    "warranty_claim": ["model", "serial_number", "purchase_date"],
    "service_request": ["product_type", "model", "issue_description"],
    "replacement_request": ["model", "serial_number", "purchase_date"],
    "cancel_request": [],
}
_PRODUCT_CATEGORY_BY_TYPE: dict[str, str] = {
    "camera": "camera",
    "router": "router",
    "cpu": "cpu",
    "wifi_modem": "modem",
}
_SERIAL_ALLOWED_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9\-_\/]*")
_SERIAL_UNLABELED_PATTERN = re.compile(r"\s*((?=[A-Za-z0-9\-_\/]*\d)[A-Za-z0-9][A-Za-z0-9\-_\/]*)\s*")


def looks_like_warranty_model_serial(message: str) -> bool:
    return bool(_extract_space_separated_warranty_details(message))


def handle_customer_support(
    state: dict[str, Any],
    tools: ToolRegistry,
    customer_hint_classifier: CustomerHintClassifier | None = None,
) -> dict[str, Any]:
    message = str(state.get("latest_user_message", ""))
    intent = str(state.get("intent") or "warranty_claim")
    entities = _extract_entities(message, state.get("extracted_entities", {}))
    tool_calls = list(state.get("tool_calls", []))
    metadata = dict(state.get("metadata", {}))
    shared_memory = dict(state.get("shared_memory", {}))
    customer_memory = _customer_memory(shared_memory)
    classifier = customer_hint_classifier or NoopCustomerHintClassifier()
    customer_hint = classifier.classify(
        latest_user_message=message,
        intent=intent,
        state=state,
    )

    llm_hints: dict[str, Any] = {
        "agent": "customer_support",
        "intent": intent,
        "latest_user_message": message,
        "customer_message_hints": _serialize_customer_hint(customer_hint),
    }

    unsupported_item = find_unsupported_item(message)
    if unsupported_item:
        llm_hints.update({"status": "unsupported_item", "unsupported_item": unsupported_item})
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    if customer_hint.warranty_memory_lookup:
        llm_hints.update(
            {
                "status": "warranty_memory_lookup",
                "active_request": customer_memory.get("active_warranty_replacement"),
                "last_request": customer_memory.get("last_warranty_replacement"),
            }
        )
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    if intent == "cancel_request" or customer_hint.warranty_cancellation:
        cancelled = _cancel_active_warranty_replacement(
            customer_memory=customer_memory,
            product_started_working=customer_hint.cancel_reason_product_started_working,
        )
        for field in ("model", "serial_number", "purchase_date"):
            entities.pop(field, None)
        _set_customer_memory(shared_memory, customer_memory)
        llm_hints.update(
            {
                "status": "warranty_cancelled" if cancelled else "no_active_warranty_to_cancel",
                "cancelled_request": cancelled,
                "last_request": customer_memory.get("last_warranty_replacement"),
            }
        )
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    if customer_hint.non_eligible_replacement_case:
        llm_hints.update(
            {
                "status": "non_eligible_replacement_case",
                "escalate_to_sales": True,
                "upsell_context": True,
                "upsell_reason": "non_repairable_or_non_eligible",
                "recommended_products": _build_upsell_recommendations(message=message, entities=entities),
            }
        )
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    if intent not in _REQUIRED_BY_INTENT and intent != "return_request":
        intent = "warranty_claim"
        llm_hints["intent"] = intent

    if intent == "return_request":
        llm_hints.update({"status": "return_request_requirements"})
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    if intent in {"warranty_claim", "replacement_request"}:
        required_fields = _REQUIRED_BY_INTENT[intent]
        serial_value = str(entities.get("serial_number", ""))
        missing_fields = [field for field in required_fields if not entities.get(field)]

        if serial_value and not _is_valid_serial(serial_value):
            entities.pop("serial_number", None)
            llm_hints.update({"status": "serial_number_required", "missing_fields": ["serial_number"]})
            metadata["llm_hints"] = llm_hints
            return _result(entities, tool_calls, metadata, shared_memory)

        if entities.get("model") and not entities.get("serial_number"):
            llm_hints.update({"status": "serial_number_required", "missing_fields": ["serial_number"]})
            metadata["llm_hints"] = llm_hints
            return _result(entities, tool_calls, metadata, shared_memory)

        if missing_fields:
            llm_hints.update({"status": "warranty_details_required", "missing_fields": missing_fields})
            metadata["llm_hints"] = llm_hints
            return _result(entities, tool_calls, metadata, shared_memory)

        warranty_details = {
            "product_type": entities.get("product_type"),
            "model": entities.get("model"),
            "serial_number": entities.get("serial_number"),
            "purchase_date": entities.get("purchase_date"),
        }
        warranty_outcome = _warranty_outcome(str(entities.get("purchase_date", "")))

        if warranty_outcome["status"] == "warranty_initialized":
            _set_active_warranty_replacement(customer_memory, warranty_details)
            for field in ("model", "serial_number", "purchase_date"):
                entities.pop(field, None)
        elif warranty_outcome["status"] in {"invalid_purchase_date", "future_purchase_date"}:
            entities.pop("purchase_date", None)
        elif warranty_outcome["status"] == "warranty_expired":
            customer_memory.pop("active_warranty_replacement", None)
            for field in ("model", "serial_number", "purchase_date"):
                entities.pop(field, None)

        _set_customer_memory(shared_memory, customer_memory)
        hint_payload: dict[str, Any] = {
            "status": warranty_outcome["status"],
            "warranty_details": warranty_details,
            "expired_days": warranty_outcome.get("expired_days"),
            "escalate_to_sales": warranty_outcome["status"] == "warranty_expired",
        }
        if warranty_outcome["status"] == "warranty_expired":
            hint_payload.update(
                {
                    "upsell_context": True,
                    "upsell_reason": "warranty_expired",
                    "recommended_products": _build_upsell_recommendations(
                        message=message,
                        entities=entities,
                        warranty_details=warranty_details,
                    ),
                }
            )

        llm_hints.update(hint_payload)
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    required_fields = _REQUIRED_BY_INTENT[intent]
    missing_fields = [field for field in required_fields if not entities.get(field)]
    if missing_fields:
        llm_hints.update({"status": "service_request_details_required", "missing_fields": missing_fields})
        metadata["llm_hints"] = llm_hints
        return _result(entities, tool_calls, metadata, shared_memory)

    payload = {key: entities[key] for key in required_fields}
    tool_name = "create_service_request"
    tool_result = _run_tool_safe(tools=tools, tool_name=tool_name, args=payload)
    tool_calls.append(tool_result)

    llm_hints.update(
        {
            "status": "service_request_tool_error"
            if tool_result.get("status") == "tool_error"
            else "service_request_created",
            "service_request_reference_id": tool_result.get("reference_id"),
            "service_request_payload": payload,
        }
    )
    metadata["llm_hints"] = llm_hints
    return _result(entities, tool_calls, metadata, shared_memory)


def _result(
    entities: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    metadata: dict[str, Any],
    shared_memory: dict[str, Any],
) -> dict[str, Any]:
    return {
        "response": "",
        "extracted_entities": entities,
        "tool_calls": tool_calls,
        "metadata": metadata,
        "shared_memory": shared_memory,
    }


def _customer_memory(shared_memory: dict[str, Any]) -> dict[str, Any]:
    raw_memory = shared_memory.get("customer_support")
    if isinstance(raw_memory, dict):
        return dict(raw_memory)
    return {}


def _set_customer_memory(shared_memory: dict[str, Any], customer_memory: dict[str, Any]) -> None:
    if customer_memory:
        shared_memory["customer_support"] = customer_memory
    else:
        shared_memory.pop("customer_support", None)


def _set_active_warranty_replacement(customer_memory: dict[str, Any], details: dict[str, Any]) -> None:
    active_request = {
        "status": "active",
        "product_type": details.get("product_type"),
        "model": details.get("model"),
        "serial_number": details.get("serial_number"),
        "purchase_date": details.get("purchase_date"),
    }
    customer_memory["active_warranty_replacement"] = active_request
    customer_memory["last_warranty_replacement"] = dict(active_request)


def _cancel_active_warranty_replacement(
    *,
    customer_memory: dict[str, Any],
    product_started_working: bool,
) -> dict[str, Any] | None:
    active_request = customer_memory.get("active_warranty_replacement")
    if not isinstance(active_request, dict):
        return None

    cancelled_request = dict(active_request)
    cancelled_request["status"] = "cancelled"
    if product_started_working:
        cancelled_request["cancel_reason"] = "product_started_working"

    customer_memory.pop("active_warranty_replacement", None)
    customer_memory["last_warranty_replacement"] = cancelled_request
    return cancelled_request


def _run_tool_safe(tools: ToolRegistry, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = tools.invoke(tool_name, args)
        return {
            "tool_name": tool_name,
            "status": result.get("status", "mock_created"),
            "reference_id": result.get("reference_id"),
        }
    except Exception:
        return {
            "status": "tool_error",
            "tool_name": tool_name,
            "message": "tool_failed",
        }


def _extract_entities(message: str, existing: dict[str, Any]) -> dict[str, Any]:
    entities = dict(existing)
    lower = message.lower()

    if re.search(r"\b(?:wifi|wi-fi)\s+modem\b", lower) or re.search(r"\bmodems?\b", lower) or "gateway" in lower:
        entities["product_type"] = "wifi_modem"
    elif "camera" in lower:
        entities["product_type"] = "camera"
    elif "router" in lower:
        entities["product_type"] = "router"
    elif "cpu" in lower or "processor" in lower:
        entities["product_type"] = "cpu"
    elif "mobile" in lower or "phone" in lower:
        entities["product_type"] = "mobile_phone"

    comma_separated_details = _extract_comma_separated_warranty_details(message)
    if comma_separated_details:
        entities.update(comma_separated_details)
    else:
        space_separated_details = _extract_space_separated_warranty_details(message)
        if space_separated_details:
            entities.update(space_separated_details)

    model_match = re.search(
        r"\bmodel(?:\s*name|\s*number|\s*no\.?)?\s*[:\-]?\s*([a-zA-Z0-9][a-zA-Z0-9\-_]*)\b",
        message,
        flags=re.IGNORECASE,
    )
    if model_match:
        entities["model"] = model_match.group(1).upper()

    serial_match = re.search(
        r"\b(?:serial(?:\s*number|\s*no\.?)?|s\/n|sn)\s*[:\-#]?\s*([^\s,;]+)",
        message,
        flags=re.IGNORECASE,
    )
    serial_only_match = re.fullmatch(_SERIAL_UNLABELED_PATTERN, message)
    if serial_match:
        serial_value = _normalize_serial_value(serial_match.group(1))
        if _is_valid_serial(serial_value):
            entities["serial_number"] = serial_value
    elif entities.get("model") and serial_only_match:
        # Allow follow-up messages like "4545" or "SN-45A" when model context is available.
        entities["serial_number"] = serial_only_match.group(1).upper()

    iso_date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", message)
    if iso_date_match:
        entities["purchase_date"] = iso_date_match.group(1)
    else:
        us_date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", message)
        if us_date_match:
            entities["purchase_date"] = us_date_match.group(1)

    issue_match = re.search(r"\bissue\s*[:\-]?\s*(.+)$", message, flags=re.IGNORECASE)
    if issue_match and issue_match.group(1).strip():
        entities["issue_description"] = issue_match.group(1).strip()
    elif len(message.split()) > 5:
        entities.setdefault("issue_description", message.strip())

    return entities


def _extract_comma_separated_warranty_details(message: str) -> dict[str, str]:
    if any(keyword in message.lower() for keyword in ("model", "serial", "purchase")):
        return {}

    parts = [part.strip() for part in message.split(",")]
    if len(parts) != 3 or any(not part for part in parts):
        return {}

    model, serial_number, purchase_date = parts
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", purchase_date):
        return {}

    return {
        "model": model.upper(),
        "serial_number": serial_number.upper(),
        "purchase_date": purchase_date,
    }


def _extract_space_separated_warranty_details(message: str) -> dict[str, str]:
    if "," in message:
        return {}
    if any(keyword in message.lower() for keyword in ("model", "serial", "purchase")):
        return {}

    parts = [part.strip() for part in message.split()]
    model = ""
    serial_number = ""
    if len(parts) == 2:
        model, serial_number = parts
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9\-_]*", model):
            return {}
        if not _is_unlabeled_serial(serial_number):
            return {}
    else:
        freeform_match = re.fullmatch(
            r"\s*([a-zA-Z0-9][a-zA-Z0-9\-\s]*[a-zA-Z0-9])(?:\s+|[-#:/])([a-zA-Z0-9][a-zA-Z0-9\-_\/]*)\s*",
            message,
        )
        if not freeform_match:
            return {}
        model = re.sub(r"\s+", " ", freeform_match.group(1)).strip()
        serial_number = freeform_match.group(2)
        if not _is_unlabeled_serial(serial_number):
            return {}
        if not model or not re.search(r"[a-zA-Z]", model):
            return {}

    return {
        "model": model.upper(),
        "serial_number": serial_number.upper(),
    }


def looks_like_serial_only_value(message: str) -> bool:
    return bool(re.fullmatch(_SERIAL_UNLABELED_PATTERN, message))


def _normalize_serial_value(value: str) -> str:
    return str(value).strip().strip("()[]{}").rstrip(".,;:").upper()


def _is_valid_serial(value: str) -> bool:
    normalized = _normalize_serial_value(value)
    return bool(normalized and _SERIAL_ALLOWED_PATTERN.fullmatch(normalized))


def _is_unlabeled_serial(value: str) -> bool:
    normalized = _normalize_serial_value(value)
    if not _is_valid_serial(normalized):
        return False
    return any(ch.isdigit() for ch in normalized)


def _warranty_outcome(purchase_date_raw: str) -> dict[str, Any]:
    purchase_date = _parse_purchase_date(purchase_date_raw)
    if purchase_date is None:
        return {"status": "invalid_purchase_date"}

    today = datetime.now(UTC).date()
    elapsed_days = (today - purchase_date).days
    if elapsed_days < 0:
        return {"status": "future_purchase_date"}

    warranty_days = 730
    if elapsed_days <= warranty_days:
        return {"status": "warranty_initialized"}

    expired_days = elapsed_days - warranty_days
    return {"status": "warranty_expired", "expired_days": expired_days}


def _parse_purchase_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _build_upsell_recommendations(
    *,
    message: str,
    entities: dict[str, Any],
    warranty_details: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    category = _resolve_upsell_category(message=message, entities=entities, warranty_details=warranty_details)
    model_name = ""
    if isinstance(warranty_details, dict):
        model_name = str(warranty_details.get("model") or "").strip()
    if not model_name:
        model_name = str(entities.get("model") or "").strip()

    query_parts = [part for part in (category, model_name, message) if part]
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
        if category is None or product.category == category
    ]
    for product in fallback:
        if product.name in seen_names:
            continue
        recommendations.append(_serialize_product(product))
        if len(recommendations) >= limit:
            break
    return recommendations


def _resolve_upsell_category(
    *,
    message: str,
    entities: dict[str, Any],
    warranty_details: dict[str, Any] | None,
) -> str | None:
    candidate_types: list[str] = []
    if isinstance(warranty_details, dict):
        candidate_types.append(str(warranty_details.get("product_type") or "").strip().lower())
    candidate_types.append(str(entities.get("product_type") or "").strip().lower())

    for candidate in candidate_types:
        mapped = _PRODUCT_CATEGORY_BY_TYPE.get(candidate)
        if mapped:
            return mapped

    lower = message.lower()
    if "camera" in lower:
        return "camera"
    if "router" in lower:
        return "router"
    if "cpu" in lower or "processor" in lower:
        return "cpu"
    if any(term in lower for term in ("modem", "wifi modem", "wi-fi modem", "gateway", "wifi", "wi-fi")):
        return "modem"
    return None


def _serialize_product(product: Product) -> dict[str, Any]:
    return {
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "summary": product.summary,
        "features": list(product.features),
    }


def _serialize_customer_hint(decision: CustomerHintDecision) -> dict[str, Any]:
    return {
        "warranty_memory_lookup": decision.warranty_memory_lookup,
        "warranty_cancellation": decision.warranty_cancellation,
        "non_eligible_replacement_case": decision.non_eligible_replacement_case,
        "cancel_reason_product_started_working": decision.cancel_reason_product_started_working,
        "confidence": decision.confidence,
    }
