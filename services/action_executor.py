"""
ActionExecutor — walks a button's Block program recursively.
All execution happens in a background thread so the WebSocket loop never blocks.
"""
from __future__ import annotations
import logging
import threading
from typing import TYPE_CHECKING, List

from macro_deck_python.utils.condition import evaluate_condition

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton, Block

logger = logging.getLogger("macro_deck.executor")


def _run_action_block(block: "Block", client_id: str, button: "ActionButton") -> None:
    from macro_deck_python.plugins.plugin_manager import PluginManager
    act = PluginManager.get_action(block.plugin_id, block.action_id)
    if act is None:
        logger.warning("Action not found: plugin=%s action=%s", block.plugin_id, block.action_id)
        return
    act.configuration         = block.configuration
    act.configuration_summary = block.configuration_summary
    try:
        act.trigger(client_id, button)
    except Exception as exc:
        logger.error("Error triggering %s/%s: %s", block.plugin_id, block.action_id, exc)


def _eval_block_condition(block: "Block", button: "ActionButton") -> bool:
    """Evaluate an IF block's conditions list with AND/OR logic."""
    conds = block.conditions if block.conditions else [{
        "variable_name": block.variable_name,
        "operator": block.operator,
        "compare_value": block.compare_value,
        "logic": "AND",
    }]
    result = None
    for c in conds:
        match = evaluate_condition(
            c.get("variable_name", ""),
            c.get("operator", "=="),
            c.get("compare_value", ""),
            button_state=button.state,
        )
        logic = c.get("logic", "AND")
        if result is None:
            result = match
        elif logic == "OR":
            result = result or match
        else:
            result = result and match
    return bool(result)


def _walk(blocks: List["Block"], client_id: str, button: "ActionButton") -> None:
    for block in blocks:
        if block.type == "action":
            _run_action_block(block, client_id, button)
        elif block.type == "if":
            try:
                matched = _eval_block_condition(block, button)
                branch = block.then_blocks if matched else block.else_blocks
                _walk(branch, client_id, button)
            except Exception as exc:
                logger.error("Condition eval error: %s", exc)
        # style blocks are appearance-only — no runtime action


def execute_button(button: "ActionButton", client_id: str) -> None:
    """Entry point — called when a button is pressed."""
    def _run() -> None:
        _walk(button.program, client_id, button)

    t = threading.Thread(target=_run, daemon=True, name=f"exec-{client_id[:8]}")
    t.start()