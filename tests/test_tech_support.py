from __future__ import annotations

from pathlib import Path

from app.agents.tech_support import handle_tech_support
from app.services.knowledge_base import KnowledgeBaseService


def _kb() -> KnowledgeBaseService:
    project_root = Path(__file__).resolve().parents[1]
    return KnowledgeBaseService(project_root / "data" / "wiki.txt")


def _state(message: str) -> dict:
    return {
        "latest_user_message": message,
        "metadata": {},
    }


def test_answers_camera_question_from_wiki() -> None:
    response = handle_tech_support(_state("My camera will not power on"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert "camera" in response.lower()
    assert "battery" in response.lower()


def test_answers_router_question_from_wiki() -> None:
    response = handle_tech_support(_state("My router keeps disconnecting"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert "router" in response.lower()
    assert "overheating" in response.lower()


def test_generic_wifi_issue_prefers_router_or_modem_guidance() -> None:
    response = handle_tech_support(_state("My wifi is not working"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert ("router" in response.lower()) or ("modem" in response.lower())
    assert "camera" not in response.lower()


def test_answers_wifi_modem_question_from_wiki() -> None:
    response = handle_tech_support(_state("My modem loses sync frequently"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert "modem" in response.lower()
    assert "event logs" in response.lower()


def test_answers_cpu_question_from_wiki() -> None:
    response = handle_tech_support(_state("My cpu temperature is too high"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert "cpu" in response.lower()
    assert ("thermal paste" in response.lower()) or ("heatsinks" in response.lower())


def test_answers_mobile_question_from_wiki() -> None:
    response = handle_tech_support(_state("My phone battery drains quickly"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert "sorry, we dont deal with mobile phone right now." in response.lower()


def test_returns_fallback_for_unsupported_product() -> None:
    response = handle_tech_support(_state("My laptop fan is too loud"), _kb())["response"]
    assert response.startswith("Technical Support Agent:")
    assert "sorry, we dont deal with laptop right now." in response.lower()


def test_answers_based_on_user_tried_steps_follow_up() -> None:
    state = {
        "latest_user_message": "I restarted it and changed router position",
        "metadata": {"awaiting_tech_attempts": True, "last_tech_section": "router"},
    }
    response = handle_tech_support(state, _kb())["response"]

    assert response.startswith("Technical Support Agent:")
    assert "since you've already tried restarting the router" in response.lower()
    assert "next try" in response.lower()


def test_ambiguous_overheating_follow_up_stays_in_router_section() -> None:
    state = {
        "latest_user_message": "it is overheating now",
        "metadata": {"awaiting_tech_attempts": False, "last_tech_section": "router"},
    }

    result = handle_tech_support(state, _kb())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "kb_match"
    assert hints["section"] == "router"
    assert "router" in hints["knowledge_text"].lower()


def test_explicit_camera_message_overrides_router_context() -> None:
    state = {
        "latest_user_message": "my camera is overheating now",
        "metadata": {"awaiting_tech_attempts": False, "last_tech_section": "router"},
    }

    result = handle_tech_support(state, _kb())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "kb_match"
    assert hints["section"] == "camera"
    assert "camera" in hints["knowledge_text"].lower()


def test_ambiguous_wifi_follow_up_stays_in_camera_section() -> None:
    state = {
        "latest_user_message": "it still cannot connect to wifi",
        "metadata": {"awaiting_tech_attempts": False, "last_tech_section": "camera"},
    }

    result = handle_tech_support(state, _kb())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "kb_match"
    assert hints["section"] == "camera"
    assert "camera" in hints["knowledge_text"].lower()


def test_explicit_modem_message_switches_from_camera_context() -> None:
    state = {
        "latest_user_message": "my modem still cannot connect to wifi",
        "metadata": {"awaiting_tech_attempts": False, "last_tech_section": "camera"},
    }

    result = handle_tech_support(state, _kb())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "kb_match"
    assert hints["section"] == "wifi_modem"
    assert "modem" in hints["knowledge_text"].lower()
