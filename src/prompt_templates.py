"""Reusable variable-driven prompt template engine (LangChain-compatible interface)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PromptTemplate:
    """Reusable prompt template with strict variable validation."""

    name: str
    template: str
    input_variables: list[str]
    version: str = "1.0"

    def format(self, **kwargs: Any) -> str:
        """Render the template after validating all required variables are provided."""
        missing = [var for var in self.input_variables if var not in kwargs]
        if missing:
            raise ValueError(
                f"Missing required template variable(s) for '{self.name}': {', '.join(missing)}"
            )
        safe_kwargs = {k: ("" if v is None else v) for k, v in kwargs.items()}
        return self.template.format(**safe_kwargs)


class TemplateRegistry:
    """Loads and serves named prompt templates from JSON."""

    def __init__(self, json_path: str | Path) -> None:
        raw = json.loads(Path(json_path).read_text(encoding="utf-8"))
        self.templates: dict[str, PromptTemplate] = {}
        for key, item in raw.items():
            self.templates[key] = PromptTemplate(
                name=item["name"],
                template=item["template"],
                input_variables=list(item["variables"]),
                version=item.get("version", "1.0"),
            )

    def get(self, template_id: str) -> PromptTemplate:
        if template_id not in self.templates:
            raise KeyError(f"Unknown template_id: {template_id}")
        return self.templates[template_id]

    def render(self, template_id: str, **kwargs: Any) -> str:
        return self.get(template_id).format(**kwargs)

    def list_ids(self) -> list[str]:
        return list(self.templates.keys())
