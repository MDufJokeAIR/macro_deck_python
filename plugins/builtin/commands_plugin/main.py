"""
Built-in plugin: system command / shell actions.
  - Run Command       : execute any shell command
  - Open URL          : open a URL in the default browser
  - Delay             : wait N milliseconds
  - Toggle Variable   : flip a Bool variable
  - Set Variable      : set any variable to a fixed value
  - Switch Profile    : switch to a different profile
"""
from __future__ import annotations
import json, logging, subprocess, time, webbrowser
from typing import List, TYPE_CHECKING
from macro_deck_python.models.variable import VariableType
from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction
from macro_deck_python.services.variable_manager import VariableManager
from macro_deck_python.services.profile_manager import ProfileManager
if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton
logger = logging.getLogger("plugin.commands")

class RunCommandAction(PluginAction):
    action_id = "run_command"; name = "Run Command"
    description = "Execute a shell command"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        cmd = cfg.get("command", ""); wait = cfg.get("wait", False)
        if not cmd: return
        try:
            if wait:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                logger.info("Command exited %d: %s", r.returncode, cmd)
            else:
                subprocess.Popen(cmd, shell=True)
        except Exception as exc:
            logger.error("RunCommandAction: %s", exc)

class OpenUrlAction(PluginAction):
    action_id = "open_url"; name = "Open URL"
    description = "Open a URL in the default browser"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        url = cfg.get("url", "")
        if url: webbrowser.open(url)

class DelayAction(PluginAction):
    action_id = "delay"; name = "Delay"
    description = "Wait N milliseconds"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        time.sleep(int(cfg.get("milliseconds", 500)) / 1000.0)

class ToggleVariableAction(PluginAction):
    action_id = "toggle_variable"; name = "Toggle Variable"
    description = "Flip a Bool variable"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        name = cfg.get("variable_name", "")
        if not name: return
        new_val = not bool(VariableManager.get_value(name))
        VariableManager.set_value(name, new_val, VariableType.BOOL,
            plugin_id=self.plugin.package_id if self.plugin else None, save=True)

class SetVariableAction(PluginAction):
    action_id = "set_variable"; name = "Set Variable"
    description = "Set any variable to a fixed value"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        name = cfg.get("variable_name", "")
        value = cfg.get("value", "")
        vtype_str = cfg.get("type", "String")
        if not name: return
        try: vtype = VariableType(vtype_str)
        except ValueError: vtype = VariableType.STRING
        VariableManager.set_value(name, value, vtype,
            plugin_id=self.plugin.package_id if self.plugin else None, save=True)

class SwitchProfileAction(PluginAction):
    action_id = "switch_profile"; name = "Switch Profile"
    description = "Switch to a different profile"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        profile_id = cfg.get("profile_id", "")
        if not profile_id:
            logger.warning("SwitchProfileAction: no profile_id in configuration")
            return
        ok = ProfileManager.set_active(profile_id)
        if ok:
            logger.info("Switched to profile: %s", profile_id)
        else:
            logger.error("SwitchProfileAction: profile not found: %s", profile_id)

class Main(IMacroDeckPlugin):
    package_id = "builtin.commands"; name = "Commands"
    version = "1.0.0"; author = "MacroDeck"
    description = "Run commands, open URLs, delay, toggle/set variables"
    can_configure = False
    def enable(self):
        self.actions: List[PluginAction] = [
            RunCommandAction(), OpenUrlAction(), DelayAction(),
            ToggleVariableAction(), SetVariableAction(), SwitchProfileAction(),
        ]
