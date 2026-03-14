"""
Folder utility helpers - extracted from server.py so they are importable
without the websockets dependency.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from macro_deck_python.models.profile import Folder


def find_folder(root: "Folder", folder_id: Optional[str]) -> Optional["Folder"]:
    """BFS search for a folder by id inside a root folder tree."""
    if folder_id is None:
        return None
    queue = [root]
    while queue:
        f = queue.pop(0)
        if f.folder_id == folder_id:
            return f
        queue.extend(f.sub_folders)
    return None
