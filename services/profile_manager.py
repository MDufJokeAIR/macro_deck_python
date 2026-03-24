"""
ProfileManager - load/save/switch profiles.
"""
from __future__ import annotations
import asyncio
import json
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional

from macro_deck_python.models.profile import Profile, Folder
from macro_deck_python.models.action_button import ActionButton, Block

logger = logging.getLogger("macro_deck.profiles")

_PROFILES_FILE = Path.home() / ".macro_deck" / "profiles.json"


class ProfileManager:
    _profiles: Dict[str, Profile] = {}
    _active_profile: Optional[Profile] = None
    # Maps client_id -> profile_id
    _client_profiles: Dict[str, str] = {}
    # Callbacks triggered when active profile changes
    _on_change_callbacks: List[Callable[[str], None]] = []

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = _PROFILES_FILE) -> None:
        if not path.exists():
            default = cls._create_default_profile()
            cls._profiles[default.profile_id] = default
            cls._active_profile = default
            cls.save(path)
            return
        with open(path) as f:
            data = json.load(f)
        for d in data.get("profiles", []):
            try:
                p = Profile.from_dict(d)
                cls._profiles[p.profile_id] = p
            except Exception as exc:
                logger.error("Could not load profile: %s", exc)
        active_id = data.get("active_profile_id")
        if active_id and active_id in cls._profiles:
            cls._active_profile = cls._profiles[active_id]
        elif cls._profiles:
            cls._active_profile = next(iter(cls._profiles.values()))
        else:
            # No profiles loaded, create default
            default = cls._create_default_profile()
            cls._profiles[default.profile_id] = default
            cls._active_profile = default
            cls.save(path)

    @classmethod
    def _create_default_profile(cls) -> Profile:
        """Create the default profile with a single centered button that toggles color."""
        profile = Profile(name="Default")
        # Set grid to 1x1 (single button)
        profile.folder.columns = 1
        profile.folder.rows = 1
        
        # Create a button that changes color when toggled
        btn = ActionButton(
            label="Color",
            background_color="#000000",  # Black
            label_color="#FFFFFF"         # White text
        )
        
        # Add IF block: if button state is true, use white background; else use black
        if_block = Block(
            type="if",
            variable_name="",
            operator="==",
            compare_value="",
            conditions=[],
        )
        
        # Then block (state == true): white background with black text
        then_style = Block(
            type="style",
            background_color="#FFFFFF",
            label_color="#000000"
        )
        if_block.then_blocks.append(then_style)
        
        # Else block (state == false): black background with white text  
        else_style = Block(
            type="style",
            background_color="#000000",
            label_color="#FFFFFF"
        )
        if_block.else_blocks.append(else_style)
        
        btn.program.append(if_block)
        profile.folder.set_button(0, 0, btn)
        
        return profile

    @classmethod
    def save(cls, path: Path = _PROFILES_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active_profile_id": cls._active_profile.profile_id if cls._active_profile else None,
            "profiles": [p.to_dict() for p in cls._profiles.values()],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    async def save_async(cls, path: Path = _PROFILES_FILE) -> None:
        """Async-safe version of save() that runs I/O in a thread pool."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, cls.save, path)

    # ------------------------------------------------------------------
    @classmethod
    def get_all(cls) -> List[Profile]:
        return list(cls._profiles.values())

    @classmethod
    def get_profile(cls, profile_id: str) -> Optional[Profile]:
        return cls._profiles.get(profile_id)

    @classmethod
    def get_active(cls) -> Optional[Profile]:
        return cls._active_profile

    @classmethod
    def set_active(cls, profile_id: str) -> bool:
        p = cls._profiles.get(profile_id)
        if p:
            cls._active_profile = p
            cls.save()
            # Trigger callbacks
            for cb in list(cls._on_change_callbacks):
                try:
                    cb(profile_id)
                except Exception as exc:
                    logger.error("Profile change callback failed: %s", exc)
            return True
        return False

    @classmethod
    async def set_active_async(cls, profile_id: str) -> bool:
        """Async-safe version of set_active()."""
        p = cls._profiles.get(profile_id)
        if p:
            cls._active_profile = p
            await cls.save_async()
            # Trigger callbacks
            for cb in list(cls._on_change_callbacks):
                try:
                    cb(profile_id)
                except Exception as exc:
                    logger.error("Profile change callback failed: %s", exc)
            return True
        return False

    @classmethod
    def on_change(cls, cb: Callable[[str], None]) -> None:
        """Register a callback to be called when active profile changes.
        The callback receives the new profile_id.
        """
        cls._on_change_callbacks.append(cb)

    @classmethod
    def set_client_profile(cls, client_id: str, profile_id: str) -> None:
        cls._client_profiles[client_id] = profile_id

    @classmethod
    def get_client_profile(cls, client_id: str) -> Optional[Profile]:
        pid = cls._client_profiles.get(client_id)
        if pid:
            return cls._profiles.get(pid)
        return cls._active_profile

    # ------------------------------------------------------------------
    @classmethod
    def create_profile(cls, name: str) -> Profile:
        p = Profile(name=name)
        cls._profiles[p.profile_id] = p
        cls.save()
        return p

    @classmethod
    async def create_profile_async(cls, name: str) -> Profile:
        """Async-safe version of create_profile()."""
        p = Profile(name=name)
        cls._profiles[p.profile_id] = p
        await cls.save_async()
        return p

    @classmethod
    def delete_profile(cls, profile_id: str) -> bool:
        if profile_id not in cls._profiles:
            return False
        del cls._profiles[profile_id]
        if cls._active_profile and cls._active_profile.profile_id == profile_id:
            cls._active_profile = next(iter(cls._profiles.values()), None)
        cls.save()
        return True

    @classmethod
    async def delete_profile_async(cls, profile_id: str) -> bool:
        """Async-safe version of delete_profile()."""
        if profile_id not in cls._profiles:
            return False
        del cls._profiles[profile_id]
        if cls._active_profile and cls._active_profile.profile_id == profile_id:
            cls._active_profile = next(iter(cls._profiles.values()), None)
        await cls.save_async()
        return True
