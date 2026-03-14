"""
sdk/decorators.py
=================
Decorators for the Macro Deck Python SDK.

@action      — mark a method as a button action
@on_load     — mark a method to be called when a button is loaded
@on_delete   — mark a method to be called when a button is deleted

Example
-------
    class MyPlugin(PluginBase):
        package_id  = "me.myplugin"
        name        = "My Plugin"
        version     = "1.0.0"
        author      = "Me"
        description = "Does something"

        @action(name="Mute Audio", description="Toggle system mute",
                can_configure=False)
        def mute(self, client_id: str, button):
            import subprocess
            subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

        @action(name="Send Text", description="Type a string", can_configure=True)
        def send_text(self, client_id: str, button):
            import pyautogui, json
            cfg = json.loads(self.configuration) if self.configuration else {}
            pyautogui.typewrite(cfg.get("text", ""))

        @on_load("send_text")
        def send_text_loaded(self):
            self.log_info("send_text button was loaded")

        @on_delete("send_text")
        def send_text_deleted(self):
            self.log_info("send_text button was deleted")
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional


def _make_action_id(fn: Callable) -> str:
    """Convert a function name like 'my_cool_action' → 'my_cool_action' (kept as-is)."""
    return fn.__name__


def action(
    name: str,
    description: str = "",
    can_configure: bool = False,
    action_id: Optional[str] = None,
) -> Callable:
    """
    Decorator: mark a PluginBase method as a Macro Deck action.

    Parameters
    ----------
    name : str
        Human-readable action name shown in the UI.
    description : str
        Short description shown in the action picker.
    can_configure : bool
        Whether the action has a configuration form.
    action_id : str, optional
        Explicit action ID. Defaults to the method name.

    The decorated method receives (self, client_id: str, button: ActionButton).
    """
    def decorator(fn: Callable) -> Callable:
        fn._sdk_action_meta = {
            "action_id":    action_id or _make_action_id(fn),
            "name":         name,
            "description":  description,
            "can_configure": can_configure,
            "on_load":      None,
            "on_delete":    None,
        }
        return fn
    return decorator


def on_load(target_action_id: str) -> Callable:
    """
    Decorator: mark a PluginBase method to run when a button using
    the specified action is loaded from disk.

    Parameters
    ----------
    target_action_id : str
        The action_id (method name or explicit id) this hook applies to.
    """
    def decorator(fn: Callable) -> Callable:
        fn._sdk_on_load_for = target_action_id
        return fn
    return decorator


def on_delete(target_action_id: str) -> Callable:
    """
    Decorator: mark a PluginBase method to run when a button using
    the specified action is deleted.

    Parameters
    ----------
    target_action_id : str
        The action_id this hook applies to.
    """
    def decorator(fn: Callable) -> Callable:
        fn._sdk_on_delete_for = target_action_id
        return fn
    return decorator
