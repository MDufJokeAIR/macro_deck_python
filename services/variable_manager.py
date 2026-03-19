"""
VariableManager - mirrors SuchByte.MacroDeck.Variables.VariableManager
Thread-safe store with change events broadcast to connected clients.
"""
from __future__ import annotations
import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from macro_deck_python.models.variable import Variable, VariableType

logger = logging.getLogger("macro_deck.variables")

_VARIABLES_FILE = Path.home() / ".macro_deck" / "variables.json"


class VariableManager:
    _lock = threading.Lock()
    _variables: Dict[str, Variable] = {}
    _on_change_callbacks: List[Callable[[Variable], None]] = []

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = _VARIABLES_FILE) -> None:
        if not path.exists():
            return
        with open(path) as f:
            data = json.load(f)
        with cls._lock:
            for d in data:
                try:
                    v = Variable.from_dict(d)
                    cls._variables[v.name] = v
                except Exception as exc:
                    logger.error("Could not load variable: %s", exc)

    @classmethod
    def save(cls, path: Path = _VARIABLES_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with cls._lock:
            data = [v.to_dict() for v in cls._variables.values() if v.save]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    async def save_async(cls, path: Path = _VARIABLES_FILE) -> None:
        """Async-safe version of save() that runs I/O in a thread pool."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, cls.save, path)

    # ------------------------------------------------------------------
    @classmethod
    def set_value(
        cls,
        name: str,
        value: Any,
        vtype: VariableType,
        plugin_id: Optional[str] = None,
        save: bool = True,
    ) -> None:
        with cls._lock:
            v = cls._variables.get(name)
            if v is None:
                v = Variable(name=name, value=value, type=vtype, plugin_id=plugin_id, save=save)
                cls._variables[name] = v
            else:
                v.value = value
                v.type = vtype
                v.save = save
        for cb in list(cls._on_change_callbacks):
            try:
                cb(v)
            except Exception as exc:
                logger.error("Variable change callback error: %s", exc)
        if save:
            cls.save()

    @classmethod
    async def set_value_async(
        cls,
        name: str,
        value: Any,
        vtype: VariableType,
        plugin_id: Optional[str] = None,
        save: bool = True,
    ) -> None:
        """Async-safe version of set_value()."""
        with cls._lock:
            v = cls._variables.get(name)
            if v is None:
                v = Variable(name=name, value=value, type=vtype, plugin_id=plugin_id, save=save)
                cls._variables[name] = v
            else:
                v.value = value
                v.type = vtype
                v.save = save
        for cb in list(cls._on_change_callbacks):
            try:
                cb(v)
            except Exception as exc:
                logger.error("Variable change callback error: %s", exc)
        if save:
            await cls.save_async()

    @classmethod
    def get_value(cls, name: str) -> Optional[Any]:
        with cls._lock:
            v = cls._variables.get(name)
        return v.cast() if v else None

    @classmethod
    def get_variable(cls, name: str) -> Optional[Variable]:
        with cls._lock:
            return cls._variables.get(name)

    @classmethod
    def get_all(cls) -> List[Variable]:
        with cls._lock:
            return list(cls._variables.values())

    @classmethod
    def delete(cls, name: str) -> None:
        with cls._lock:
            cls._variables.pop(name, None)
        cls.save()

    @classmethod
    async def delete_async(cls, name: str) -> None:
        """Async-safe version of delete()."""
        with cls._lock:
            cls._variables.pop(name, None)
        await cls.save_async()

    # ------------------------------------------------------------------
    @classmethod
    def on_change(cls, cb: Callable[[Variable], None]) -> None:
        cls._on_change_callbacks.append(cb)
