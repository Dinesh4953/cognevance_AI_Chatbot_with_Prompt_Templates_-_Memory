"""Input and output guardrails for out-of-scope, unsafe, PII, and ambiguous inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GuardrailDecision:
    """Result of evaluating a user message against safety and scope guardrails."""

    action: str  # "allow" | "block_unsafe" | "block_out_of_scope" | "clarify_ambiguous"
    reason: str
    user_message: str
    pii_detected: list[str]


UNSAFE_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"reveal\s+(your\s+)?(system\s+prompt|hidden\s+instructions)",
    r"bypass\s+(security|mfa|authentication|guardrails)",
    r"\b(phishing|ransomware|exploit|keylogger|sql\s*injection\s+payload)\b",
    r"\b(hack|steal|exfiltrate)\b.*\b(password|database|credentials|salary)\b",
    r"\b(self-harm|suicide|bomb|weapon)\b",
]

OUT_OF_SCOPE_PATTERNS = [
    r"\b(stock\s+price|buy\s+crypto|bitcoin|eth|trading\s+advice|invest\s+in)\b",
    r"\b(diagnose|prescription|chest\s+pain|dosage|medical\s+advice)\b",
    r"\b(write\s+a\s+poem|sonnet|astrology|horoscope|movie\s+recommendation)\b",
    r"\b(solve\s+my\s+calculus|physics\s+homework|essay\s+on\s+shakespeare)\b",
    r"\b(recipe\s+for|bake\s+a\s+cake|cricket\s+score|football\s+match)\b",
]

DOMAIN_KEYWORDS = {
    "vpn", "mfa", "okta", "sso", "laptop", "macbook", "windows", "wifi", "network",
    "password", "reset", "access", "jira", "slack", "github", "email", "outlook",
    "pto", "leave", "vacation", "sick", "stipend", "expense", "reimbursement",
    "expensify", "payroll", "w-2", "benefit", "insurance", "onboarding", "ticket",
    "sla", "policy", "hr", "it", "hardware", "software", "printer", "monitor",
    "docker", "ssh", "account", "locked", "approval", "manager", "salary",
}

PII_PATTERNS: list[tuple[str, str, str]] = [
    ("SSN", r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]"),
    ("CREDIT_CARD", r"\b(?:\d[ -]*?){13,16}\b", "[REDACTED-CARD]"),
    ("API_KEY", r"\b(?:sk-|gsk_|AIza)[A-Za-z0-9_\-]{12,}\b", "[REDACTED-KEY]"),
]


class GuardrailEngine:
    """Evaluates user inputs and sanitizes PII in inputs/outputs."""

    def redact_pii(self, text: str) -> tuple[str, list[str]]:
        """Mask sensitive PII/secret patterns and return `(sanitized_text, found_labels)`."""
        found: list[str] = []
        sanitized = text
        for label, pattern, replacement in PII_PATTERNS:
            if re.search(pattern, sanitized):
                found.append(label)
                sanitized = re.sub(pattern, replacement, sanitized)
        return sanitized, found

    def evaluate_input(self, user_input: str, has_prior_context: bool = False) -> GuardrailDecision:
        """Classify user input as allow, block_unsafe, block_out_of_scope, or clarify_ambiguous."""
        cleaned = user_input.strip()
        sanitized, pii_found = self.redact_pii(cleaned)
        lower = sanitized.lower()

        # 1. Unsafe / Prompt Injection check
        for pat in UNSAFE_PATTERNS:
            if re.search(pat, lower):
                return GuardrailDecision(
                    action="block_unsafe",
                    reason="Detected unsafe content, security bypass, or prompt injection attempt.",
                    user_message=(
                        "I cannot assist with bypassing security controls, revealing internal "
                        "instructions, or performing unsafe actions. Please reach out to "
                        "IT Security via official approved channels for legitimate access help."
                    ),
                    pii_detected=pii_found,
                )

        # 2. Out-of-scope check
        for pat in OUT_OF_SCOPE_PATTERNS:
            if re.search(pat, lower):
                return GuardrailDecision(
                    action="block_out_of_scope",
                    reason="Query falls outside NovaCloud IT & HR Helpdesk domain.",
                    user_message=(
                        "That topic is outside my scope as the **NovaCloud IT & HR Helpdesk Assistant**. "
                        "I can help with IT troubleshooting (VPN, MFA, hardware, software access), "
                        "HR policies (PTO, sick leave, expenses, stipends), or creating support tickets."
                    ),
                    pii_detected=pii_found,
                )

        # 3. Ambiguity check (very short / underspecified without domain specifics)
        words = re.findall(r"[a-zA-Z0-9'-]+", lower)
        vague_phrases = {
            "help", "hi", "hello", "issue", "broken", "it broke", "not working",
            "policy", "policy?", "access", "error", "fix this", "stuck", "problem",
        }
        has_domain_term = any(w in DOMAIN_KEYWORDS for w in words)
        if not has_prior_context and (
            lower in vague_phrases
            or (len(words) <= 3 and not has_domain_term)
            or (len(words) <= 4 and "not working" in lower and not has_domain_term)
        ):
            return GuardrailDecision(
                action="clarify_ambiguous",
                reason="Request is too brief or ambiguous to diagnose accurately.",
                user_message=(
                    "I'd be happy to help! To route or troubleshoot your request accurately, "
                    "could you share a few details?\n"
                    "1. Is this an **IT issue** (e.g., VPN, Okta/MFA, hardware, software access) "
                    "or an **HR policy** question (e.g., PTO, expenses, stipends)?\n"
                    "2. What device/OS or portal are you using, and what exact error or blocker do you see?"
                ),
                pii_detected=pii_found,
            )

        return GuardrailDecision(
            action="allow",
            reason="Passed safety, scope, and clarity checks.",
            user_message=sanitized,
            pii_detected=pii_found,
        )
