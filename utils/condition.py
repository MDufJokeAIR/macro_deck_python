"""
Condition evaluator.
Evaluates whether variable <op> value is True/False.
Supports the special variable name ``_state`` which refers to the button's
own toggle state (pass button_state=True/False).
"""
from __future__ import annotations
from typing import Any, Callable, Optional

from macro_deck_python.services.variable_manager import VariableManager


def _coerce(a: Any, b: Any):
    """Try to coerce both values to the same numeric type for comparison."""
    try:
        fa, fb = float(a), float(b)
        return fa, fb
    except (ValueError, TypeError):
        return str(a), str(b)


def evaluate_condition(
    variable_name: str,
    operator: str,
    compare_value: str,
    button_state: bool = False,
    get_variable: Optional[Callable] = None,
) -> bool:
    """Return True if <variable_name> <operator> <compare_value>.

    Special variable name ``_state`` refers to the button's own toggle state.
    Pass button_state=btn.state for this to work.

    get_variable is an optional callable(name)->value; falls back to
    VariableManager.get_value if not provided.
    """
    if get_variable is None:
        get_variable = VariableManager.get_value

    if variable_name == "_state":
        raw = button_state
    else:
        raw = get_variable(variable_name)
        if raw is None:
            return False

    a, b = _coerce(raw, compare_value)

    try:
        if operator == "==":  return a == b
        if operator == "!=":  return a != b
        if operator == ">":   return a > b
        if operator == "<":   return a < b
        if operator == ">=":  return a >= b
        if operator == "<=":  return a <= b
    except TypeError:
        pass
    return False