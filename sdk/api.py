"""
sdk/api.py
==========
Free-function helpers — mirrors the static classes in the C# SDK:
  PluginConfiguration.SetValue / GetValue
  PluginCredentials.SetCredentials / GetPluginCredentials
  VariableManager.SetValue / GetValue
  MacroDeckLogger.*

These can be used by decorator-style plugins that don't hold a plugin instance,
or called from anywhere inside a plugin module.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from macro_deck_python.plugins.base import IMacroDeckPlugin
    from macro_deck_python.models.variable import VariableType


# ── Config ────────────────────────────────────────────────────────────

def get_config(plugin: "IMacroDeckPlugin", key: str, default: str = "") -> str:
    """Get a persisted config value for *plugin*."""
    from macro_deck_python.plugins.base import PluginConfiguration
    return PluginConfiguration.get_value(plugin, key, default)


def set_config(plugin: "IMacroDeckPlugin", key: str, value: str) -> None:
    """Set a persisted config value for *plugin*."""
    from macro_deck_python.plugins.base import PluginConfiguration
    PluginConfiguration.set_value(plugin, key, value)


# ── Credentials ───────────────────────────────────────────────────────

def get_credentials(plugin: "IMacroDeckPlugin") -> List[Dict[str, str]]:
    """
    Return all stored (decrypted) credential sets for *plugin*.
    Each set is a dict of key→value pairs.
    """
    from macro_deck_python.plugins.base import PluginCredentials
    return PluginCredentials.get_plugin_credentials(plugin)


def set_credentials(plugin: "IMacroDeckPlugin", kv: Dict[str, str]) -> None:
    """
    Store a new set of credentials for *plugin* (encrypted with Fernet).
    *kv* is a plain dict, e.g. {"email": "x@x.com", "password": "secret"}.
    """
    from macro_deck_python.plugins.base import PluginCredentials
    PluginCredentials.set_credentials(plugin, kv)


def delete_credentials(plugin: "IMacroDeckPlugin") -> None:
    """Delete all stored credentials for *plugin*."""
    from macro_deck_python.plugins.base import PluginCredentials
    PluginCredentials.delete_credentials(plugin)


# ── Variables ─────────────────────────────────────────────────────────

def set_variable(
    name: str,
    value: Any,
    vtype: "VariableType",
    plugin: Optional["IMacroDeckPlugin"] = None,
    save: bool = True,
) -> None:
    """
    Create or update a Macro Deck variable.
    If *plugin* is None the variable is treated as user-created.

    Parameters
    ----------
    name  : str          Variable name (lowercase, no spaces).
    value : Any          The value to store.
    vtype : VariableType Integer | Float | String | Bool.
    plugin: plugin ref   The owning plugin (makes variable read-only in UI).
    save  : bool         Persist to disk immediately (set False for high-frequency updates).
    """
    from macro_deck_python.services.variable_manager import VariableManager
    VariableManager.set_value(
        name, value, vtype,
        plugin_id=plugin.package_id if plugin else None,
        save=save,
    )


def get_variable(name: str) -> Optional[Any]:
    """Return the current (cast) value of a variable, or None if it doesn't exist."""
    from macro_deck_python.services.variable_manager import VariableManager
    return VariableManager.get_value(name)


# ── Logger ────────────────────────────────────────────────────────────

def log_trace(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
    from macro_deck_python.utils.logger import MacroDeckLogger
    MacroDeckLogger.trace(plugin, message)


def log_info(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
    from macro_deck_python.utils.logger import MacroDeckLogger
    MacroDeckLogger.info(plugin, message)


def log_warning(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
    from macro_deck_python.utils.logger import MacroDeckLogger
    MacroDeckLogger.warning(plugin, message)


def log_error(plugin: Optional["IMacroDeckPlugin"], message: str) -> None:
    from macro_deck_python.utils.logger import MacroDeckLogger
    MacroDeckLogger.error(plugin, message)
