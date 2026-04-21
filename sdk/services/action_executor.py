"""
ActionExecutor — walks a button's Block program recursively.
All execution happens in a background thread so the WebSocket loop never blocks.
"""
from __future__ import annotations
import asyncio
import copy
import logging
import re
import threading
from typing import TYPE_CHECKING, List, Optional, Callable, Awaitable

from macro_deck_python.utils.condition import evaluate_condition

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton, Block

logger = logging.getLogger("macro_deck.executor")

# Global event loop for async callbacks (set by WebSocket server)
_event_loop: Optional[asyncio.AbstractEventLoop] = None

# Global callback for pushing button updates to clients
_appearance_update_callback: Optional[Callable[[str], Awaitable[None]]] = None

def set_event_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Set the event loop for pushing appearance updates."""
    global _event_loop
    _event_loop = loop


def set_appearance_update_callback(cb: Optional[Callable[[str], Awaitable[None]]]) -> None:
    """Set callback to push appearance updates when STYLE blocks execute."""
    global _appearance_update_callback
    _appearance_update_callback = cb


async def _push_button_update(button_id: str) -> None:
    """Push button appearance update to all clients."""
    if _appearance_update_callback:
        try:
            await _appearance_update_callback(button_id)
        except Exception as exc:
            logger.error("Error pushing button update: %s", exc)


def _run_action_block(block: "Block", client_id: str, button: "ActionButton") -> None:
    from macro_deck_python.plugins.plugin_manager import PluginManager
    act = PluginManager.get_action(block.plugin_id, block.action_id)
    if act is None:
        logger.warning("Action not found: plugin=%s action=%s", block.plugin_id, block.action_id)
        return
    # Work on a shallow copy so concurrent button executions (each running in
    # their own thread) cannot overwrite each other's .configuration before or
    # during trigger().  Without this, two rapid presses sharing the same action
    # singleton can race: Thread A sets act.configuration = "ctrl+c", Thread B
    # overwrites it with "ctrl+v", and Thread A ends up triggering the wrong key.
    act = copy.copy(act)
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
        elif block.type == "style":
            # Apply style block to button appearance
            if block.label is not None:            button.label            = block.label
            if block.label_color is not None:      button.label_color      = block.label_color
            if block.background_color is not None: button.background_color = block.background_color
            if block.icon is not None:             button.icon             = block.icon
            # Font size: extract numeric part if it's a string like "12px" or "1rem"
            if block.font_size is not None:
                try:
                    # Extract leading digits from font_size string (e.g., "12px" → 12)
                    match = re.match(r'(\d+)', str(block.font_size))
                    if match:
                        button.label_font_size = int(match.group(1))
                except (ValueError, AttributeError):
                    pass  # Keep current value if parsing fails
            
            # Push update to clients so appearance changes are visible
            # Use run_coroutine_threadsafe to safely call async code from this thread
            global _event_loop
            if _event_loop is not None and _event_loop.is_running():
                try:
                    asyncio.run_coroutine_threadsafe(
                        _push_button_update(button.button_id),
                        _event_loop
                    )
                except Exception as exc:
                    logger.debug("Could not push style update: %s", exc)


def execute_button(button, client_id: str) -> None:
    """Entry point — called when a button is pressed.  Only ActionButton is executable."""
    from macro_deck_python.models.action_button import ActionButton
    if not isinstance(button, ActionButton):
        logger.debug("execute_button called on non-ActionButton (%s) — ignored",
                     type(button).__name__)
        return

    def _run() -> None:
        _walk(button.program, client_id, button)
        global _event_loop
        if _event_loop is not None and _event_loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(
                    _push_button_update(button.button_id), _event_loop)
            except Exception as exc:
                logger.debug("Could not push final update: %s", exc)

    t = threading.Thread(target=_run, daemon=True, name=f"exec-{client_id[:8]}")
    t.start()