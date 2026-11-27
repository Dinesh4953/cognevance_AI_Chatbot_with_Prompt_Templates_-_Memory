"""Core orchestration combining prompt templates, memory, guardrails, and output validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from prompts.system_prompts import (
    NOVACLOUD_POLICY_KNOWLEDGE,
    SYSTEM_PROMPT_V1_BASELINE,
    SYSTEM_PROMPT_V2_REFINED,
)
from src.guardrails import GuardrailEngine
from src.llm_client import ChatbotLLMClient
from src.memory import ConversationMemory
from src.prompt_templates import TemplateRegistry
from src.schemas import (
    SupportTicketOutput,
    validate_markdown_table,
    validate_ticket_json,
)

DEFAULT_TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "templates.json"


@dataclass
class ChatbotTurnResult:
    """Structured result returned for every user message."""

    reply_text: str
    mode: str
    guardrail_action: str
    guardrail_reason: str
    pii_detected: list[str]
    template_used: str
    structured_valid: bool | None = None
    validated_ticket: SupportTicketOutput | None = None
    validated_table: tuple[list[str], list[list[str]]] | None = None
    validation_error: str | None = None
    latency_ms: float = 0.0
    provider: str = "demo"
    is_demo: bool = True


class NovaCloudChatbot:
    """Stateful domain chatbot with prompt templates, memory, guardrails, and schema validation."""

    def __init__(
        self,
        templates_path: str | Path = DEFAULT_TEMPLATES_PATH,
        api_key: str | None = None,
        window_size: int = 6,
        prompt_version: str = "v2",
    ) -> None:
        self.registry = TemplateRegistry(templates_path)
        self.memory = ConversationMemory(window_size=window_size)
        self.guardrails = GuardrailEngine()
        self.client = ChatbotLLMClient(api_key=api_key)
        self.prompt_version = prompt_version

    def _select_template_id(self, user_input: str, requested_mode: str) -> str:
        if requested_mode in {"structured_ticket_json", "policy_comparison_table", "troubleshooting_steps"}:
            return requested_mode
        lower = user_input.lower()
        if any(w in lower for w in ("json", "create ticket", "raise a ticket", "open a ticket", "log ticket")):
            return "structured_ticket_json"
        if any(w in lower for w in ("table", "compare", "comparison", "sla matrix")):
            return "policy_comparison_table"
        if any(w in lower for w in ("troubleshoot", "steps to fix", "checklist")):
            return "troubleshooting_steps"
        return "conversational_qa"

    def chat(
        self,
        user_input: str,
        mode: str = "auto",
        provider: str = "groq",
        model: str = "openai/gpt-oss-20b",
        temperature: float = 0.2,
    ) -> ChatbotTurnResult:
        """Process one user turn through guardrails -> memory -> templates -> LLM -> validation."""
        has_context = len(self.memory.turns) > 0
        decision = self.guardrails.evaluate_input(user_input, has_prior_context=has_context)

        if self.prompt_version == "v2" and decision.action != "allow":
            self.memory.add_turn("user", decision.user_message if decision.pii_detected else user_input, mode=mode)
            self.memory.add_turn("assistant", decision.user_message, mode=mode, guardrail_triggered=decision.action)
            return ChatbotTurnResult(
                reply_text=decision.user_message,
                mode=mode,
                guardrail_action=decision.action,
                guardrail_reason=decision.reason,
                pii_detected=decision.pii_detected,
                template_used="guardrail_response",
            )

        clean_input = decision.user_message if decision.action == "allow" else user_input
        template_id = self._select_template_id(clean_input, mode)
        self.memory.add_turn("user", clean_input, mode=template_id)

        if self.prompt_version == "v1":
            system_prompt = SYSTEM_PROMPT_V1_BASELINE
            rendered_prompt = clean_input
            template_id = "v1_raw_baseline"
        else:
            system_prompt = SYSTEM_PROMPT_V2_REFINED
            if template_id == "conversational_qa":
                rendered_prompt = self.registry.render(
                    "conversational_qa",
                    policy_context=NOVACLOUD_POLICY_KNOWLEDGE,
                    conversation_summary=self.memory.rolling_summary,
                    recent_history=self.memory.format_recent_history(),
                    user_profile=self.memory.profile_string(),
                    user_query=clean_input,
                )
            elif template_id == "structured_ticket_json":
                rendered_prompt = self.registry.render(
                    "structured_ticket_json",
                    policy_context=NOVACLOUD_POLICY_KNOWLEDGE,
                    conversation_summary=self.memory.rolling_summary,
                    user_profile=self.memory.profile_string(),
                    user_query=clean_input,
                )
            elif template_id == "policy_comparison_table":
                rendered_prompt = self.registry.render(
                    "policy_comparison_table",
                    policy_context=NOVACLOUD_POLICY_KNOWLEDGE,
                    user_query=clean_input,
                )
            else:
                rendered_prompt = self.registry.render(
                    "troubleshooting_steps",
                    device_os=self.memory.user_profile["device_os"],
                    conversation_summary=self.memory.rolling_summary,
                    user_query=clean_input,
                )

        gen = self.client.generate(
            system_prompt=system_prompt,
            user_prompt=rendered_prompt,
            provider=provider,
            model=model,
            temperature=temperature,
            mode=template_id,
            memory_context=self.memory.profile_string(),
        )
        safe_reply, out_pii = self.guardrails.redact_pii(gen.text)
        pii_all = sorted(set(decision.pii_detected + out_pii))

        structured_valid: bool | None = None
        ticket_obj: SupportTicketOutput | None = None
        table_obj: tuple[list[str], list[list[str]]] | None = None
        val_err: str | None = None

        if template_id == "structured_ticket_json":
            ok, ticket_obj, val_err = validate_ticket_json(safe_reply)
            structured_valid = ok
        elif template_id == "policy_comparison_table":
            ok, headers, rows, val_err = validate_markdown_table(safe_reply)
            structured_valid = ok
            if ok:
                table_obj = (headers, rows)

        self.memory.add_turn("assistant", safe_reply, mode=template_id)

        return ChatbotTurnResult(
            reply_text=safe_reply,
            mode=template_id,
            guardrail_action=decision.action,
            guardrail_reason=decision.reason,
            pii_detected=pii_all,
            template_used=template_id,
            structured_valid=structured_valid,
            validated_ticket=ticket_obj,
            validated_table=table_obj,
            validation_error=val_err,
            latency_ms=gen.latency_ms,
            provider=gen.provider,
            is_demo=gen.is_demo,
        )
