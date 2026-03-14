"""
Plugin base classes - mirrors SuchByte.MacroDeck.Plugins
Plugins are Python packages that live in ~/.macro_deck/plugins/<package_id>/
Each plugin has a manifest.json and a main.py exporting a class called Main.
"""
from __future__ import annotations
import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton

logger = logging.getLogger("macro_deck.plugins")

# ── Fernet key path ─────────────────────────────────────────────────
_KEY_FILE = Path.home() / ".macro_deck" / ".creds_key"


def _get_fernet():
    """Return a Fernet instance, creating a key on first run."""
    try:
        from cryptography.fernet import Fernet
        if not _KEY_FILE.exists():
            _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            _KEY_FILE.write_bytes(Fernet.generate_key())
            _KEY_FILE.chmod(0o600)
        return Fernet(_KEY_FILE.read_bytes())
    except ImportError:
        return None


# ────────────────────────────────────────────────────────────────────

class IMacroDeckPlugin(ABC):
    """Interface every plugin must satisfy."""
    package_id: str = ""
    name: str = ""
    version: str = "0.0.0"
    author: str = ""
    description: str = ""
    can_configure: bool = False

    @abstractmethod
    def enable(self) -> None:
        """Called once when the plugin is loaded."""

    def disable(self) -> None:
        """Called when the plugin is unloaded (optional)."""

    def open_configurator(self) -> None:
        """Called when the user clicks 'Configure' in the package manager."""


class PluginAction(ABC):
    """One triggerable action provided by a plugin."""
    plugin: Optional[IMacroDeckPlugin] = None
    action_id: str = ""
    name: str = ""
    description: str = ""
    can_configure: bool = False
    configuration: str = ""           # JSON string
    configuration_summary: str = ""

    @abstractmethod
    def trigger(self, client_id: str, action_button: "ActionButton") -> None:
        """Called on button press (or event). Must not block indefinitely."""

    def on_action_button_loaded(self) -> None:
        """Called when the button owning this action is loaded from disk."""

    def on_action_button_delete(self) -> None:
        """Called when the button owning this action is deleted."""


class PluginConfiguration:
    """Simple per-plugin key/value store. Backed by plugin's config.json."""
    _store: Dict[str, Dict[str, str]] = {}

    @classmethod
    def set_value(cls, plugin: IMacroDeckPlugin, key: str, value: str) -> None:
        pid = plugin.package_id
        if pid not in cls._store:
            cls._store[pid] = {}
        cls._store[pid][key] = value

    @classmethod
    def get_value(cls, plugin: IMacroDeckPlugin, key: str, default: str = "") -> str:
        return cls._store.get(plugin.package_id, {}).get(key, default)


class PluginCredentials:
    """
    Encrypted credential store for plugins.
    Uses Fernet symmetric encryption (cryptography package).
    Falls back to plain storage with a warning if cryptography is unavailable.
    Credentials are stored in ~/.macro_deck/credentials/<package_id>.json
    Each value is Fernet-encrypted and base64-encoded.
    """
    _CREDS_DIR = Path.home() / ".macro_deck" / "credentials"

    @classmethod
    def _creds_file(cls, plugin: IMacroDeckPlugin) -> Path:
        return cls._CREDS_DIR / f"{plugin.package_id}.json"

    @classmethod
    def set_credentials(cls, plugin: IMacroDeckPlugin, kv: Dict[str, str]) -> None:
        cls._CREDS_DIR.mkdir(parents=True, exist_ok=True)
        f = _get_fernet()
        existing = cls._load_raw(plugin)

        if f:
            encrypted = {
                k: base64.b64encode(f.encrypt(v.encode())).decode()
                for k, v in kv.items()
            }
        else:
            logger.warning("cryptography not available; storing credentials unencrypted")
            encrypted = dict(kv)

        existing.append(encrypted)
        creds_file = cls._creds_file(plugin)
        creds_file.write_text(json.dumps(existing, indent=2))
        creds_file.chmod(0o600)

    @classmethod
    def get_plugin_credentials(cls, plugin: IMacroDeckPlugin) -> List[Dict[str, str]]:
        f = _get_fernet()
        raw = cls._load_raw(plugin)
        if not f:
            return raw
        result = []
        for entry in raw:
            try:
                decrypted = {
                    k: f.decrypt(base64.b64decode(v)).decode()
                    for k, v in entry.items()
                }
                result.append(decrypted)
            except Exception as exc:
                logger.error("Failed to decrypt credentials entry: %s", exc)
        return result

    @classmethod
    def delete_credentials(cls, plugin: IMacroDeckPlugin) -> None:
        cls._creds_file(plugin).unlink(missing_ok=True)

    @classmethod
    def _load_raw(cls, plugin: IMacroDeckPlugin) -> list:
        path = cls._creds_file(plugin)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
