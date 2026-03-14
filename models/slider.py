"""
SliderWidget model
==================
A slider occupies `height` consecutive cells in one column of a Folder.
It replaces those button slots with a continuous input widget rendered
on the client.

Slider modes
------------
variable      Write slider value directly to a VariableManager variable.
key_ramp      Continuously press key_up / key_down at a rate proportional
              to how far the slider is from the centre deadzone.
scroll        Each slider-delta triggers scroll key presses (up/down/left/right).
axis          (Linux) Map value to a real evdev ABS joystick axis via uinput.
key_threshold Press a different key depending on which zone the value falls in.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── zone entry for key_threshold mode ────────────────────────────────
@dataclass
class ThresholdZone:
    min_val: float
    max_val: float
    key: str          # canonical key name from key_map.KEY_MAP
    label: str = ""

    def to_dict(self) -> dict:
        return {"min_val": self.min_val, "max_val": self.max_val,
                "key": self.key, "label": self.label}

    @staticmethod
    def from_dict(d: dict) -> "ThresholdZone":
        return ThresholdZone(min_val=d["min_val"], max_val=d["max_val"],
                             key=d["key"], label=d.get("label",""))


# ── main model ────────────────────────────────────────────────────────
@dataclass
class SliderWidget:
    slider_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # grid position
    column:    int = 0           # 0-based column index in the folder grid
    row_start: int = 0           # first row occupied
    height:    int = 3           # number of rows replaced (≥1)

    # appearance
    label:      str   = "Slider"
    label_color: str  = "#FFFFFF"
    track_color: str  = "#7c83fd"
    thumb_color: str  = "#ffffff"

    # value range
    min_value:     float = 0.0
    max_value:     float = 100.0
    step:          float = 1.0
    current_value: float = 50.0
    initial_value: float = 50.0

    # mode
    mode: str = "variable"       # see module docstring

    # mode=variable
    variable_name: str = ""
    variable_type: str = "Float" # Integer | Float

    # mode=key_ramp
    key_up:          str   = "volume_up"
    key_down:        str   = "volume_down"
    deadzone_low:    float = 40.0   # % of range
    deadzone_high:   float = 60.0   # % of range
    min_rate_ms:     int   = 50     # fastest repeat interval
    max_rate_ms:     int   = 800    # slowest repeat interval

    # mode=scroll
    scroll_key_up:   str = "up"
    scroll_key_down: str = "down"
    scroll_sensitivity: int = 3  # key presses per unit of delta

    # mode=axis (Linux evdev)
    axis_name:   str = "ABS_Y"
    device_name: str = "MacroDeck Analog Slider"

    # mode=key_threshold
    threshold_zones: List[ThresholdZone] = field(default_factory=list)

    # ── serialisation ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "slider_id":    self.slider_id,
            "column":       self.column,
            "row_start":    self.row_start,
            "height":       self.height,
            "label":        self.label,
            "label_color":  self.label_color,
            "track_color":  self.track_color,
            "thumb_color":  self.thumb_color,
            "min_value":    self.min_value,
            "max_value":    self.max_value,
            "step":         self.step,
            "current_value":    self.current_value,
            "initial_value":    self.initial_value,
            "mode":             self.mode,
            "variable_name":    self.variable_name,
            "variable_type":    self.variable_type,
            "key_up":           self.key_up,
            "key_down":         self.key_down,
            "deadzone_low":     self.deadzone_low,
            "deadzone_high":    self.deadzone_high,
            "min_rate_ms":      self.min_rate_ms,
            "max_rate_ms":      self.max_rate_ms,
            "scroll_key_up":    self.scroll_key_up,
            "scroll_key_down":  self.scroll_key_down,
            "scroll_sensitivity": self.scroll_sensitivity,
            "axis_name":        self.axis_name,
            "device_name":      self.device_name,
            "threshold_zones":  [z.to_dict() for z in self.threshold_zones],
        }

    @staticmethod
    def from_dict(d: dict) -> "SliderWidget":
        s = SliderWidget(
            slider_id    = d.get("slider_id", str(uuid.uuid4())),
            column       = d.get("column", 0),
            row_start    = d.get("row_start", 0),
            height       = max(1, d.get("height", 3)),
            label        = d.get("label", "Slider"),
            label_color  = d.get("label_color", "#FFFFFF"),
            track_color  = d.get("track_color", "#7c83fd"),
            thumb_color  = d.get("thumb_color", "#ffffff"),
            min_value    = float(d.get("min_value", 0)),
            max_value    = float(d.get("max_value", 100)),
            step         = float(d.get("step", 1)),
            current_value= float(d.get("current_value", 50)),
            initial_value= float(d.get("initial_value", 50)),
            mode         = d.get("mode", "variable"),
            variable_name= d.get("variable_name", ""),
            variable_type= d.get("variable_type", "Float"),
            key_up       = d.get("key_up", "volume_up"),
            key_down     = d.get("key_down", "volume_down"),
            deadzone_low = float(d.get("deadzone_low", 40)),
            deadzone_high= float(d.get("deadzone_high", 60)),
            min_rate_ms  = int(d.get("min_rate_ms", 50)),
            max_rate_ms  = int(d.get("max_rate_ms", 800)),
            scroll_key_up  = d.get("scroll_key_up", "up"),
            scroll_key_down= d.get("scroll_key_down", "down"),
            scroll_sensitivity = int(d.get("scroll_sensitivity", 3)),
            axis_name    = d.get("axis_name", "ABS_Y"),
            device_name  = d.get("device_name", "MacroDeck Analog Slider"),
        )
        s.threshold_zones = [ThresholdZone.from_dict(z)
                             for z in d.get("threshold_zones", [])]
        return s

    # ── helpers ───────────────────────────────────────────────────────

    @property
    def occupied_cells(self) -> List[str]:
        """Return all 'row_col' keys this slider occupies."""
        return [f"{self.row_start + i}_{self.column}"
                for i in range(self.height)]

    def normalised(self) -> float:
        """Return current_value mapped to [0.0, 1.0]."""
        span = self.max_value - self.min_value
        if span == 0:
            return 0.0
        return (self.current_value - self.min_value) / span

    def clamp(self, value: float) -> float:
        return max(self.min_value, min(self.max_value, value))
