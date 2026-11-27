"""Pydantic schemas and validators for structured JSON and Markdown table outputs."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class TicketCategory(str, Enum):
    IT_ACCESS = "IT_ACCESS"
    IT_HARDWARE = "IT_HARDWARE"
    IT_NETWORK = "IT_NETWORK"
    HR_LEAVE = "HR_LEAVE"
    HR_EXPENSE = "HR_EXPENSE"
    ONBOARDING = "ONBOARDING"


class TicketPriority(str, Enum):
    P1_CRITICAL = "P1_CRITICAL"
    P2_HIGH = "P2_HIGH"
    P3_NORMAL = "P3_NORMAL"


class SupportTicketOutput(BaseModel):
    """Validated JSON schema for structured IT/HR helpdesk tickets."""

    ticket_id: str = Field(..., min_length=4, max_length=20)
    category: TicketCategory
    priority: TicketPriority
    summary: str = Field(..., min_length=8, max_length=300)
    action_steps: list[str] = Field(..., min_length=1, max_length=8)
    escalation_needed: bool
    sla_target: str = Field(..., min_length=2, max_length=80)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("ticket_id")
    @classmethod
    def check_ticket_prefix(cls, val: str) -> str:
        cleaned = val.strip().upper()
        if not cleaned.startswith("NC-"):
            cleaned = f"NC-{cleaned.lstrip('#')}"
        return cleaned


def extract_json_block(raw_text: str) -> str:
    """Extract JSON payload from raw text or ```json fenced code blocks."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    brace_match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
    if brace_match:
        return brace_match.group(1).strip()
    return raw_text.strip()


def validate_ticket_json(raw_text: str) -> tuple[bool, SupportTicketOutput | None, str | None]:
    """Parse and Pydantic-validate a structured ticket JSON response."""
    candidate = extract_json_block(raw_text)
    try:
        parsed: Any = json.loads(candidate)
        ticket = SupportTicketOutput.model_validate(parsed)
        return True, ticket, None
    except (json.JSONDecodeError, ValidationError) as exc:
        return False, None, str(exc)


def validate_markdown_table(raw_text: str) -> tuple[bool, list[str], list[list[str]], str | None]:
    """Validate that the output contains a well-formed Markdown pipe table."""
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 3:
        return False, [], [], "Response must contain header, separator, and at least 1 data row."

    def split_row(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip("|").split("|")]

    headers = split_row(lines[0])
    separator = split_row(lines[1])
    if len(headers) < 2:
        return False, [], [], "Markdown table must have at least 2 columns."
    if not all(re.fullmatch(r":?-{2,}:?", cell) for cell in separator):
        return False, [], [], "Second row must be a valid Markdown separator (e.g., |---|---|)."

    rows: list[list[str]] = []
    for row_line in lines[2:]:
        cells = split_row(row_line)
        if len(cells) != len(headers):
            return (
                False,
                headers,
                rows,
                f"Row column count ({len(cells)}) does not match headers ({len(headers)}).",
            )
        rows.append(cells)

    if not rows:
        return False, headers, [], "Markdown table has no data rows."
    return True, headers, rows, None
