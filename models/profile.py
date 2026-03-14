"""
Profile / Folder model - mirrors SuchByte.MacroDeck.Profiles / Folders
- A Profile has one root Folder.
- Folders can be nested (unlimited depth).
- Each Folder has a grid of ActionButtons indexed by position (row, col).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import uuid

from macro_deck_python.models.action_button import ActionButton


@dataclass
class Folder:
    folder_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Main"
    # key = (row, col) as "row_col" string for JSON serialisation
    buttons: Dict[str, ActionButton] = field(default_factory=dict)
    sub_folders: List["Folder"] = field(default_factory=list)
    columns: int = 5
    rows: int = 3

    # ------------------------------------------------------------------
    def get_button(self, row: int, col: int) -> Optional[ActionButton]:
        return self.buttons.get(f"{row}_{col}")

    def set_button(self, row: int, col: int, btn: ActionButton) -> None:
        self.buttons[f"{row}_{col}"] = btn

    def remove_button(self, row: int, col: int) -> None:
        self.buttons.pop(f"{row}_{col}", None)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "folder_id": self.folder_id,
            "name": self.name,
            "columns": self.columns,
            "rows": self.rows,
            "buttons": {k: v.to_dict() for k, v in self.buttons.items()},
            "sub_folders": [f.to_dict() for f in self.sub_folders],
        }

    @staticmethod
    def from_dict(d: dict) -> "Folder":
        f = Folder(
            folder_id=d.get("folder_id", str(uuid.uuid4())),
            name=d.get("name", "Main"),
            columns=d.get("columns", 5),
            rows=d.get("rows", 3),
        )
        f.buttons = {k: ActionButton.from_dict(v) for k, v in d.get("buttons", {}).items()}
        f.sub_folders = [Folder.from_dict(sf) for sf in d.get("sub_folders", [])]
        return f


@dataclass
class Profile:
    profile_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default"
    folder: Folder = field(default_factory=Folder)

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "folder": self.folder.to_dict(),
        }

    @staticmethod
    def from_dict(d: dict) -> "Profile":
        return Profile(
            profile_id=d.get("profile_id", str(uuid.uuid4())),
            name=d.get("name", "Default"),
            folder=Folder.from_dict(d.get("folder", {})),
        )
