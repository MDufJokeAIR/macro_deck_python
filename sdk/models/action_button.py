"""
action_button.py — grid cell models.

Hierarchy
---------
ActionInterface          base dataclass — shared identity + appearance
  ActionButton           pressable button with a Block program
  ActionSlider           analog slider that writes a Float variable
  SliderCell             placeholder for cells occupied by a slider

Both ActionButton and ActionSlider live in Folder.buttons
(Dict[str, ActionInterface]).

ActionInterface.from_dict() is the single deserialisation entry point; it
inspects the ``kind`` field (or legacy ``is_slider`` / ``button_type`` flags)
and returns the right subclass.  Existing JSON profiles are migrated
automatically on load with no manual conversion step.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import uuid


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Block
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class Block:
    type: str  # "action" | "style" | "if"

    plugin_id: str = ""
    action_id: str = ""
    configuration: str = "{}"
    configuration_summary: str = ""

    label: Optional[str] = None
    label_color: Optional[str] = None
    background_color: Optional[str] = None
    icon: Optional[str] = None
    font_size: Optional[str] = None

    variable_name: str = ""
    operator: str = "=="
    compare_value: str = ""
    conditions: List[dict] = field(default_factory=list)
    then_blocks: List["Block"] = field(default_factory=list)
    else_blocks: List["Block"] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.type == "action":
            d.update({"plugin_id": self.plugin_id, "action_id": self.action_id,
                       "configuration": self.configuration,
                       "configuration_summary": self.configuration_summary})
        elif self.type == "style":
            if self.label is not None:            d["label"]            = self.label
            if self.label_color is not None:      d["label_color"]      = self.label_color
            if self.background_color is not None: d["background_color"] = self.background_color
            if self.icon is not None:             d["icon"]             = self.icon
            if self.font_size is not None:        d["font_size"]        = self.font_size
        elif self.type == "if":
            conds = self.conditions if self.conditions else [{
                "variable_name": self.variable_name, "operator": self.operator,
                "compare_value": self.compare_value, "logic": "AND"}]
            d.update({"conditions": conds,
                       "then_blocks": [b.to_dict() for b in self.then_blocks],
                       "else_blocks": [b.to_dict() for b in self.else_blocks]})
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
            b.label = d.get("label"); b.label_color = d.get("label_color")
            b.background_color = d.get("background_color"); b.icon = d.get("icon")
            b.font_size = d.get("font_size")
        elif t == "if":
            if "conditions" in d:
                b.conditions = d["conditions"]
                if b.conditions:
                    fc = b.conditions[0]
                    b.variable_name = fc.get("variable_name", "")
                    b.operator      = fc.get("operator", "==")
                    b.compare_value = fc.get("compare_value", "")
            else:
                b.variable_name = d.get("variable_name", "")
                b.operator      = d.get("operator", "==")
                b.compare_value = d.get("compare_value", "")
                b.conditions = [{"variable_name": b.variable_name,
                                  "operator": b.operator,
                                  "compare_value": b.compare_value,
                                  "logic": "AND"}]
            b.then_blocks = [Block.from_dict(x) for x in d.get("then_blocks", [])]
            b.else_blocks = [Block.from_dict(x) for x in d.get("else_blocks", [])]
        return b


def _migrate_legacy(actions: list, conditions: list) -> List[Block]:
    program: List[Block] = []
    for cond in conditions:
        b = Block(type="if", variable_name=cond.get("variable_name", ""),
                  operator=cond.get("operator", "=="),
                  compare_value=cond.get("compare_value", ""))
        for style_key, acts_key, branch in (
            ("style_true",  "actions_true",  b.then_blocks),
            ("style_false", "actions_false", b.else_blocks),
        ):
            st = cond.get(style_key, {})
            if any(v not in (None, "") for v in st.values()):
                branch.append(Block(type="style",
                                    label=st.get("label") or None,
                                    label_color=st.get("label_color") or None,
                                    background_color=st.get("background_color") or None,
                                    font_size=st.get("font_size") or None))
            for a in cond.get(acts_key, []):
                branch.append(Block(type="action",
                                    plugin_id=a.get("plugin_id",""),
                                    action_id=a.get("action_id",""),
                                    configuration=a.get("configuration","{}")))
        program.append(b)
    for a in actions:
        program.append(Block(type="action",
                             plugin_id=a.get("plugin_id",""),
                             action_id=a.get("action_id",""),
                             configuration=a.get("configuration","{}"),
                             configuration_summary=a.get("configuration_summary","")))
    return program


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ActionInterface  —  shared base
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ActionInterface:
    """
    Base for every grid cell.  Subclasses must set ``kind`` as a class-level
    constant (overriding the dataclass default).

    ``button_id`` is kept as a property alias of ``cell_id`` so all existing
    code that accesses ``btn.button_id`` continues to work without changes.
    """
    cell_id:          str           = field(default_factory=lambda: str(uuid.uuid4()))
    kind:             str           = "base"   # overridden by each subclass
    label:            str           = ""
    label_color:      str           = "#FFFFFF"
    label_font_size:  Optional[int] = None     # None = auto-fit
    icon:             Optional[str] = None
    background_color: str           = "#000000"

    # ── button_id alias ───────────────────────────────────────────────
    @property
    def button_id(self) -> str:
        return self.cell_id

    @button_id.setter
    def button_id(self, v: str) -> None:
        self.cell_id = v

    # ── serialisation helpers ─────────────────────────────────────────
    def _base_dict(self) -> dict:
        return {
            "cell_id":         self.cell_id,
            "kind":            self.kind,
            "label":           self.label,
            "label_color":     self.label_color,
            "label_font_size": self.label_font_size,
            "icon":            self.icon,
            "background_color": self.background_color,
        }

    def to_dict(self) -> dict:
        return self._base_dict()

    @staticmethod
    def from_dict(d: dict) -> "ActionInterface":
        """
        Factory — detects the right subclass from ``kind`` or legacy flags.

        Priority:
          1. ``kind`` field present           → use directly
          2. ``is_slider: true``              → ActionSlider
          3. ``button_type: "slider"``        → ActionSlider
          4. ``slider_parent_position``       → SliderCell
          5. ``button_type: "slider_occupied"`` → SliderCell
          6. everything else                  → ActionButton
        """
        kind = d.get("kind")
        if kind is None:
            if d.get("is_slider") or d.get("button_type") == "slider":
                kind = "slider"
            elif d.get("slider_parent_position") or d.get("button_type") == "slider_occupied":
                kind = "slider_cell"
            else:
                kind = "button"

        if kind == "slider":
            return ActionSlider._from_dict(d)
        if kind == "slider_cell":
            return SliderCell._from_dict(d)
        return ActionButton._from_dict(d)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ActionButton
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ActionButton(ActionInterface):
    """Pressable grid cell.  Executes a Block program when the user taps it."""
    kind:          str            = field(default="button", init=False)
    state:         bool           = False
    state_binding: Optional[str]  = None
    program:       List[Block]    = field(default_factory=list)

    def resolve_appearance(self, get_variable) -> dict:
        from macro_deck_python.utils.condition import evaluate_condition
        result = {"label": self.label, "label_color": self.label_color,
                  "background_color": self.background_color,
                  "icon": self.icon, "state": self.state}

        def _apply(b: Block) -> None:
            if b.label is not None:            result["label"]            = b.label
            if b.label_color is not None:      result["label_color"]      = b.label_color
            if b.background_color is not None: result["background_color"] = b.background_color
            if b.icon is not None:             result["icon"]             = b.icon

        def _eval(b: Block) -> bool:
            conds = b.conditions if b.conditions else [{
                "variable_name": b.variable_name, "operator": b.operator,
                "compare_value": b.compare_value, "logic": "AND"}]
            res = None
            for c in conds:
                m = evaluate_condition(
                    c.get("variable_name",""), c.get("operator","=="),
                    c.get("compare_value",""), button_state=self.state,
                    get_variable=get_variable)
                logic = c.get("logic", "AND")
                res = m if res is None else (res or m if logic == "OR" else res and m)
            return bool(res)

        def _walk(blocks: List[Block]) -> None:
            for b in blocks:
                if b.type == "style":
                    _apply(b)
                elif b.type == "if":
                    try:
                        _walk(b.then_blocks if _eval(b) else b.else_blocks)
                    except Exception:
                        pass

        _walk(self.program)
        return result

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({"state": self.state, "state_binding": self.state_binding,
                   "program": [b.to_dict() for b in self.program]})
        return d

    @staticmethod
    def _from_dict(d: dict) -> "ActionButton":
        btn = ActionButton(
            cell_id          = d.get("cell_id") or d.get("button_id", str(uuid.uuid4())),
            label            = d.get("label", ""),
            label_color      = d.get("label_color", "#FFFFFF"),
            label_font_size  = d.get("label_font_size"),
            icon             = d.get("icon"),
            background_color = d.get("background_color", "#000000"),
            state            = d.get("state", False),
            state_binding    = d.get("state_binding"),
        )
        if "program" in d:
            btn.program = [Block.from_dict(b) for b in d["program"]]
        else:
            btn.program = _migrate_legacy(d.get("actions", []), d.get("conditions", []))
        return btn


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ActionSlider
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ActionSlider(ActionInterface):
    """
    Analog slider.  Spans ``size`` consecutive cells in one column (vertical)
    or row (horizontal).  On every drag event the pad client sends
    SET_VARIABLE with a Float in [min_value, max_value].

    The cells below the head are represented by SliderCell objects so the
    grid dict stays complete.
    """
    kind:        str   = field(default="slider", init=False)
    size:        int   = 3
    orientation: str   = "vertical"
    variable:    str   = ""
    min_value:   float = 0.0
    max_value:   float = 1.0
    step:        float = 0.01
    initial:     float = 0.0

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({"size": self.size, "orientation": self.orientation,
                   "variable": self.variable, "min_value": self.min_value,
                   "max_value": self.max_value, "step": self.step,
                   "initial": self.initial})
        return d

    @staticmethod
    def _from_dict(d: dict) -> "ActionSlider":
        variable = (d.get("variable") or d.get("slider_variable") or "")
        if not variable:
            for out in d.get("slider_config", {}).get("outputs", []):
                if out.get("type") == "variable":
                    variable = out.get("variable_name", "")
                    break
        return ActionSlider(
            cell_id          = d.get("cell_id") or d.get("button_id", str(uuid.uuid4())),
            label            = d.get("label", ""),
            label_color      = d.get("label_color", "#FFFFFF"),
            label_font_size  = d.get("label_font_size"),
            icon             = d.get("icon"),
            background_color = d.get("background_color", "#000000"),
            size             = int(d.get("size") or d.get("slider_size") or 3),
            orientation      = d.get("orientation") or d.get("slider_orientation") or "vertical",
            variable         = variable,
            min_value        = float(d.get("min_value") or d.get("slider_min") or 0.0),
            max_value        = float(d.get("max_value") or d.get("slider_max") or 1.0),
            step             = float(d.get("step") or d.get("slider_step") or 0.01),
            initial          = float(d.get("initial") or d.get("slider_initial") or 0.0),
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SliderCell
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class SliderCell(ActionInterface):
    """
    A grid cell occupied by an ActionSlider whose head is in another cell.
    The server skips it in the BUTTONS payload; the client never renders it.
    """
    kind:            str = field(default="slider_cell", init=False)
    parent_cell_id:  str = ""
    parent_position: str = ""

    def to_dict(self) -> dict:
        d = self._base_dict()
        d.update({"parent_cell_id": self.parent_cell_id,
                   "parent_position": self.parent_position})
        return d

    @staticmethod
    def _from_dict(d: dict) -> "SliderCell":
        return SliderCell(
            cell_id          = d.get("cell_id") or d.get("button_id", str(uuid.uuid4())),
            parent_cell_id   = d.get("parent_cell_id") or d.get("slider_parent_id") or "",
            parent_position  = d.get("parent_position") or d.get("slider_parent_position") or "",
        )
