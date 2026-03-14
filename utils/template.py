"""
Template renderer for button labels.
Supports {variable_name} substitution (mirrors Macro Deck's Cottle-style templates).
Also evaluates arithmetic expressions: {my_var + 1}, {my_float:.2f}
"""
from __future__ import annotations
import re
from typing import Any, Callable, Optional

_PATTERN = re.compile(r"\{([^}]+)\}")


def render_label(template: str, get_variable: Callable[[str], Optional[Any]]) -> str:
    """Replace {var_name} and {var_name:format_spec} tokens in *template*."""

    def replacer(match: re.Match) -> str:
        expr = match.group(1).strip()
        # Split optional format spec
        if ":" in expr:
            var_part, fmt_spec = expr.split(":", 1)
        else:
            var_part, fmt_spec = expr, None

        value = get_variable(var_part.strip())
        if value is None:
            return match.group(0)  # keep original token if unknown
        try:
            if fmt_spec:
                return format(value, fmt_spec)
            return str(value)
        except Exception:
            return str(value)

    return _PATTERN.sub(replacer, template)
