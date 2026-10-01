from __future__ import annotations

from pathlib import Path

from app.agents.tech_support import handle_tech_support
from app.services.knowledge_base import KnowledgeBaseService


def _kb() -> KnowledgeBaseService:
    project_root = Path(__file__).resolve().parents[1]
    return KnowledgeBaseService(project_root / "data" / "wiki.txt")


def test_non_resolvable_issue_sets_upsell_hints() -> None:
    state = {
        "latest_user_message": "my camera is physically damaged and cannot be repaired",
        "metadata": {"last_tech_section": "camera"},
    }

    result = handle_tech_support(state, _kb())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "non_resolvable_issue"
    assert hints["section"] == "camera"
    assert hints["escalate_to_sales"] is True
    assert hints["upsell_context"] is True
    assert hints["upsell_reason"] == "issue_not_resolvable"
    assert isinstance(hints["recommended_products"], list)
    assert hints["recommended_products"]
    assert all("name" in product and "price" in product for product in hints["recommended_products"])
    assert all(product.get("category") == "camera" for product in hints["recommended_products"])


def test_troubleshooting_exhausted_sets_upsell_hints() -> None:
    state = {
        "latest_user_message": "I restarted reset firmware and moved router location to fix interference",
        "metadata": {"awaiting_tech_attempts": True, "last_tech_section": "router"},
    }

    result = handle_tech_support(state, _kb())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "troubleshooting_exhausted"
    assert hints["section"] == "router"
    assert hints["escalate_to_sales"] is True
    assert hints["upsell_context"] is True
    assert hints["upsell_reason"] == "troubleshooting_exhausted"
    assert isinstance(hints["recommended_products"], list)
    assert hints["recommended_products"]
    assert all("name" in product and "price" in product for product in hints["recommended_products"])
    assert all(product.get("category") == "router" for product in hints["recommended_products"])
