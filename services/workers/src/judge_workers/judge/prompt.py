"""Prompt template rendering — `{{var}}` substitution only.

We deliberately do NOT use Jinja for M2: full Jinja is overkill for a
metric prompt and a security risk for hosted/multi-tenant. The supported
syntax is just `{{name}}` (whitespace allowed); missing names raise.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptRenderError(ValueError):
    pass


def render_prompt(template: str, vars: Mapping[str, Any]) -> str:
    missing: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in vars:
            missing.append(key)
            return ""
        v = vars[key]
        return v if isinstance(v, str) else str(v)

    out = _PLACEHOLDER.sub(_sub, template)
    if missing:
        raise PromptRenderError(f"missing template vars: {sorted(set(missing))}")
    return out
