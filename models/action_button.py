"""
ActionButton model - mirrors SuchByte.MacroDeck.ActionButton
Each button can have:
  - multiple PluginActions (with configuration JSON)
  - an icon (base64 PNG or path)
  - a label (supports variable templates via Cottle-style {{var}})
  - a state (on/off)
  - a state binding to a Bool variable
  - conditions (run different action lists based on variable values)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List, Optional
import uuid


@dataclass
class ActionEntry:
    """One action wired to a button."""
    plugin_id: str
    action_id: str
    configuration: str = ""           # JSON string, plugin-defined
    configuration_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "plugin_id": self.plugin_id,
            "action_id": self.action_id,
            "configuration": self.configuration,
            "configuration_summary": self.configuration_summary,
        }

    @staticmethod
    def from_dict(d: dict) -> "ActionEntry":
        return ActionEntry(
            plugin_id=d["plugin_id"],
            action_id=d["action_id"],
            configuration=d.get("configuration", ""),
            configuration_summary=d.get("configuration_summary", ""),
        )


@dataclass
class Condition:
    """Condition block: if variable <op> value → run actions_true, else actions_false.

    style_true / style_false are optional appearance overrides applied when the
    condition evaluates to True / False.  Each is a dict with any subset of:
      { "label": str, "label_color": str, "background_color": str, "icon": str|None }

    Use variable_name="_state" to test the button's own toggle state (True/False).
    """
    variable_name: str
    operator: str          # ==, !=, >, <, >=, <=
    compare_value: str
    actions_true: List[ActionEntry] = field(default_factory=list)
    actions_false: List[ActionEntry] = field(default_factory=list)
    style_true:  dict = field(default_factory=dict)   # appearance when condition is True
    style_false: dict = field(default_factory=dict)   # appearance when condition is False

    def to_dict(self) -> dict:
        return {
            "variable_name": self.variable_name,
            "operator": self.operator,
            "compare_value": self.compare_value,
            "actions_true":  [a.to_dict() for a in self.actions_true],
            "actions_false": [a.to_dict() for a in self.actions_false],
            "style_true":    self.style_true,
            "style_false":   self.style_false,
        }

    @staticmethod
    def from_dict(d: dict) -> "Condition":
        return Condition(
            variable_name=d["variable_name"],
            operator=d["operator"],
            compare_value=d["compare_value"],
            actions_true=[ActionEntry.from_dict(a) for a in d.get("actions_true", [])],
            actions_false=[ActionEntry.from_dict(a) for a in d.get("actions_false", [])],
            style_true=d.get("style_true", {}),
            style_false=d.get("style_false", {}),
        )


@dataclass
class ActionButton:
    button_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    label_color: str = "#FFFFFF"
    label_font_size: int = 12
    icon: Optional[str] = None           # base64 or file path
    background_color: str = "#000000"
    state: bool = False                  # on/off toggle
    state_binding: Optional[str] = None  # variable name (Bool)
    actions: List[ActionEntry] = field(default_factory=list)
    conditions: List[Condition] = field(default_factory=list)
    button_type: str = "button"          # "button" | "slider" | "slider_occupied"
    slider_config: dict = field(default_factory=dict)

    def resolve_appearance(self, get_variable) -> dict:
        """Return the effective {label, label_color, background_color, icon, state}
        after evaluating all conditions.  Conditions are applied in order; the last
        matching condition wins.  get_variable(name) -> value (or None)."""
        from macro_deck_python.utils.condition import evaluate_condition
        result = {
            "label":            self.label,
            "label_color":      self.label_color,
            "background_color": self.background_color,
            "icon":             self.icon,
            "state":            self.state,
        }
        for cond in self.conditions:
            try:
                matched = evaluate_condition(
                    cond.variable_name, cond.operator, cond.compare_value,
                    button_state=self.state, get_variable=get_variable,
                )
                style = cond.style_true if matched else cond.style_false
                for key in ("label", "label_color", "background_color", "icon"):
                    if style.get(key) not in (None, ""):
                        result[key] = style[key]
            except Exception:
                pass
        return result

    def to_dict(self) -> dict:
        return {
            "button_id": self.button_id,
            "label": self.label,
            "label_color": self.label_color,
            "label_font_size": self.label_font_size,
            "icon": self.icon,
            "background_color": self.background_color,
            "state": self.state,
            "state_binding": self.state_binding,
            "actions": [a.to_dict() for a in self.actions],
            "conditions": [c.to_dict() for c in self.conditions],
            "button_type": self.button_type,
            "slider_config": self.slider_config,
        }

    @staticmethod
    def from_dict(d: dict) -> "ActionButton":
        return ActionButton(
            button_id=d.get("button_id", str(uuid.uuid4())),
            label=d.get("label", ""),
            label_color=d.get("label_color", "#FFFFFF"),
            label_font_size=d.get("label_font_size", 12),
            icon=d.get("icon"),
            background_color=d.get("background_color", "#000000"),
            state=d.get("state", False),
            state_binding=d.get("state_binding"),
            actions=[ActionEntry.from_dict(a) for a in d.get("actions", [])],
            conditions=[Condition.from_dict(c) for c in d.get("conditions", [])],
            button_type=d.get("button_type", "button"),
            slider_config=d.get("slider_config", {}),
        )