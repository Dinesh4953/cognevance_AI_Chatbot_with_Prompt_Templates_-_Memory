"""Pytest suite for NovaCloud Chatbot templates, memory, schemas, guardrails, and 24 test cases."""

from __future__ import annotations

import json
from pathlib import Path

from src.chatbot import NovaCloudChatbot
from src.memory import ConversationMemory
from src.prompt_templates import TemplateRegistry
from src.schemas import validate_markdown_table, validate_ticket_json

ROOT = Path(__file__).resolve().parent.parent


def test_template_registry_renders_and_validates_missing_vars():
    reg = TemplateRegistry(ROOT / "prompts" / "templates.json")
    assert "conversational_qa" in reg.list_ids()
    rendered = reg.render(
        "clarification_request",
        user_query="help",
        missing_details="OS and service name",
    )
    assert "OS and service name" in rendered

    try:
        reg.render("clarification_request", user_query="help")
        raise AssertionError("Expected ValueError for missing variable")
    except ValueError as exc:
        assert "missing_details" in str(exc)


def test_conversation_memory_sliding_window_and_entity_extraction():
    mem = ConversationMemory(window_size=4)
    mem.add_turn("user", "Hi, my name is Elena in Engineering on macOS.")
    assert mem.user_profile["name"] == "Elena"
    assert mem.user_profile["department"] == "Engineering"
    assert mem.user_profile["device_os"] == "macOS"

    for i in range(6):
        mem.add_turn("user", f"Follow-up turn {i}")
    assert len(mem.turns) == 4
    assert "Elena" in mem.rolling_summary


def test_structured_json_and_table_validators():
    raw_json = """```json
    {
      "ticket_id": "NC-102",
      "category": "IT_NETWORK",
      "priority": "P1_CRITICAL",
      "summary": "Corporate VPN gateway unreachable for macOS users.",
      "action_steps": ["Check Okta session", "Switch gateway"],
      "escalation_needed": true,
      "sla_target": "15 minutes",
      "confidence": 0.94
    }
    ```"""
    ok, ticket, err = validate_ticket_json(raw_json)
    assert ok is True and err is None
    assert ticket is not None and ticket.ticket_id == "NC-102"

    raw_table = "| Policy | Limit | Notes |\n|---|---|---|\n| PTO | 20 days | 5 carryover |"
    t_ok, headers, rows, t_err = validate_markdown_table(raw_table)
    assert t_ok is True and t_err is None
    assert headers == ["Policy", "Limit", "Notes"]
    assert len(rows) == 1


def test_all_24_chatbot_test_cases_in_demo_mode():
    cases = json.loads((ROOT / "tests" / "test_cases.json").read_text(encoding="utf-8"))
    assert len(cases) >= 20

    for tc in cases:
        bot = NovaCloudChatbot(prompt_version="v2")
        res = None
        for turn in tc["turns"]:
            res = bot.chat(turn, mode=tc["mode"], provider="demo", model="demo-helpdesk-v2")
        assert res is not None, tc["id"]
        assert res.guardrail_action == tc["expected_guardrail"], f"{tc['id']}: {res.guardrail_action}"
        if tc.get("validate_json"):
            assert res.structured_valid is True, f"{tc['id']}: {res.validation_error}"
        if tc.get("validate_table"):
            assert res.structured_valid is True, f"{tc['id']}: {res.validation_error}"
        if tc.get("expect_pii_redacted"):
            assert len(res.pii_detected) >= 1, tc["id"]
        if tc.get("must_contain_any"):
            combined = res.reply_text.lower()
            assert any(k.lower() in combined for k in tc["must_contain_any"]), (
                f"{tc['id']} reply={res.reply_text}"
            )
