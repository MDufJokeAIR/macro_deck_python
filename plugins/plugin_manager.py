"""
PluginManager
=============
Discovers, loads, validates, enables and tracks all plugins.
Supports:
  - Traditional class-style plugins (ActionBase subclasses)
  - Decorator-style plugins (PluginBase with @action)
  - Per-plugin requirements.txt auto-install
  - Plugin validation before loading
"""
from __future__ import annotations

import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction, PluginConfiguration

logger = logging.getLogger("macro_deck.plugins")


class PluginValidationError(Exception):
    """Raised when a plugin fails pre-load validation."""


class PluginManager:
    _plugins: Dict[str, IMacroDeckPlugin] = {}
    _actions: Dict[str, Dict[str, PluginAction]] = {}
    _plugins_dir: Path = Path.home() / ".macro_deck" / "plugins"

    # ── directory ─────────────────────────────────────────────────────

    @classmethod
    def set_plugins_dir(cls, path: Path) -> None:
        cls._plugins_dir = path

    # ── bulk load ──────────────────────────────────────────────────────

    @classmethod
    def load_all_plugins(cls) -> None:
        cls._plugins_dir.mkdir(parents=True, exist_ok=True)
        for plugin_dir in sorted(cls._plugins_dir.iterdir()):
            if not plugin_dir.is_dir():
                continue
            try:
                cls._load_plugin(plugin_dir)
            except PluginValidationError as exc:
                logger.warning("Plugin validation failed (%s): %s", plugin_dir.name, exc)
            except Exception as exc:
                logger.error("Failed to load plugin from %s: %s", plugin_dir, exc)

    # ── single plugin load ─────────────────────────────────────────────

    @classmethod
    def _load_plugin(cls, plugin_dir: Path) -> None:
        # ── 1. Manifest ───────────────────────────────────────────────
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            return
        with open(manifest_path) as f:
            manifest = json.load(f)

        package_id = manifest.get("package_id", plugin_dir.name)

        # ── 2. Validate ───────────────────────────────────────────────
        cls._validate_manifest(manifest, plugin_dir)

        # ── 3. Auto-install requirements ──────────────────────────────
        requirements_path = plugin_dir / "requirements.txt"
        if requirements_path.exists():
            cls._install_requirements(requirements_path, package_id)

        # ── 4. Restore saved config ───────────────────────────────────
        config_path = plugin_dir / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                PluginConfiguration._store[package_id] = json.load(f)

        # ── 5. Dynamically import main.py ─────────────────────────────
        main_path = plugin_dir / "main.py"
        if not main_path.exists():
            raise PluginValidationError(f"No main.py found in {plugin_dir}")

        mod_key = f"macro_deck_plugin_{package_id}"
        spec = importlib.util.spec_from_file_location(mod_key, main_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_key] = module
        spec.loader.exec_module(module)

        # ── 6. Find the Main class ────────────────────────────────────
        plugin_cls = getattr(module, "Main", None)
        if plugin_cls is None:
            raise PluginValidationError(f"Plugin {package_id} has no 'Main' class in main.py")

        if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, IMacroDeckPlugin)):
            raise PluginValidationError(
                f"Plugin {package_id}: 'Main' must be a subclass of PluginBase or IMacroDeckPlugin"
            )

        # ── 7. Instantiate and enable ─────────────────────────────────
        plugin: IMacroDeckPlugin = plugin_cls()
        plugin.package_id = package_id
        plugin.name        = manifest.get("name", package_id)
        plugin.version     = manifest.get("version", "0.0.0")
        plugin.author      = manifest.get("author", "")
        plugin.description = manifest.get("description", "")

        plugin.enable()

        # ── 8. Index ──────────────────────────────────────────────────
        cls._plugins[package_id] = plugin
        actions_list: List[PluginAction] = getattr(plugin, "actions", []) or []
        cls._actions[package_id] = {}
        for act in actions_list:
            act.plugin = plugin
            if not act.action_id:
                logger.warning("Plugin %s has an action with no action_id — skipped", package_id)
                continue
            cls._actions[package_id][act.action_id] = act

        logger.info(
            "Loaded plugin: %s v%s by %s  (%d action(s))",
            plugin.name, plugin.version, plugin.author, len(cls._actions[package_id]),
        )

    # ── validation ────────────────────────────────────────────────────

    @classmethod
    def _validate_manifest(cls, manifest: dict, plugin_dir: Path) -> None:
        required = ["package_id", "name", "version"]
        for field in required:
            if not manifest.get(field):
                raise PluginValidationError(
                    f"Missing required manifest field '{field}' in {plugin_dir}"
                )
        pid = manifest["package_id"]
        if " " in pid or "/" in pid or "\\" in pid:
            raise PluginValidationError(
                f"Invalid package_id '{pid}' — must not contain spaces or path separators"
            )

    # ── requirements.txt auto-install ─────────────────────────────────

    @classmethod
    def _install_requirements(cls, req_path: Path, package_id: str) -> None:
        logger.info("Installing requirements for %s from %s", package_id, req_path)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_path),
                 "--quiet", "--disable-pip-version-check"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.warning(
                    "pip install for %s exited %d:\n%s",
                    package_id, result.returncode, result.stderr[:500],
                )
            else:
                logger.info("Requirements installed for %s", package_id)
        except subprocess.TimeoutExpired:
            logger.error("pip install timed out for %s", package_id)
        except Exception as exc:
            logger.error("pip install failed for %s: %s", package_id, exc)

    # ── query ─────────────────────────────────────────────────────────

    @classmethod
    def get_plugin(cls, package_id: str) -> Optional[IMacroDeckPlugin]:
        return cls._plugins.get(package_id)

    @classmethod
    def get_action(cls, plugin_id: str, action_id: str) -> Optional[PluginAction]:
        return cls._actions.get(plugin_id, {}).get(action_id)

    @classmethod
    def all_plugins(cls) -> List[IMacroDeckPlugin]:
        return list(cls._plugins.values())

    @classmethod
    def all_actions(cls) -> List[PluginAction]:
        result = []
        for acts in cls._actions.values():
            result.extend(acts.values())
        return result

    # ── unload ────────────────────────────────────────────────────────

    @classmethod
    def unload_plugin(cls, package_id: str) -> bool:
        plugin = cls._plugins.get(package_id)
        if plugin is None:
            return False
        try:
            plugin.disable()
        except Exception as exc:
            logger.warning("disable() error on %s: %s", package_id, exc)
        cls._plugins.pop(package_id, None)
        cls._actions.pop(package_id, None)
        sys.modules.pop(f"macro_deck_plugin_{package_id}", None)
        logger.info("Unloaded plugin: %s", package_id)
        return True

    # ── persist config ────────────────────────────────────────────────

    @classmethod
    def save_plugin_config(cls, plugin: IMacroDeckPlugin) -> None:
        config_path = cls._plugins_dir / plugin.package_id / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(PluginConfiguration._store.get(plugin.package_id, {}), f, indent=2)
