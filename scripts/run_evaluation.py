"""Evaluate Prompt v1 (baseline) vs Prompt v2 (templates + memory + guardrails + schema) across 24 test cases."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot import NovaCloudChatbot
from src.llm_client import DEFAULT_MODELS


def evaluate_version(prompt_version: str, provider: str, model: str, cases: list[dict]) -> dict:
    passed = 0
    json_checked = 0
    json_valid = 0
    table_checked = 0
    table_valid = 0
    guardrail_checked = 0
    guardrail_matched = 0
    rows = []

    for tc in cases:
        bot = NovaCloudChatbot(prompt_version=prompt_version)
        res = None
        for turn in tc["turns"]:
            res = bot.chat(turn, mode=tc["mode"], provider=provider, model=model, temperature=0.1)
        assert res is not None

        checks_ok = True
        notes = []

        if tc["expected_guardrail"] != "allow":
            guardrail_checked += 1
            if res.guardrail_action == tc["expected_guardrail"]:
                guardrail_matched += 1
            else:
                checks_ok = False
                notes.append(f"guardrail={res.guardrail_action}!=expected({tc['expected_guardrail']})")

        if tc.get("validate_json"):
            json_checked += 1
            if res.structured_valid:
                json_valid += 1
            else:
                checks_ok = False
                notes.append("invalid_json")

        if tc.get("validate_table"):
            table_checked += 1
            if res.structured_valid:
                table_valid += 1
            else:
                checks_ok = False
                notes.append("invalid_table")

        if tc.get("expect_pii_redacted"):
            if not res.pii_detected:
                checks_ok = False
                notes.append("pii_not_detected")

        if tc.get("must_contain_any"):
            low = res.reply_text.lower()
            if not any(k.lower() in low for k in tc["must_contain_any"]):
                checks_ok = False
                notes.append("missing_expected_fact")

        if checks_ok:
            passed += 1

        rows.append(
            {
                "id": tc["id"],
                "category": tc["category"],
                "passed": checks_ok,
                "guardrail": res.guardrail_action,
                "structured_valid": res.structured_valid,
                "latency_ms": res.latency_ms,
                "notes": "; ".join(notes) if notes else "OK",
                "reply_preview": res.reply_text.replace("\n", " ")[:140],
            }
        )

    total = len(cases)
    return {
        "prompt_version": prompt_version,
        "provider": provider,
        "model": model,
        "total_cases": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1),
        "json_valid_pct": round(100 * json_valid / max(1, json_checked), 1),
        "table_valid_pct": round(100 * table_valid / max(1, table_checked), 1),
        "guardrail_accuracy_pct": round(100 * guardrail_matched / max(1, guardrail_checked), 1),
        "details": rows,
    }


def main() -> None:
    cases = json.loads((ROOT / "tests" / "test_cases.json").read_text(encoding="utf-8"))
    provider = "groq" if os.getenv("GROQ_API_KEY") else "demo"
    model = DEFAULT_MODELS[provider][0]

    v1 = evaluate_version("v1", provider, model, cases)
    v2 = evaluate_version("v2", provider, model, cases)

    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval_results.json").write_text(
        json.dumps({"v1_baseline": v1, "v2_refined": v2}, indent=2),
        encoding="utf-8",
    )

    md_lines = [
        "# Prompt Refinement & 24-Test-Case Evaluation Report",
        "",
        f"- **Provider / Model:** `{provider}` / `{model}`",
        f"- **Total Test Cases:** {len(cases)} (Domain Q&A, Multi-Turn Memory, Structured JSON, Markdown Tables, Out-of-Scope, Unsafe/Injection, Ambiguity, PII)",
        "",
        "## v1 Baseline vs v2 Refined Comparison",
        "",
        "| Metric | v1 Baseline (Raw Prompt) | v2 Refined (Templates + Memory + Guardrails + Schema) | Improvement |",
        "|---|---:|---:|---:|",
        f"| Overall Pass Rate | {v1['pass_rate_pct']}% ({v1['passed']}/{v1['total_cases']}) | {v2['pass_rate_pct']}% ({v2['passed']}/{v2['total_cases']}) | +{v2['pass_rate_pct'] - v1['pass_rate_pct']:.1f}% |",
        f"| Structured JSON Validity | {v1['json_valid_pct']}% | {v2['json_valid_pct']}% | +{v2['json_valid_pct'] - v1['json_valid_pct']:.1f}% |",
        f"| Markdown Table Validity | {v1['table_valid_pct']}% | {v2['table_valid_pct']}% | +{v2['table_valid_pct'] - v1['table_valid_pct']:.1f}% |",
        f"| Guardrail Accuracy | {v1['guardrail_accuracy_pct']}% | {v2['guardrail_accuracy_pct']}% | +{v2['guardrail_accuracy_pct'] - v1['guardrail_accuracy_pct']:.1f}% |",
        "",
        "## Iterative Prompt Refinements Applied",
        "1. **Persona & Grounding (`SYSTEM_PROMPT_V2_REFINED`)**: Added explicit NovaCloud policy reference block (`NOVACLOUD_POLICY_KNOWLEDGE`), eliminating policy-number hallucinations.",
        "2. **Schema-First JSON Template**: Added exact enum choices (`IT_ACCESS`, `P1_CRITICAL`, etc.) and explicit instruction to emit raw JSON without prose wrappers, validated via Pydantic `SupportTicketOutput`.",
        "3. **Multi-Turn Memory Injection**: Added sliding window (`window_size=6`) + regex entity profile + rolling summary so follow-up turns recall user name, department, and OS.",
        "4. **Pre-LLM Guardrails**: Added deterministic unsafe/injection detection, out-of-scope deflection, PII redaction, and ambiguity clarification prompts.",
        "",
        "## Per-Case v2 Results",
        "",
        "| ID | Category | Passed | Guardrail | Latency (ms) | Notes |",
        "|---|---|---:|---|---:|---|",
    ]
    for r in v2["details"]:
        md_lines.append(
            f"| {r['id']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | `{r['guardrail']}` | {r['latency_ms']:.1f} | {r['notes']} |"
        )

    (out_dir / "refinement_report.md").write_text("\n".join(md_lines), encoding="utf-8")
    print(f"v1 pass rate: {v1['pass_rate_pct']}% | v2 pass rate: {v2['pass_rate_pct']}%")


if __name__ == "__main__":
    main()
