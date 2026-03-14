"""
Built-in plugin: system variables.
Publishes CPU usage, RAM usage, time/date as Macro Deck variables.
Updates every 5 seconds.
"""
from __future__ import annotations
import logging
import threading
import time
from datetime import datetime
from typing import List, TYPE_CHECKING

from macro_deck_python.models.variable import VariableType
from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction
from macro_deck_python.services.variable_manager import VariableManager

if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton

logger = logging.getLogger("plugin.system_variables")

UPDATE_INTERVAL = 5  # seconds


class Main(IMacroDeckPlugin):
    package_id = "builtin.system_variables"
    name = "System Variables"
    version = "1.0.0"
    author = "MacroDeck"
    description = "Publishes CPU, RAM, time and date as variables"
    can_configure = False

    _stop_event: threading.Event

    def enable(self) -> None:
        self.actions: List[PluginAction] = []
        self._stop_event = threading.Event()
        t = threading.Thread(target=self._loop, daemon=True, name="sys-vars")
        t.start()

    def disable(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._update()
            self._stop_event.wait(UPDATE_INTERVAL)

    def _update(self) -> None:
        pid = self.package_id
        # Time / Date
        now = datetime.now()
        VariableManager.set_value("system_time", now.strftime("%H:%M:%S"), VariableType.STRING, pid, save=False)
        VariableManager.set_value("system_date", now.strftime("%Y-%m-%d"), VariableType.STRING, pid, save=False)
        VariableManager.set_value("system_datetime", now.strftime("%Y-%m-%d %H:%M:%S"), VariableType.STRING, pid, save=False)

        # CPU / RAM - optional
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            VariableManager.set_value("system_cpu_percent", cpu, VariableType.FLOAT, pid, save=False)
            VariableManager.set_value("system_ram_percent", ram, VariableType.FLOAT, pid, save=False)
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("psutil error: %s", exc)
