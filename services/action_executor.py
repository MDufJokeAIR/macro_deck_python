"""
ActionExecutor - mirrors SuchByte.MacroDeck.ActionButton trigger pipeline.
Runs PluginActions attached to a button, evaluating conditions first.
All actions are executed in a background thread so the WebSocket loop never blocks.
"""
from __future__ import annotations
import asyncio
import logging
import threading
from typing import TYPE_CHECKING

from macro_deck_python.utils.condition import evaluate_condition

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton, ActionEntry

logger = logging.getLogger("macro_deck.executor")


def _run_action_entry(entry: "ActionEntry", client_id: str, button: "ActionButton") -> None:
    from macro_deck_python.plugins.plugin_manager import PluginManager
    act = PluginManager.get_action(entry.plugin_id, entry.action_id)
    if act is None:
        logger.warning(
            "Action not found: plugin=%s action=%s", entry.plugin_id, entry.action_id
        )
        return
    # Inject current configuration into the action instance
    act.configuration = entry.configuration
    act.configuration_summary = entry.configuration_summary
    try:
        act.trigger(client_id, button)
    except Exception as exc:
        logger.error(
            "Error triggering action %s/%s: %s", entry.plugin_id, entry.action_id, exc
        )


def execute_button(button: "ActionButton", client_id: str) -> None:
    """Entry point — call this when a button is pressed."""

    def _run() -> None:
        # 1. Evaluate conditions first (each condition may have its own action list)
        for cond in button.conditions:
            result = evaluate_condition(cond.variable_name, cond.operator, cond.compare_value)
            actions_to_run = cond.actions_true if result else cond.actions_false
            for entry in actions_to_run:
                _run_action_entry(entry, client_id, button)

        # 2. Run the unconditional actions
        for entry in button.actions:
            _run_action_entry(entry, client_id, button)

    t = threading.Thread(target=_run, daemon=True, name=f"exec-{client_id[:8]}")
    t.start()
