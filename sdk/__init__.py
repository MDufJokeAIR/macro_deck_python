"""
macro_deck_python.sdk
=====================
Public API for writing Macro Deck Python extensions.

Minimal import:
    from macro_deck_python.sdk import PluginBase, action, variable, get_config, set_config

Full import (matches C# plugin API surface):
    from macro_deck_python.sdk import (
        PluginBase, ActionBase,
        VariableType,
        action, on_load, on_delete,
        get_config, set_config,
        get_credentials, set_credentials, delete_credentials,
        set_variable, get_variable,
        log_trace, log_info, log_warning, log_error,
    )
"""

from macro_deck_python.sdk.plugin_base import PluginBase, ActionBase
from macro_deck_python.sdk.decorators import action, on_load, on_delete
from macro_deck_python.sdk.api import (
    get_config, set_config,
    get_credentials, set_credentials, delete_credentials,
    set_variable, get_variable,
    log_trace, log_info, log_warning, log_error,
)
from macro_deck_python.models.variable import VariableType

__all__ = [
    # Classes
    "PluginBase",
    "ActionBase",
    "VariableType",
    # Decorators
    "action",
    "on_load",
    "on_delete",
    # Config helpers
    "get_config",
    "set_config",
    # Credential helpers
    "get_credentials",
    "set_credentials",
    "delete_credentials",
    # Variable helpers
    "set_variable",
    "get_variable",
    # Logger helpers
    "log_trace",
    "log_info",
    "log_warning",
    "log_error",
]
