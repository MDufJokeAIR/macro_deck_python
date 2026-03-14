"""
Condition evaluator.
Evaluates whether variable <op> value is True/False.
Mirrors the condition logic in SuchByte.MacroDeck.ActionButton conditions.
"""
from __future__ import annotations
from typing import Any

from macro_deck_python.services.variable_manager import VariableManager


def _coerce(a: Any, b: Any):
    """Try to coerce both values to the same numeric type for comparison."""
    try:
        fa, fb = float(a), float(b)
        return fa, fb
    except (ValueError, TypeError):
        return str(a), str(b)


def evaluate_condition(variable_name: str, operator: str, compare_value: str) -> bool:
    """Return True if <variable_name> <operator> <compare_value>."""
    raw = VariableManager.get_value(variable_name)
    if raw is None:
        return False

    a, b = _coerce(raw, compare_value)

    try:
        if operator == "==":
            return a == b
        if operator == "!=":
            return a != b
        if operator == ">":
            return a > b
        if operator == "<":
            return a < b
        if operator == ">=":
            return a >= b
        if operator == "<=":
            return a <= b
    except TypeError:
        pass
    return False
