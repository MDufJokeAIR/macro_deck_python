"""
ProfileManager - load/save/switch profiles.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from macro_deck_python.models.profile import Profile, Folder

logger = logging.getLogger("macro_deck.profiles")

_PROFILES_FILE = Path.home() / ".macro_deck" / "profiles.json"


class ProfileManager:
    _profiles: Dict[str, Profile] = {}
    _active_profile: Optional[Profile] = None
    # Maps client_id -> profile_id
    _client_profiles: Dict[str, str] = {}

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = _PROFILES_FILE) -> None:
        if not path.exists():
            default = Profile(name="Default")
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

    @classmethod
    def save(cls, path: Path = _PROFILES_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active_profile_id": cls._active_profile.profile_id if cls._active_profile else None,
            "profiles": [p.to_dict() for p in cls._profiles.values()],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

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
            return True
        return False

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
    def delete_profile(cls, profile_id: str) -> bool:
        if profile_id not in cls._profiles:
            return False
        del cls._profiles[profile_id]
        if cls._active_profile and cls._active_profile.profile_id == profile_id:
            cls._active_profile = next(iter(cls._profiles.values()), None)
        cls.save()
        return True
