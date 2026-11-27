"""Multi-turn conversation memory with sliding window and rolling summary."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class ChatTurn:
    """Represents a single user or assistant turn in conversation memory."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mode: str = "conversational"
    guardrail_triggered: str | None = None


class ConversationMemory:
    """Maintains sliding-window turns, user profile entities, and rolling summary."""

    def __init__(self, window_size: int = 6) -> None:
        self.window_size = max(2, window_size)
        self.turns: list[ChatTurn] = []
        self.rolling_summary: str = "No prior conversation yet."
        self.user_profile: dict[str, str] = {
            "name": "Employee",
            "department": "General",
            "device_os": "Unknown",
        }

    def _extract_entities(self, text: str) -> None:
        """Lightweight entity extraction so multi-turn memory tracks key user details."""
        name_match = re.search(r"\b(?:my name is|i am|i'm)\s+([A-Z][a-z]{1,20})\b", text)
        if name_match:
            candidate = name_match.group(1)
            if candidate.lower() not in {"trying", "having", "working", "unable", "locked", "new"}:
                self.user_profile["name"] = candidate

        dept_match = re.search(
            r"\b(?:in|from)\s+(Engineering|Sales|Marketing|Finance|HR|Operations|Product|Design)\b",
            text,
            re.IGNORECASE,
        )
        if dept_match:
            self.user_profile["department"] = dept_match.group(1).title()

        os_match = re.search(r"\b(macOS|MacBook|Windows 11|Windows 10|Windows|Ubuntu|Linux)\b", text, re.I)
        if os_match:
            self.user_profile["device_os"] = os_match.group(1)

    def add_turn(
        self,
        role: str,
        content: str,
        mode: str = "conversational",
        guardrail_triggered: str | None = None,
    ) -> None:
        """Append a turn, extract profile entities, and compress overflow turns."""
        if role == "user":
            self._extract_entities(content)
        self.turns.append(
            ChatTurn(
                role=role,
                content=content,
                mode=mode,
                guardrail_triggered=guardrail_triggered,
            )
        )
        self._compress_if_needed()

    def _compress_if_needed(self) -> None:
        """Keep recent `window_size` turns verbatim and roll older ones into summary."""
        if len(self.turns) <= self.window_size:
            return
        overflow = self.turns[: -self.window_size]
        self.turns = self.turns[-self.window_size :]

        snippets = []
        for t in overflow:
            tag = "User" if t.role == "user" else "Nova"
            cleaned = " ".join(t.content.split())[:140]
            snippets.append(f"{tag}: {cleaned}")
        combined = " | ".join(snippets)
        if self.rolling_summary == "No prior conversation yet.":
            self.rolling_summary = combined[:450]
        else:
            self.rolling_summary = f"{self.rolling_summary} | {combined}"[-500:]

    def format_recent_history(self) -> str:
        """Format active window turns for prompt injection."""
        if not self.turns:
            return "(No prior turns in active window)"
        lines = []
        for t in self.turns:
            speaker = "User" if t.role == "user" else "Assistant"
            lines.append(f"{speaker}: {t.content}")
        return "\n".join(lines)

    def profile_string(self) -> str:
        return (
            f"Name={self.user_profile['name']}, "
            f"Department={self.user_profile['department']}, "
            f"Device/OS={self.user_profile['device_os']}"
        )

    def clear(self) -> None:
        self.turns.clear()
        self.rolling_summary = "No prior conversation yet."
        self.user_profile = {"name": "Employee", "department": "General", "device_os": "Unknown"}

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_profile": self.user_profile,
                "rolling_summary": self.rolling_summary,
                "turns": [asdict(t) for t in self.turns],
            },
            indent=2,
        )
