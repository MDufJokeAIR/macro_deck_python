"""
macro_deck_python/__main__.py
Entry point: python -m macro_deck_python [command] [options]

Commands:
  (none)          Start the Macro Deck server (default)
  new-plugin      Scaffold a new Python extension

Start sequence:
  1. Parse CLI args
  2. Load config
  3. Load variables
  4. Load profiles
  5. Load built-in plugins
  6. Load user plugins  (auto-installs requirements.txt per plugin)
  7. Start WebSocket server
  8. Start web config UI
  9. Start hot-reload watcher (user plugins only)
  10. Start update checker
  11. Start system tray
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from macro_deck_python.core.config_manager import ConfigManager
from macro_deck_python.plugins.plugin_manager import PluginManager
from macro_deck_python.services.profile_manager import ProfileManager
from macro_deck_python.services.update_service import UpdateService
from macro_deck_python.services.variable_manager import VariableManager
from macro_deck_python.utils.logger import MacroDeckLogger

logger = logging.getLogger("macro_deck")


# ── Argument parser ───────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="macro-deck",
        description="Macro Deck Python Server",
    )
    sub = root.add_subparsers(dest="command")

    # ── server (default) ─────────────────────────────────────────────
    srv = sub.add_parser("start", help="Start the Macro Deck server (default)")
    _add_server_args(srv)

    # ── new-plugin ───────────────────────────────────────────────────
    np = sub.add_parser("new-plugin", help="Scaffold a new Python extension")
    np.add_argument("name",       help='Human-readable name, e.g. "My Plugin"')
    np.add_argument("--id",       required=True, dest="package_id",
                    help='Package ID, e.g. "me.myplugin"')
    np.add_argument("--author",   default="Unknown")
    np.add_argument("--desc",     default="")
    np.add_argument("--style",    default="decorator", choices=["decorator", "class"])
    np.add_argument("--out",      default=None,
                    help="Output parent directory (default: ~/.macro_deck/plugins)")

    # Allow `python -m macro_deck_python` with no subcommand → start server
    _add_server_args(root)
    return root


def _add_server_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port",        type=int, default=None)
    p.add_argument("--config-port", type=int, default=None)
    p.add_argument("--host",        default=None)
    p.add_argument("--no-tray",     action="store_true")
    p.add_argument("--no-gui",      action="store_true")
    p.add_argument("--no-updates",  action="store_true")
    p.add_argument("--no-hot-reload", action="store_true")
    p.add_argument("--plugins-dir", default=None)
    p.add_argument("--log-level",   default=None,
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])


# ── Server startup ─────────────────────────────────────────────────────

async def _main_async(args: argparse.Namespace) -> None:
    # 1. Config
    ConfigManager.load()
    if getattr(args, "port", None):        ConfigManager.set("port",           args.port)
    if getattr(args, "config_port", None): ConfigManager.set("web_config_port", args.config_port)
    if getattr(args, "host", None):        ConfigManager.set("host",            args.host)

    log_level = getattr(args, "log_level", None) or ConfigManager.get("log_level", "INFO")
    logging.getLogger().setLevel(log_level)

    port        = ConfigManager.get("port",           8191)
    config_port = ConfigManager.get("web_config_port", 8192)
    host        = ConfigManager.get("host",           "0.0.0.0")

    MacroDeckLogger.info(None, f"Macro Deck Python starting — ws://{host}:{port}")

    # 2. Variables
    VariableManager.load()
    MacroDeckLogger.info(None, f"Variables loaded: {len(VariableManager.get_all())}")

    # 3. Profiles
    ProfileManager.load()
    active = ProfileManager.get_active()
    MacroDeckLogger.info(None,
        f"Profiles: {len(ProfileManager.get_all())}  active={active.name if active else 'none'}")

    # 3b. Ensure auto-variables exist for every button position in every profile
    #     (covers profiles created before this feature was added)
    from macro_deck_python.models.variable import VariableType as _VT
    _created = 0
    for _p in ProfileManager.get_all():
        for _r in range(_p.folder.rows):
            for _c in range(_p.folder.columns):
                _pos  = f"{_r}_{_c}"
                _safe = "".join(ch for ch in _p.name if ch.isalnum() or ch == "_")
                _vname = f"Profile{_safe}_x{_c+1}y{_r+1}"
                if VariableManager.get_variable(_vname) is None:
                    VariableManager.set_value(_vname, False, _VT.BOOL,
                                              plugin_id=None, save=False)
                    _created += 1
    if _created:
        VariableManager.save()
        MacroDeckLogger.info(None, f"Auto-variables seeded: {_created}")

    # 4. Built-in plugins
    builtin_dir = Path(__file__).parent / "plugins" / "builtin"
    PluginManager.set_plugins_dir(builtin_dir)
    PluginManager.load_all_plugins()

    # 5. User plugins
    user_plugins_dir = (
        Path(args.plugins_dir) if getattr(args, "plugins_dir", None)
        else Path.home() / ".macro_deck" / "plugins"
    )
    PluginManager.set_plugins_dir(user_plugins_dir)
    PluginManager.load_all_plugins()
    MacroDeckLogger.info(None, f"Plugins loaded: {len(PluginManager.all_plugins())}")

    # 6. Update checker
    if not getattr(args, "no_updates", False) and ConfigManager.get("check_updates", True):
        UpdateService.start()

    # 7. Stop event
    _stop = asyncio.Event()

    # 8. System tray
    if not getattr(args, "no_tray", False):
        try:
            from macro_deck_python.gui.tray import TrayIcon
            TrayIcon(web_config_port=config_port, on_quit=lambda: _stop.set()).start()
        except Exception as exc:
            MacroDeckLogger.warning(None, f"Tray icon unavailable: {exc}")

    # 9. WebSocket server
    from macro_deck_python.websocket.server import MacroDeckServer
    ws_server = MacroDeckServer(host=host, port=port)
    tasks = [asyncio.create_task(ws_server.start())]

    # 10. Web config UI
    if not getattr(args, "no_gui", False) and ConfigManager.get("gui_enabled", True):
        try:
            from aiohttp import web
            from macro_deck_python.gui.web_config import create_app
            runner = web.AppRunner(create_app())
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", config_port).start()
            MacroDeckLogger.info(None, f"Config UI → http://localhost:{config_port}")
        except ImportError:
            MacroDeckLogger.warning(None, "aiohttp not installed — web config UI disabled")
        except Exception as exc:
            MacroDeckLogger.error(None, f"Web config UI error: {exc}")

    # 11. Hot-reload watcher (user plugins only)
    hot_reload_watcher = None
    if not getattr(args, "no_hot_reload", False):
        from macro_deck_python.services.hot_reload import HotReloadWatcher

        def _on_plugin_reload(package_id: str) -> None:
            MacroDeckLogger.info(None, f"Hot-reloaded plugin: {package_id}")

        hot_reload_watcher = HotReloadWatcher(
            plugins_dir=user_plugins_dir,
            interval=2.0,
            on_reload=_on_plugin_reload,
        )
        hot_reload_watcher.start()

    MacroDeckLogger.info(None, "Macro Deck ready ✓")
    MacroDeckLogger.info(None, f"  Button pad  → http://0.0.0.0:{config_port}")
    MacroDeckLogger.info(None, f"  Admin UI    → http://0.0.0.0:{config_port}/admin")
    MacroDeckLogger.info(None, f"  WebSocket   → ws://0.0.0.0:{port}")
    MacroDeckLogger.info(None, "  ⚠ On the Raspberry Pi browser open: ")
    MacroDeckLogger.info(None, f"    http://<this-machine-ip>:{config_port}")

    try:
        await _stop.wait()
    except asyncio.CancelledError:
        pass
    finally:
        MacroDeckLogger.info(None, "Macro Deck shutting down…")
        if hot_reload_watcher:
            hot_reload_watcher.stop()
        VariableManager.save()
        ProfileManager.save()
        UpdateService.stop()


# ── Entry point ────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "new-plugin":
        from macro_deck_python.cli.scaffold import scaffold
        try:
            out = scaffold(
                name=args.name,
                package_id=args.package_id,
                author=args.author,
                description=args.desc,
                style=args.style,
                output_dir=Path(args.out) if args.out else None,
            )
            print(f"\n✅  Plugin scaffolded at:\n   {out}\n")
            print("Next steps:")
            print(f"  1. Edit  {out}/main.py  to implement your actions")
            print(f"  2. Add pip deps to  {out}/requirements.txt")
            print(f"  3. Start Macro Deck — your plugin loads automatically\n")
        except FileExistsError as exc:
            print(f"❌  {exc}", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"❌  Scaffold failed: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            asyncio.run(_main_async(args))
        except KeyboardInterrupt:
            print("\nMacro Deck stopped.")


if __name__ == "__main__":
    main()