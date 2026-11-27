"""LLM client for NovaCloud Chatbot supporting Groq, Gemini, OpenAI, and Demo fallback."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = {
    "groq": ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"],
    "gemini": ["gemini-2.0-flash", "gemini-1.5-flash"],
    "openai": ["gpt-4o-mini", "gpt-4o"],
    "demo": ["demo-helpdesk-v2"],
}


@dataclass
class ChatGeneration:
    text: str
    provider: str
    model: str
    latency_ms: float
    is_demo: bool = False
    error: str | None = None


def _smart_demo_reply(prompt: str, mode: str, memory_context: str = "") -> str:
    """Deterministic domain-aware demo fallback when running offline or without API keys."""
    query_match = re.search(
        r"(?:Current User Message|User Request|Reported Issue):\s*(.+?)(?:\n\n|\Z)",
        prompt,
        re.DOTALL,
    )
    query_only = (query_match.group(1) if query_match else prompt).lower()
    if mode == "structured_ticket_json":
        cat = "IT_NETWORK" if "vpn" in query_only else (
            "IT_ACCESS" if any(k in query_only for k in ("mfa", "okta", "access", "password")) else (
                "HR_EXPENSE" if "expense" in query_only else (
                    "HR_LEAVE" if any(k in query_only for k in ("pto", "leave", "sick")) else "IT_HARDWARE"
                )
            )
        )
        prio = "P1_CRITICAL" if any(k in query_only for k in ("outage", "locked", "vpn", "down")) else "P2_HIGH"
        sla = "15 minutes" if prio == "P1_CRITICAL" else "4 hours"
        return (
            "{\n"
            '  "ticket_id": "NC-4092",\n'
            f'  "category": "{cat}",\n'
            f'  "priority": "{prio}",\n'
            '  "summary": "Employee helpdesk request triaged via NovaCloud structured workflow.",\n'
            '  "action_steps": [\n'
            '    "Verify employee identity and device/OS context from session profile",\n'
            '    "Apply standard NovaCloud troubleshooting or policy verification checklist",\n'
            '    "Escalate to Tier-2 IT/HR resolver if unresolved within SLA"\n'
            "  ],\n"
            f'  "escalation_needed": {str(prio == "P1_CRITICAL").lower()},\n'
            f'  "sla_target": "{sla}",\n'
            '  "confidence": 0.91\n'
            "}"
        )
    if mode == "policy_comparison_table":
        return (
            "| Policy / Tier | Allowance / SLA | Key Condition |\n"
            "|---|---|---|\n"
            "| Annual PTO | 20 days/year | Up to 5 days carry over until March 31 |\n"
            "| Sick Leave | 10 days/year | Doctor's note required for >3 consecutive days |\n"
            "| Home-Office Stipend | $600 setup + $75/mo | Eligible after 30 days of employment |\n"
            "| P1 IT Outage SLA | 15 minutes response | Auth/VPN downtime affecting work |\n\n"
            "Takeaway: Submit HR exceptions via Workday and urgent P1 IT blockers to the Service Desk."
        )

    # Check for name / device / dept recall in memory_context
    name_m = re.search(r"Name=([A-Za-z]+)", memory_context)
    dept_m = re.search(r"Department=([A-Za-z]+)", memory_context)
    dev_m = re.search(r"Device/OS=([A-Za-z0-9 ]+)", memory_context)
    name = name_m.group(1) if name_m else "there"
    dept = dept_m.group(1) if dept_m else "General"
    dev = dev_m.group(1) if dev_m and "Unknown" not in dev_m.group(1) else "your device"

    if "what laptop" in query_only or "what os" in query_only or "department you have" in query_only:
        return f"Hi {name}, your profile lists Department **{dept}** and Device/OS **{dev}**."
    if "stipend" in query_only or "home-office" in query_only:
        return (
            "NovaCloud provides a **$600 one-time home-office setup stipend** after 30 days of "
            "employment, plus **$75/month** for internet reimbursement via Expensify."
        )
    if "sick" in query_only:
        return (
            f"Hi {name}, employees receive **10 paid sick days/year**. A doctor's note is only "
            "required for **more than 3 consecutive days**—so 2 sick days do not require one."
        )
    if "carryover" in query_only or "pto" in query_only:
        return (
            f"Hi {name}, NovaCloud employees accrue **20 PTO days/year**. Up to **5 unused days** "
            "can carry over into the next calendar year and expire on **March 31**."
        )
    if "mfa" in query_only or "okta" in query_only:
        return (
            f"Got it, {name}. For an **Okta MFA reset** on {dev}, IT Service Desk issues a temporary "
            "24-hour bypass code after brief **manager approval** (P1/P2 SLA: 15 min – 4 hours)."
        )
    if "vpn" in query_only:
        return (
            f"Hi {name}, let's troubleshoot your VPN issue on **{dev}**:\n"
            "1. Confirm internet connectivity and re-authenticate Okta SSO.\n"
            "2. Restart the WireGuard/GlobalProtect VPN client and switch to the backup gateway.\n"
            "3. If error persists, open a P1 ticket (15-min SLA) with your OS version and error code."
        )
    return (
        f"Hi {name}, I've noted your request for {dev} ({dept}). Based on NovaCloud IT & HR guidelines, "
        "please share any ticket/error details or switch output mode to **Structured JSON Ticket** "
        "to generate a validated support ticket."
    )


class ChatbotLLMClient:
    """Unified multi-provider client for the NovaCloud Chatbot."""

    def __init__(self, api_key: str | None = None) -> None:
        self.override_api_key = api_key

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: str = "groq",
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        max_tokens: int = 512,
        mode: str = "conversational",
        memory_context: str = "",
    ) -> ChatGeneration:
        start = time.perf_counter()
        prov = provider.lower()

        if prov == "demo":
            txt = _smart_demo_reply(user_prompt, mode=mode, memory_context=memory_context)
            return ChatGeneration(
                text=txt,
                provider="demo",
                model=model,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                is_demo=True,
            )

        try:
            if prov == "groq":
                key = self.override_api_key or os.getenv("GROQ_API_KEY", "")
                if not key:
                    raise ValueError("GROQ_API_KEY not configured")
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=45,
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip()
            elif prov == "openai":
                key = self.override_api_key or os.getenv("OPENAI_API_KEY", "")
                if not key:
                    raise ValueError("OPENAI_API_KEY not configured")
                base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
                resp = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=45,
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip()
            elif prov == "gemini":
                key = self.override_api_key or os.getenv("GEMINI_API_KEY", "")
                if not key:
                    raise ValueError("GEMINI_API_KEY not configured")
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={key}"
                )
                resp = requests.post(
                    url,
                    json={
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
                    },
                    timeout=45,
                )
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                raise ValueError(f"Unsupported provider: {prov}")

            return ChatGeneration(
                text=text,
                provider=prov,
                model=model,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                is_demo=False,
            )
        except Exception as exc:  # noqa: BLE001
            txt = _smart_demo_reply(user_prompt, mode=mode, memory_context=memory_context)
            return ChatGeneration(
                text=txt,
                provider=f"{prov} (fallback->demo)",
                model=model,
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
                is_demo=True,
                error=str(exc),
            )
