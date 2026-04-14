"""
ActionButton model.
Each button has a `program`: a list of Blocks executed in order.
Blocks can be:
  - "action"  : run a plugin action
  - "style"   : override appearance at this point in execution
  - "if"      : conditional branch with nested then_blocks / else_blocks

Backward-compat: old buttons with `actions` + `conditions` are auto-migrated
to a program on load.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid


# ── Block ─────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    """One block in a button program."""
    type: str  # "action" | "style" | "if"

    # ── action fields ──────────────────────────────────────────────
    plugin_id: str = ""
    action_id: str = ""
    configuration: str = "{}"
    configuration_summary: str = ""

    # ── style fields ───────────────────────────────────────────────
    label: Optional[str] = None
    label_color: Optional[str] = None
    background_color: Optional[str] = None
    icon: Optional[str] = None
    font_size: Optional[str] = None

    # ── if fields ──────────────────────────────────────────────────
    # `conditions` is a list of {variable_name, operator, compare_value, logic}
    # where logic is "AND" or "OR" (ignored on the first item).
    # For backward compat, if conditions is empty we fall back to the
    # top-level variable_name / operator / compare_value fields.
    variable_name: str = ""
    operator: str = "=="
    compare_value: str = ""
    conditions: List[dict] = field(default_factory=list)
    then_blocks: List["Block"] = field(default_factory=list)
    else_blocks: List["Block"] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.type == "action":
            d.update({
                "plugin_id":             self.plugin_id,
                "action_id":             self.action_id,
                "configuration":         self.configuration,
                "configuration_summary": self.configuration_summary,
            })
        elif self.type == "style":
            if self.label is not None:         d["label"]            = self.label
            if self.label_color is not None:   d["label_color"]      = self.label_color
            if self.background_color is not None: d["background_color"] = self.background_color
            if self.icon is not None:          d["icon"]             = self.icon
            if self.font_size is not None:     d["font_size"]        = self.font_size
        elif self.type == "if":
            # Normalise: always store as conditions list
            conds = self.conditions if self.conditions else [{
                "variable_name": self.variable_name,
                "operator":      self.operator,
                "compare_value": self.compare_value,
                "logic":         "AND",
            }]
            d.update({
                "conditions":  conds,
                "then_blocks": [b.to_dict() for b in self.then_blocks],
                "else_blocks": [b.to_dict() for b in self.else_blocks],
            })
        return d

    @staticmethod
    def from_dict(d: dict) -> "Block":
        t = d.get("type", "action")
        b = Block(type=t)
        if t == "action":
            b.plugin_id             = d.get("plugin_id", "")
            b.action_id             = d.get("action_id", "")
            b.configuration         = d.get("configuration", "{}")
            b.configuration_summary = d.get("configuration_summary", "")
        elif t == "style":
            b.label            = d.get("label")
            b.label_color      = d.get("label_color")
            b.background_color = d.get("background_color")
            b.icon             = d.get("icon")
            b.font_size        = d.get("font_size")
        elif t == "if":
            # Support both new (conditions list) and legacy (flat fields)
            if "conditions" in d:
                b.conditions = d["conditions"]
                # Also populate top-level fields from first condition for UI compatibility
                if b.conditions:
                    first_cond = b.conditions[0]
                    b.variable_name = first_cond.get("variable_name", "")
                    b.operator = first_cond.get("operator", "==")
                    b.compare_value = first_cond.get("compare_value", "")
            else:
                b.variable_name = d.get("variable_name", "")
                b.operator = d.get("operator", "==")
                b.compare_value = d.get("compare_value", "")
                b.conditions = [{
                    "variable_name": b.variable_name,
                    "operator":      b.operator,
                    "compare_value": b.compare_value,
                    "logic":         "AND",
                }]
            b.then_blocks = [Block.from_dict(x) for x in d.get("then_blocks", [])]
            b.else_blocks = [Block.from_dict(x) for x in d.get("else_blocks", [])]
        return b


def _migrate_legacy(actions: list, conditions: list) -> List[Block]:
    """Convert old actions + conditions lists into a Block program."""
    program: List[Block] = []

    # Legacy conditions become IF blocks first
    for cond in conditions:
        b = Block(
            type="if",
            variable_name=cond.get("variable_name", ""),
            operator=cond.get("operator", "=="),
            compare_value=cond.get("compare_value", ""),
        )
        # style_true → style block inside then
        st = cond.get("style_true", {})
        if any(v not in (None, "") for v in st.values()):
            sb = Block(type="style",
                       label=st.get("label") or None,
                       label_color=st.get("label_color") or None,
                       background_color=st.get("background_color") or None,
                       font_size=st.get("font_size") or None)
            b.then_blocks.append(sb)
        for a in cond.get("actions_true", []):
            b.then_blocks.append(Block(type="action",
                                       plugin_id=a.get("plugin_id",""),
                                       action_id=a.get("action_id",""),
                                       configuration=a.get("configuration","{}")))
        # style_false → style block inside else
        sf = cond.get("style_false", {})
        if any(v not in (None, "") for v in sf.values()):
            sb = Block(type="style",
                       label=sf.get("label") or None,
                       label_color=sf.get("label_color") or None,
                       background_color=sf.get("background_color") or None,
                       font_size=sf.get("font_size") or None)
            b.else_blocks.append(sb)
        for a in cond.get("actions_false", []):
            b.else_blocks.append(Block(type="action",
                                       plugin_id=a.get("plugin_id",""),
                                       action_id=a.get("action_id",""),
                                       configuration=a.get("configuration","{}")))
        program.append(b)

    # Legacy unconditional actions come after
    for a in actions:
        program.append(Block(type="action",
                             plugin_id=a.get("plugin_id",""),
                             action_id=a.get("action_id",""),
                             configuration=a.get("configuration","{}"),
                             configuration_summary=a.get("configuration_summary","")))
    return program


# ── ActionButton ──────────────────────────────────────────────────────────────

@dataclass
class ActionButton:
    button_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    label_color: str = "#FFFFFF"
    # None  = auto-fit (pad client computes the largest font where the longest
    #         word fills the button width, each word on its own line).
    # int   = explicit size in px, used as-is on all screen sizes.
    label_font_size: Optional[int] = None
    icon: Optional[str] = None
    background_color: str = "#000000"
    state: bool = False
    state_binding: Optional[str] = None
    program: List[Block] = field(default_factory=list)
    # Slider mode: if is_slider=True, this button acts as a slider instead of a button
    is_slider: bool = False
    slider_size: int = 1  # number of cells to extend (1-max)
    slider_orientation: str = "vertical"  # "vertical" or "horizontal"
    slider_variable: str = ""  # variable name to bind slider value (0-100)
    # If this cell is occupied by a slider from another button, points to that button's position
    slider_parent_position: Optional[str] = None  # e.g. "4_3"

    def resolve_appearance(self, get_variable) -> dict:
        """Walk the program and apply style blocks / if-branch styles.
        Returns effective {label, label_color, background_color, icon, state}."""
        from macro_deck_python.utils.condition import evaluate_condition
        result = {
            "label":            self.label,
            "label_color":      self.label_color,
            "background_color": self.background_color,
            "icon":             self.icon,
            "state":            self.state,
        }

        def _apply_style(block: "Block") -> None:
            if block.label is not None:            result["label"]            = block.label
            if block.label_color is not None:      result["label_color"]      = block.label_color
            if block.background_color is not None: result["background_color"] = block.background_color
            if block.icon is not None:             result["icon"]             = block.icon

        def _eval_if(b: "Block") -> bool:
            from macro_deck_python.utils.condition import evaluate_condition
            conds = b.conditions if b.conditions else [{
                "variable_name": b.variable_name,
                "operator": b.operator,
                "compare_value": b.compare_value,
                "logic": "AND",
            }]
            result = None
            for c in conds:
                match = evaluate_condition(
                    c.get("variable_name", ""),
                    c.get("operator", "=="),
                    c.get("compare_value", ""),
                    button_state=self.state,
                    get_variable=get_variable,
                )
                logic = c.get("logic", "AND")
                if result is None:
                    result = match
                elif logic == "OR":
                    result = result or match
                else:  # AND
                    result = result and match
            return bool(result)

        def _walk(blocks):
            for b in blocks:
                if b.type == "style":
                    _apply_style(b)
                elif b.type == "if":
                    try:
                        _walk(b.then_blocks if _eval_if(b) else b.else_blocks)
                    except Exception:
                        pass
                # action blocks don't affect appearance

        _walk(self.program)
        return result

    def to_dict(self) -> dict:
        return {
            "button_id":        self.button_id,
            "label":            self.label,
            "label_color":      self.label_color,
            "label_font_size":  self.label_font_size,
            "icon":             self.icon,
            "background_color": self.background_color,
            "state":            self.state,
            "state_binding":    self.state_binding,
            "program":          [b.to_dict() for b in self.program],
            "is_slider":        self.is_slider,
            "slider_size":      self.slider_size if self.is_slider else None,
            "slider_orientation": self.slider_orientation if self.is_slider else None,
            "slider_variable":  self.slider_variable if self.is_slider else None,
            "slider_parent_position": self.slider_parent_position,
        }

    @staticmethod
    def from_dict(d: dict) -> "ActionButton":
        # Support old button_type="slider" → migrate to is_slider=True
        old_button_type = d.get("button_type", "button")
        is_slider = d.get("is_slider", False) or (old_button_type == "slider")
        slider_orientation = d.get("slider_orientation", "vertical")
        slider_variable = d.get("slider_variable", "")
        
        # For old-style sliders, extract variable from outputs if present
        if is_slider and not slider_variable:
            old_slider_cfg = d.get("slider_config", {})
            outputs = old_slider_cfg.get("outputs", [])
            for out in outputs:
                if out.get("type") == "variable":
                    slider_variable = out.get("variable_name", "")
                    break
        
        btn = ActionButton(
            button_id=d.get("button_id", str(uuid.uuid4())),
            label=d.get("label", ""),
            label_color=d.get("label_color", "#FFFFFF"),
            label_font_size=d.get("label_font_size"),   # None → auto-fit; int → explicit px
            icon=d.get("icon"),
            background_color=d.get("background_color", "#000000"),
            state=d.get("state", False),
            state_binding=d.get("state_binding"),
            is_slider=is_slider,
            slider_size=d.get("slider_size", 1) if is_slider else 1,
            slider_orientation=slider_orientation,
            slider_variable=slider_variable,
            slider_parent_position=d.get("slider_parent_position"),
        )
        if "program" in d:
            btn.program = [Block.from_dict(b) for b in d["program"]]
        else:
            # Migrate legacy actions + conditions
            btn.program = _migrate_legacy(
                d.get("actions", []), d.get("conditions", [])
            )
        return btn