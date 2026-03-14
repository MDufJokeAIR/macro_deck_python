"""
HotReloadWatcher
================
Watches the user plugins directory for file changes and automatically
reloads affected plugins without restarting Macro Deck.

Uses polling (no external dependency) with a configurable interval.
When a plugin's main.py or manifest.json changes:
  1. The old plugin is disabled (disable() called).
  2. All its actions and state are cleared.
  3. The plugin is freshly re-imported and re-enabled.
  4. An optional on_reload callback is invoked (e.g. to push updated
     button layouts to connected WebSocket clients).
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Set

logger = logging.getLogger("macro_deck.hot_reload")


class HotReloadWatcher:
    """
    Polls *plugins_dir* every *interval* seconds.
    Reloads any plugin whose source files have changed since last check.
    """

    def __init__(
        self,
        plugins_dir: Path,
        interval: float = 2.0,
        on_reload: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.plugins_dir = plugins_dir
        self.interval = interval
        self.on_reload = on_reload          # called with package_id after reload

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # plugin_id → {path → mtime}
        self._mtimes: Dict[str, Dict[str, float]] = {}

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="hot-reload"
        )
        self._thread.start()
        logger.info("HotReloadWatcher started (interval=%.1fs dir=%s)",
                    self.interval, self.plugins_dir)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1)
        logger.info("HotReloadWatcher stopped")

    # ── polling loop ──────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self._scan()
            except Exception as exc:
                logger.error("Hot-reload scan error: %s", exc)

    def _scan(self) -> None:
        if not self.plugins_dir.exists():
            return
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            manifest = plugin_dir / "manifest.json"
            if not manifest.exists():
                continue
            watched = [manifest, plugin_dir / "main.py"]
            # Also watch any .py files in the plugin dir
            watched += list(plugin_dir.glob("*.py"))
            pid = plugin_dir.name

            current: Dict[str, float] = {}
            for p in watched:
                if p.exists():
                    current[str(p)] = p.stat().st_mtime

            previous = self._mtimes.get(pid, {})
            if previous and current != previous:
                logger.info("Change detected in plugin %s — reloading", pid)
                self._reload(plugin_dir, pid)
            self._mtimes[pid] = current

    # ── reload ────────────────────────────────────────────────────────

    def _reload(self, plugin_dir: Path, pid: str) -> None:
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.plugins.base import PluginConfiguration

        # 1. Disable old plugin
        old = PluginManager._plugins.get(pid)
        if old:
            try:
                old.disable()
            except Exception as exc:
                logger.warning("disable() error on %s: %s", pid, exc)

        # 2. Remove from registry
        PluginManager._plugins.pop(pid, None)
        PluginManager._actions.pop(pid, None)

        # 3. Remove cached module so Python re-executes it
        mod_key = f"macro_deck_plugin_{pid}"
        sys.modules.pop(mod_key, None)

        # 4. Re-load fresh
        try:
            PluginManager._load_plugin(plugin_dir)
            logger.info("Plugin %s reloaded successfully", pid)
        except Exception as exc:
            logger.error("Reload failed for %s: %s", pid, exc)
            return

        # 5. Notify caller (e.g. push new button layout to clients)
        if self.on_reload:
            try:
                self.on_reload(pid)
            except Exception as exc:
                logger.error("on_reload callback error: %s", exc)
