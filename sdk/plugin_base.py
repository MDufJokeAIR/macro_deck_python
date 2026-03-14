"""
sdk/plugin_base.py  — PluginBase and ActionBase
"""
from __future__ import annotations

import json
import logging
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton
    from macro_deck_python.models.variable import VariableType

logger = logging.getLogger("macro_deck.sdk")


# ═══════════════════════════════════════════════════════════════════
# ActionBase
# ═══════════════════════════════════════════════════════════════════

class ActionBase(PluginAction):
    """
    Base class for actions written in the traditional class style.
    Adds a get_config() helper for reading JSON configuration.
    """

    def get_config(self, key: str, default: Any = None) -> Any:
        """Read a value from this action's JSON configuration string."""
        try:
            cfg = json.loads(self.configuration) if self.configuration else {}
            return cfg.get(key, default)
        except (json.JSONDecodeError, TypeError):
            return default

    @abstractmethod
    def trigger(self, client_id: str, action_button: "ActionButton") -> None: ...

    def on_action_button_loaded(self) -> None: ...
    def on_action_button_delete(self) -> None: ...


# ═══════════════════════════════════════════════════════════════════
# Internal: action built from @action decorator
# ═══════════════════════════════════════════════════════════════════

_MISSING = object()  # sentinel for attribute presence check


class _DecoratorAction(ActionBase):
    action_id: str = ""
    name: str = ""
    description: str = ""
    can_configure: bool = False
    _trigger_fn: Optional[Callable] = None
    _on_load_fn: Optional[Callable] = None
    _on_delete_fn: Optional[Callable] = None

    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        if self._trigger_fn and self.plugin:
            # Temporarily expose action attributes on the plugin so that
            # @action methods can read `self.configuration` naturally.
            _old_cfg     = getattr(self.plugin, "configuration", _MISSING)
            _old_summary = getattr(self.plugin, "configuration_summary", _MISSING)
            self.plugin.configuration          = self.configuration
            self.plugin.configuration_summary  = self.configuration_summary
            try:
                self._trigger_fn(self.plugin, client_id, action_button)
            finally:
                if _old_cfg is _MISSING:
                    self.plugin.__dict__.pop("configuration", None)
                else:
                    self.plugin.configuration = _old_cfg
                if _old_summary is _MISSING:
                    self.plugin.__dict__.pop("configuration_summary", None)
                else:
                    self.plugin.configuration_summary = _old_summary

    def on_action_button_loaded(self) -> None:
        if self._on_load_fn and self.plugin:
            self._on_load_fn(self.plugin)

    def on_action_button_delete(self) -> None:
        if self._on_delete_fn and self.plugin:
            self._on_delete_fn(self.plugin)


# ═══════════════════════════════════════════════════════════════════
# PluginBase
# ═══════════════════════════════════════════════════════════════════

class PluginBase(IMacroDeckPlugin):
    """
    Base class for all Python Macro Deck extensions.

    Decorator style (recommended)
    ─────────────────────────────
        from macro_deck_python.sdk import PluginBase, action, VariableType, set_variable

        class Main(PluginBase):
            package_id  = "me.myplugin"
            name        = "My Plugin"
            version     = "1.0.0"
            author      = "Me"
            description = "Does something cool"

            @action(name="Mute", description="Toggle system mute")
            def mute(self, client_id, button):
                import subprocess
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

            @action(name="Counter", description="Increment counter", can_configure=True)
            def counter(self, client_id, button):
                import json
                cfg = json.loads(self.configuration) if self.configuration else {}
                n = int(cfg.get("start", 0))
                set_variable("my_counter", n + 1, VariableType.INTEGER, self)

    Traditional class style
    ───────────────────────
        class CountAction(ActionBase):
            action_id = "count"; name = "Count"; description = "Counts"
            def trigger(self, client_id, button): ...

        class Main(PluginBase):
            package_id = "me.myplugin"; ...
            def enable(self):
                super().enable()                  # loads @action methods
                self.actions.append(CountAction()) # add class-style actions
    """

    can_configure: bool = False
    _sdk_action_defs: List[dict]   # collected by __init_subclass__

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Collect @action / @on_load / @on_delete decorated methods
        action_defs: Dict[str, dict] = {}
        on_load_hooks: Dict[str, Callable] = {}
        on_delete_hooks: Dict[str, Callable] = {}

        for attr_name in vars(cls):          # only this class's own attrs
            attr = getattr(cls, attr_name, None)
            if not callable(attr):
                continue
            if hasattr(attr, "_sdk_action_meta"):
                meta = dict(attr._sdk_action_meta)
                meta["_trigger_fn"] = attr
                action_defs[meta["action_id"]] = meta
            if hasattr(attr, "_sdk_on_load_for"):
                on_load_hooks[attr._sdk_on_load_for] = attr
            if hasattr(attr, "_sdk_on_delete_for"):
                on_delete_hooks[attr._sdk_on_delete_for] = attr

        # Wire hooks into their target action defs
        for aid, fn in on_load_hooks.items():
            if aid in action_defs:
                action_defs[aid]["on_load"] = fn
        for aid, fn in on_delete_hooks.items():
            if aid in action_defs:
                action_defs[aid]["on_delete"] = fn

        cls._sdk_action_defs = list(action_defs.values())

    def _build_decorator_actions(self) -> List[_DecoratorAction]:
        result = []
        for meta in self.__class__._sdk_action_defs:
            act_cls = type(
                f"_Action_{meta['action_id']}",
                (_DecoratorAction,),
                {
                    "action_id":    meta["action_id"],
                    "name":         meta["name"],
                    "description":  meta["description"],
                    "can_configure": meta["can_configure"],
                    "_trigger_fn":  staticmethod(meta["_trigger_fn"]),
                    "_on_load_fn":  staticmethod(meta.get("on_load")) if meta.get("on_load") else None,
                    "_on_delete_fn": staticmethod(meta.get("on_delete")) if meta.get("on_delete") else None,
                },
            )
            result.append(act_cls())
        return result

    def enable(self) -> None:
        """
        Auto-discovers @action-decorated methods and populates self.actions.
        Call super().enable() and then append your own ActionBase subclasses.
        """
        self.actions: List[PluginAction] = self._build_decorator_actions()

    def disable(self) -> None: ...
    def open_configurator(self) -> None: ...

    # ── convenience shortcuts ─────────────────────────────────────────

    def get_config(self, key: str, default: str = "") -> str:
        from macro_deck_python.plugins.base import PluginConfiguration
        return PluginConfiguration.get_value(self, key, default)

    def set_config(self, key: str, value: str) -> None:
        from macro_deck_python.plugins.base import PluginConfiguration
        PluginConfiguration.set_value(self, key, value)

    def set_variable(self, name: str, value: Any,
                     vtype: "VariableType", save: bool = True) -> None:
        from macro_deck_python.services.variable_manager import VariableManager
        VariableManager.set_value(name, value, vtype, plugin_id=self.package_id, save=save)

    def get_variable(self, name: str) -> Any:
        from macro_deck_python.services.variable_manager import VariableManager
        return VariableManager.get_value(name)

    def log_trace(self, msg: str) -> None:   logger.debug("[%s] %s", self.package_id, msg)
    def log_info(self, msg: str) -> None:    logger.info("[%s] %s", self.package_id, msg)
    def log_warning(self, msg: str) -> None: logger.warning("[%s] %s", self.package_id, msg)
    def log_error(self, msg: str) -> None:   logger.error("[%s] %s", self.package_id, msg)
