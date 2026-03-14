"""
Variable model - mirrors SuchByte.MacroDeck.Variables
Supports Integer, Float, String, Bool types.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class VariableType(str, Enum):
    INTEGER = "Integer"
    FLOAT = "Float"
    STRING = "String"
    BOOL = "Bool"


@dataclass
class Variable:
    name: str
    value: Any
    type: VariableType
    plugin_id: Optional[str] = None  # None = user created
    save: bool = True

    # ------------------------------------------------------------------
    def cast(self) -> Any:
        """Return value cast to its declared type."""
        try:
            if self.type == VariableType.INTEGER:
                return int(self.value)
            if self.type == VariableType.FLOAT:
                return float(self.value)
            if self.type == VariableType.BOOL:
                if isinstance(self.value, str):
                    return self.value.lower() in ("true", "1", "yes")
                return bool(self.value)
            return str(self.value)
        except (ValueError, TypeError):
            return self.value

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "type": self.type.value,
            "plugin_id": self.plugin_id,
        }

    @staticmethod
    def from_dict(d: dict) -> "Variable":
        return Variable(
            name=d["name"],
            value=d["value"],
            type=VariableType(d["type"]),
            plugin_id=d.get("plugin_id"),
        )
