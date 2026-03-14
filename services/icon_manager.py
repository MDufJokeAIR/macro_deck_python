"""
IconManager - mirrors SuchByte.MacroDeck.Icons.IconManager
Manages button icons:
  - User-uploaded PNG files stored in ~/.macro_deck/icons/
  - Icon packs installed from the Extension Store
  - Base64-encoded inline icons attached to buttons
  - Returns icons as base64 PNG strings for WebSocket transport
"""
from __future__ import annotations
import base64
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger("macro_deck.icons")

_ICONS_DIR  = Path.home() / ".macro_deck" / "icons"
_PACKS_DIR  = Path.home() / ".macro_deck" / "icon_packs"
_CACHE_DIR  = Path.home() / ".macro_deck" / ".icon_cache"
_PLACEHOLDER_B64: Optional[str] = None   # lazy-generated


def _ensure_dirs() -> None:
    for d in (_ICONS_DIR, _PACKS_DIR, _CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _make_placeholder() -> str:
    """Generate a tiny 32×32 grey PNG as base64 (no Pillow needed)."""
    # Minimal valid 1×1 grey PNG
    _GREY_PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    return _GREY_PNG_B64


class IconManager:
    # icon_id → base64 PNG string (in-memory LRU-ish cache, max 500 entries)
    _cache: Dict[str, str] = {}
    _MAX_CACHE = 500

    # ── load / store user icons ──────────────────────────────────────

    @classmethod
    def save_icon(cls, name: str, data: bytes, pack_id: Optional[str] = None) -> str:
        """
        Persist a PNG file and return its icon_id.
        icon_id = sha256 of file content (content-addressable).
        """
        _ensure_dirs()
        icon_id = hashlib.sha256(data).hexdigest()[:16]
        dest_dir = _PACKS_DIR / pack_id if pack_id else _ICONS_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{icon_id}.png"
        if not dest.exists():
            dest.write_bytes(data)
            logger.debug("Saved icon %s (%d bytes)", icon_id, len(data))
        return icon_id

    @classmethod
    def get_icon_b64(cls, icon_id: str) -> Optional[str]:
        """
        Return a base64-encoded PNG string for the given icon_id.
        Searches user icons first, then icon packs.
        Returns a placeholder if not found.
        """
        if icon_id in cls._cache:
            return cls._cache[icon_id]

        # Search user icons
        candidate = _ICONS_DIR / f"{icon_id}.png"
        if candidate.exists():
            return cls._cache_and_return(icon_id, candidate.read_bytes())

        # Search icon packs
        for pack_dir in _PACKS_DIR.iterdir():
            if not pack_dir.is_dir():
                continue
            p = pack_dir / f"{icon_id}.png"
            if p.exists():
                return cls._cache_and_return(icon_id, p.read_bytes())

        logger.debug("Icon not found: %s", icon_id)
        return _make_placeholder()

    @classmethod
    def delete_icon(cls, icon_id: str) -> bool:
        path = _ICONS_DIR / f"{icon_id}.png"
        if path.exists():
            path.unlink()
            cls._cache.pop(icon_id, None)
            return True
        return False

    # ── icon packs ───────────────────────────────────────────────────

    @classmethod
    def list_icon_packs(cls) -> List[str]:
        _ensure_dirs()
        return [d.name for d in _PACKS_DIR.iterdir() if d.is_dir()]

    @classmethod
    def delete_icon_pack(cls, pack_id: str) -> bool:
        pack_dir = _PACKS_DIR / pack_id
        if pack_dir.exists():
            shutil.rmtree(pack_dir)
            # Invalidate cache entries from this pack
            cls._cache.clear()
            return True
        return False

    @classmethod
    def list_icons_in_pack(cls, pack_id: str) -> List[str]:
        pack_dir = _PACKS_DIR / pack_id
        if not pack_dir.is_dir():
            return []
        return [p.stem for p in pack_dir.glob("*.png")]

    # ── inline base64 icons (attached directly to buttons) ───────────

    @staticmethod
    def is_inline(icon_value: Optional[str]) -> bool:
        """Return True if icon_value is already a base64 data string."""
        if not icon_value:
            return False
        return icon_value.startswith("data:image") or len(icon_value) > 64

    @staticmethod
    def to_data_url(b64: str) -> str:
        if b64.startswith("data:"):
            return b64
        return f"data:image/png;base64,{b64}"

    # ── cache helpers ─────────────────────────────────────────────────

    @classmethod
    def _cache_and_return(cls, icon_id: str, data: bytes) -> str:
        b64 = base64.b64encode(data).decode()
        if len(cls._cache) >= cls._MAX_CACHE:
            # Evict oldest key
            cls._cache.pop(next(iter(cls._cache)))
        cls._cache[icon_id] = b64
        return b64

    # ── list all user icons ───────────────────────────────────────────

    @classmethod
    def list_user_icons(cls) -> List[str]:
        _ensure_dirs()
        return [p.stem for p in _ICONS_DIR.glob("*.png")]
