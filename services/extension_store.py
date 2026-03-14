"""
ExtensionStore - mirrors SuchByte.MacroDeck.ExtensionStore
Downloads plugins and icon packs from macrodeck.org/extensionstore
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from macro_deck_python.plugins.plugin_manager import PluginManager

logger = logging.getLogger("macro_deck.extension_store")

STORE_API = "https://macrodeck.org/extensionstore/extensionstore.php"
PLUGINS_DIR = Path.home() / ".macro_deck" / "plugins"
ICONS_DIR = Path.home() / ".macro_deck" / "icons"


@dataclass
class ExtensionEntry:
    package_id: str
    name: str
    author: str
    description: str
    version: str
    download_url: str
    icon_url: str = ""
    extension_type: str = "Plugin"   # Plugin | IconPack
    target_api_version: int = 20
    installed: bool = False
    installed_version: str = ""

    @staticmethod
    def from_dict(d: dict) -> "ExtensionEntry":
        return ExtensionEntry(
            package_id=d.get("package_id", ""),
            name=d.get("name", ""),
            author=d.get("author", ""),
            description=d.get("description", ""),
            version=d.get("version", "0.0.0"),
            download_url=d.get("download_url", ""),
            icon_url=d.get("icon_url", ""),
            extension_type=d.get("type", "Plugin"),
            target_api_version=int(d.get("target_api_version", 20)),
        )


class ExtensionStore:
    _cache: List[ExtensionEntry] = []
    _lock = threading.Lock()

    # ── fetch catalogue ───────────────────────────────────────────────

    @classmethod
    def fetch_extensions(
        cls,
        on_done: Optional[Callable[[List[ExtensionEntry]], None]] = None,
    ) -> List[ExtensionEntry]:
        try:
            with urllib.request.urlopen(STORE_API, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            entries = [ExtensionEntry.from_dict(d) for d in data]
        except Exception as exc:
            logger.error("Could not fetch extension store: %s", exc)
            entries = []

        # Mark installed
        for e in entries:
            e.installed = cls._is_installed(e)
            e.installed_version = cls._installed_version(e)

        with cls._lock:
            cls._cache = entries

        if on_done:
            on_done(entries)
        return entries

    @classmethod
    def fetch_extensions_async(
        cls, on_done: Callable[[List[ExtensionEntry]], None]
    ) -> None:
        t = threading.Thread(
            target=cls.fetch_extensions, kwargs={"on_done": on_done}, daemon=True
        )
        t.start()

    # ── install / uninstall ───────────────────────────────────────────

    @classmethod
    def install(
        cls,
        entry: ExtensionEntry,
        on_progress: Optional[Callable[[int], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> bool:
        try:
            dest_dir = (
                PLUGINS_DIR / entry.package_id
                if entry.extension_type == "Plugin"
                else ICONS_DIR / entry.package_id
            )
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Download zip
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            def _reporthook(count, block_size, total):
                if total > 0 and on_progress:
                    on_progress(int(count * block_size * 100 / total))

            urllib.request.urlretrieve(entry.download_url, tmp_path, _reporthook)
            if on_progress:
                on_progress(100)

            # Extract
            with zipfile.ZipFile(tmp_path) as z:
                z.extractall(dest_dir)
            tmp_path.unlink(missing_ok=True)

            # Reload plugin
            if entry.extension_type == "Plugin":
                PluginManager.load_all_plugins()

            entry.installed = True
            entry.installed_version = entry.version
            logger.info("Installed extension: %s v%s", entry.name, entry.version)
            if on_done:
                on_done(True, "")
            return True
        except Exception as exc:
            logger.error("Install failed for %s: %s", entry.package_id, exc)
            if on_done:
                on_done(False, str(exc))
            return False

    @classmethod
    def install_async(
        cls,
        entry: ExtensionEntry,
        on_progress: Optional[Callable[[int], None]] = None,
        on_done: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        t = threading.Thread(
            target=cls.install,
            kwargs={"entry": entry, "on_progress": on_progress, "on_done": on_done},
            daemon=True,
        )
        t.start()

    @classmethod
    def uninstall(cls, entry: ExtensionEntry) -> bool:
        try:
            dest = (
                PLUGINS_DIR / entry.package_id
                if entry.extension_type == "Plugin"
                else ICONS_DIR / entry.package_id
            )
            if dest.exists():
                shutil.rmtree(dest)
            entry.installed = False
            entry.installed_version = ""
            logger.info("Uninstalled extension: %s", entry.package_id)
            return True
        except Exception as exc:
            logger.error("Uninstall failed: %s", exc)
            return False

    # ── helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _is_installed(entry: ExtensionEntry) -> bool:
        base = PLUGINS_DIR if entry.extension_type == "Plugin" else ICONS_DIR
        return (base / entry.package_id).exists()

    @staticmethod
    def _installed_version(entry: ExtensionEntry) -> str:
        base = PLUGINS_DIR if entry.extension_type == "Plugin" else ICONS_DIR
        manifest = base / entry.package_id / "manifest.json"
        if not manifest.exists():
            return ""
        try:
            with open(manifest) as f:
                return json.load(f).get("version", "")
        except Exception:
            return ""
