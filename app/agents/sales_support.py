from __future__ import annotations

from typing import Any

from app.services.product_catalog import (
    Product,
    find_products_in_text,
    get_product_by_name,
    list_catalog_products,
    recommend_products,
)
from app.services.product_scope import find_explicit_unsupported_item
from app.services.sales_hint_classifier import (
    NoopSalesHintClassifier,
    SalesHintClassifier,
    SalesHintDecision,
)
from app.services.tool_registry import ToolRegistry

_FOLLOW_UP_FLAG = "awaiting_sales_follow_up"


def handle_sales_support(
    state: dict[str, Any],
    tools: ToolRegistry,
    sales_hint_classifier: SalesHintClassifier | None = None,
) -> dict[str, Any]:
    message = str(state.get("latest_user_message", ""))
    intent = str(state.get("intent") or "sales_general")
    metadata = dict(state.get("metadata", {}))
    tool_calls = list(state.get("tool_calls", []))
    shared_memory = dict(state.get("shared_memory", {}))
    sales_memory = _sales_memory(shared_memory)
    classifier = sales_hint_classifier or NoopSalesHintClassifier()
    sales_hint = classifier.classify(
        latest_user_message=message,
        intent=intent,
        state=state,
    )

    llm_hints: dict[str, Any] = {
        "agent": "sales_support",
        "intent": intent,
        "latest_user_message": message,
        "sales_message_hints": _serialize_sales_hint(sales_hint),
    }

    unsupported_item = find_explicit_unsupported_item(message)
    if unsupported_item:
        metadata[_FOLLOW_UP_FLAG] = False
        llm_hints.update({"status": "unsupported_item", "unsupported_item": unsupported_item})
        metadata["llm_hints"] = llm_hints
        return _result(metadata, tool_calls, shared_memory)

    pending_order = _pending_order(sales_memory)

    if pending_order:
        if sales_hint.action == "checkout_cancel":
            sales_memory.pop("pending_order", None)
            _set_sales_memory(shared_memory, sales_memory)
            metadata[_FOLLOW_UP_FLAG] = True
            llm_hints.update({"status": "pending_checkout_cancelled", "pending_order": pending_order})
            metadata["llm_hints"] = llm_hints
            return _result(metadata, tool_calls, shared_memory)

        address_parts = sales_hint.shipping_address
        if address_parts:
            placement = _place_order_from_pending(
                sales_memory=sales_memory,
                pending_order=pending_order,
                address_parts=address_parts,
                tools=tools,
            )
            if placement.get("tool_call"):
                tool_calls.append(placement["tool_call"])
            _set_sales_memory(shared_memory, sales_memory)
            metadata[_FOLLOW_UP_FLAG] = True
            llm_hints.update(placement["llm_hints"])
            metadata["llm_hints"] = llm_hints
            return _result(metadata, tool_calls, shared_memory)

        metadata[_FOLLOW_UP_FLAG] = True
        llm_hints.update(
            {
                "status": "shipping_address_required",
                "pending_order": pending_order,
            }
        )
        metadata["llm_hints"] = llm_hints
        return _result(metadata, tool_calls, shared_memory)

    if intent == "order_cancellation" or sales_hint.action == "order_cancellation":
        cancellation = _cancel_order_response(
            sales_memory=sales_memory,
            tools=tools,
            hinted_reference=sales_hint.order_reference,
        )
        if cancellation.get("tool_call"):
            tool_calls.append(cancellation["tool_call"])
        _set_sales_memory(shared_memory, sales_memory)
        metadata[_FOLLOW_UP_FLAG] = True
        llm_hints.update(cancellation["llm_hints"])
        metadata["llm_hints"] = llm_hints
        return _result(metadata, tool_calls, shared_memory)

    if intent == "product_comparison" or sales_hint.action == "product_comparison":
        comparison = _comparison_payload(message=message, sales_memory=sales_memory)
        _set_sales_memory(shared_memory, sales_memory)
        metadata[_FOLLOW_UP_FLAG] = True
        llm_hints.update(comparison)
        metadata["llm_hints"] = llm_hints
        return _result(metadata, tool_calls, shared_memory)

    if intent == "order_placement" or sales_hint.action == "order_placement":
        product = _resolve_product_for_order(message=message, sales_memory=sales_memory)
        if product is None:
            recommendations = recommend_products(message, limit=3)
            llm_hints.update(
                {
                    "status": "order_product_required",
                    "suggested_products": [_serialize_product(rec.product) for rec in recommendations],
                }
            )
            metadata[_FOLLOW_UP_FLAG] = True
            metadata["llm_hints"] = llm_hints
            return _result(metadata, tool_calls, shared_memory)

        sales_memory["selected_product"] = product.name
        address_parts = sales_hint.shipping_address
        if address_parts:
            direct_place = _place_order_direct(product=product, address_parts=address_parts, sales_memory=sales_memory, tools=tools)
            if direct_place.get("tool_call"):
                tool_calls.append(direct_place["tool_call"])
            _set_sales_memory(shared_memory, sales_memory)
            metadata[_FOLLOW_UP_FLAG] = True
            llm_hints.update(direct_place["llm_hints"])
            metadata["llm_hints"] = llm_hints
            return _result(metadata, tool_calls, shared_memory)

        sales_memory["pending_order"] = {"product_name": product.name}
        _set_sales_memory(shared_memory, sales_memory)
        metadata[_FOLLOW_UP_FLAG] = True
        llm_hints.update({"status": "shipping_address_required", "pending_order": sales_memory["pending_order"]})
        metadata["llm_hints"] = llm_hints
        return _result(metadata, tool_calls, shared_memory)

    recommendations = recommend_products(message, limit=3)
    if recommendations:
        names = [rec.product.name for rec in recommendations]
        serialized_products = [_serialize_product(rec.product) for rec in recommendations]
    else:
        fallback_products = list(list_catalog_products())[:3]
        names = [product.name for product in fallback_products]
        serialized_products = [_serialize_product(product) for product in fallback_products]

    if names:
        sales_memory["last_recommendations"] = names
        sales_memory["selected_product"] = names[0]
    _set_sales_memory(shared_memory, sales_memory)
    metadata[_FOLLOW_UP_FLAG] = True
    llm_hints.update(
        {
            "status": "recommendations",
            "recommended_products": serialized_products,
            "upsell_context": intent == "warranty_replacement_upsell",
        }
    )
    metadata["llm_hints"] = llm_hints
    return _result(metadata, tool_calls, shared_memory)


def is_sales_follow_up(
    state: dict[str, Any],
    latest_message: str,
    sales_hint_classifier: SalesHintClassifier | None = None,
) -> bool:
    metadata = state.get("metadata", {})
    if not metadata.get(_FOLLOW_UP_FLAG):
        return False
    classifier = sales_hint_classifier or NoopSalesHintClassifier()
    decision = classifier.classify(
        latest_user_message=latest_message,
        intent=str(state.get("intent") or "sales_general"),
        state=state,
    )
    return not decision.switch_to_other_support


def _result(metadata: dict[str, Any], tool_calls: list[dict[str, Any]], shared_memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "response": "",
        "metadata": metadata,
        "tool_calls": tool_calls,
        "shared_memory": shared_memory,
    }


def _comparison_payload(*, message: str, sales_memory: dict[str, Any]) -> dict[str, Any]:
    products = find_products_in_text(message)
    if len(products) < 2:
        recents = _recent_products(sales_memory)
        products = (products + recents)[:2]

    if len(products) < 2:
        return {"status": "comparison_requires_two_products", "available_products": [p.name for p in _recent_products(sales_memory)]}

    left, right = products[0], products[1]
    recommendation = left if left.price <= right.price else right
    sales_memory["last_compared"] = [left.name, right.name]
    sales_memory["selected_product"] = recommendation.name
    return {
        "status": "comparison_ready",
        "left_product": _serialize_product(left),
        "right_product": _serialize_product(right),
        "recommended_product": recommendation.name,
    }


def _place_order_from_pending(
    *,
    sales_memory: dict[str, Any],
    pending_order: dict[str, Any],
    address_parts: dict[str, str],
    tools: ToolRegistry,
) -> dict[str, Any]:
    product_name = str(pending_order.get("product_name") or "")
    if not product_name:
        sales_memory.pop("pending_order", None)
        return {"llm_hints": {"status": "order_product_required"}}

    tool_call = _invoke_tool(
        tools=tools,
        tool_name="place_mock_order",
        args={"product_name": product_name, "shipping_address": address_parts},
    )
    sales_memory.pop("pending_order", None)
    if tool_call["status"] == "tool_error":
        return {"tool_call": tool_call, "llm_hints": {"status": "order_placement_tool_error", "product_name": product_name}}

    _remember_order(
        sales_memory=sales_memory,
        order={
            "reference_id": tool_call.get("reference_id"),
            "product_name": product_name,
            "shipping_address": address_parts,
            "status": "placed",
        },
    )
    sales_memory["last_order_reference"] = tool_call.get("reference_id")
    sales_memory["last_shipping_address_parts"] = address_parts
    return {
        "tool_call": tool_call,
        "llm_hints": {
            "status": "order_placed",
            "product_name": product_name,
            "reference_id": tool_call.get("reference_id"),
            "shipping_address": address_parts,
        },
    }


def _place_order_direct(
    *,
    product: Product,
    address_parts: dict[str, str],
    sales_memory: dict[str, Any],
    tools: ToolRegistry,
) -> dict[str, Any]:
    tool_call = _invoke_tool(
        tools=tools,
        tool_name="place_mock_order",
        args={"product_name": product.name, "shipping_address": address_parts},
    )
    if tool_call["status"] == "tool_error":
        return {"tool_call": tool_call, "llm_hints": {"status": "order_placement_tool_error", "product_name": product.name}}

    _remember_order(
        sales_memory=sales_memory,
        order={
            "reference_id": tool_call.get("reference_id"),
            "product_name": product.name,
            "shipping_address": address_parts,
            "status": "placed",
        },
    )
    sales_memory["last_order_reference"] = tool_call.get("reference_id")
    sales_memory["last_shipping_address_parts"] = address_parts
    sales_memory.pop("pending_order", None)
    return {
        "tool_call": tool_call,
        "llm_hints": {
            "status": "order_placed",
            "product_name": product.name,
            "reference_id": tool_call.get("reference_id"),
            "shipping_address": address_parts,
        },
    }


def _cancel_order_response(
    *,
    sales_memory: dict[str, Any],
    tools: ToolRegistry,
    hinted_reference: str = "",
) -> dict[str, Any]:
    reference_id = str(hinted_reference or "").strip() or str(sales_memory.get("last_order_reference") or "")
    if not reference_id:
        orders = _order_history(sales_memory)
        if orders:
            reference_id = str(orders[-1].get("reference_id") or "")

    if not reference_id:
        return {"llm_hints": {"status": "order_cancellation_reference_required"}}

    tool_call = _invoke_tool(
        tools=tools,
        tool_name="cancel_mock_order",
        args={"reference_id": reference_id},
    )
    if tool_call["status"] != "tool_error":
        _mark_order_cancelled(sales_memory=sales_memory, reference_id=reference_id)
    return {
        "tool_call": tool_call,
        "llm_hints": {
            "status": "order_cancelled" if tool_call["status"] != "tool_error" else "order_cancellation_tool_error",
            "reference_id": reference_id,
        },
    }


def _resolve_product_for_order(*, message: str, sales_memory: dict[str, Any]) -> Product | None:
    direct = find_products_in_text(message)
    if direct:
        return direct[0]

    selected_name = str(sales_memory.get("selected_product") or "").strip()
    if selected_name and any(token in message.lower() for token in ("this", "that", "it", "chosen", "selected")):
        selected = get_product_by_name(selected_name)
        if selected:
            return selected

    recs = recommend_products(message, limit=1)
    if recs:
        return recs[0].product

    recent = _recent_products(sales_memory)
    return recent[0] if recent else None


def _sales_memory(shared_memory: dict[str, Any]) -> dict[str, Any]:
    raw_memory = shared_memory.get("sales_support")
    if isinstance(raw_memory, dict):
        return dict(raw_memory)
    return {}


def _set_sales_memory(shared_memory: dict[str, Any], sales_memory: dict[str, Any]) -> None:
    if sales_memory:
        shared_memory["sales_support"] = sales_memory
    else:
        shared_memory.pop("sales_support", None)


def _recent_products(sales_memory: dict[str, Any]) -> list[Product]:
    names = sales_memory.get("last_recommendations", [])
    if not isinstance(names, list):
        return []
    products: list[Product] = []
    for name in names:
        if not isinstance(name, str):
            continue
        product = get_product_by_name(name)
        if product:
            products.append(product)
    return products


def _pending_order(sales_memory: dict[str, Any]) -> dict[str, Any] | None:
    raw_pending = sales_memory.get("pending_order")
    if isinstance(raw_pending, dict):
        return dict(raw_pending)
    return None


def _order_history(sales_memory: dict[str, Any]) -> list[dict[str, Any]]:
    raw_orders = sales_memory.get("orders", [])
    if not isinstance(raw_orders, list):
        return []
    orders: list[dict[str, Any]] = []
    for item in raw_orders:
        if isinstance(item, dict):
            orders.append(dict(item))
    return orders


def _remember_order(*, sales_memory: dict[str, Any], order: dict[str, Any]) -> None:
    orders = _order_history(sales_memory)
    orders.append(order)
    sales_memory["orders"] = orders


def _mark_order_cancelled(*, sales_memory: dict[str, Any], reference_id: str) -> None:
    orders = _order_history(sales_memory)
    for order in orders:
        if str(order.get("reference_id", "")).upper() == reference_id.upper():
            order["status"] = "cancelled"
    sales_memory["orders"] = orders
    sales_memory["last_order_reference"] = reference_id


def _invoke_tool(*, tools: ToolRegistry, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = tools.invoke(tool_name, args)
        return {
            "tool_name": tool_name,
            "status": result.get("status", "mock_created"),
            "reference_id": result.get("reference_id"),
        }
    except Exception:
        return {"tool_name": tool_name, "status": "tool_error"}


def _serialize_product(product: Product) -> dict[str, Any]:
    return {
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "summary": product.summary,
        "features": list(product.features),
    }


def _serialize_sales_hint(decision: SalesHintDecision) -> dict[str, Any]:
    return {
        "action": decision.action,
        "confidence": decision.confidence,
        "shipping_address": decision.shipping_address,
        "order_reference": decision.order_reference,
        "switch_to_other_support": decision.switch_to_other_support,
    }
