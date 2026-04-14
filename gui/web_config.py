"""
Web-based configuration UI server (replaces the WinForms GUI).
Serves an HTML5 single-page app on http://127.0.0.1:8193
Uses aiohttp for a lightweight async HTTP + REST API backend.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

try:
    from aiohttp import web
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False
    web = None  # type: ignore

from macro_deck_python.core.config_manager import ConfigManager
from macro_deck_python.gui.pad_client import get_pad_html
from macro_deck_python.gui.editor_client import get_editor_html
from macro_deck_python.models.action_button import ActionButton
from macro_deck_python.models.profile import Profile, Folder
from macro_deck_python.models.variable import Variable, VariableType
from macro_deck_python.plugins.plugin_manager import PluginManager
from macro_deck_python.services.extension_store import ExtensionStore
from macro_deck_python.services.profile_manager import ProfileManager
from macro_deck_python.services.variable_manager import VariableManager
from macro_deck_python.utils.folder_utils import find_folder as _find_folder

logger = logging.getLogger("macro_deck.webui")

_STATIC_DIR = Path(__file__).parent.parent / "gui" / "static"


# ── live-push helper ──────────────────────────────────────────────────

async def _push_buttons_to_clients(profile_id: str) -> None:
    """After any button mutation, broadcast fresh BUTTONS to all pad clients
    that are currently viewing the affected profile."""
    try:
        from macro_deck_python.websocket.server import _LIVE_INSTANCES
        from macro_deck_python.websocket.protocol import encode
        from macro_deck_python.utils.template import render_label
        from macro_deck_python.services.variable_manager import VariableManager

        profile = ProfileManager.get_profile(profile_id)
        if profile is None:
            return

        folder = profile.folder

        def _resolve_label(label: str) -> str:
            return render_label(label, VariableManager.get_value)

        def _btn_payload(pos, btn) -> dict:
            row, col = pos.split("_")
            base = {
                "button_id":   btn.button_id,
                "position":    pos,
                "row":         int(row),
                "col":         int(col),
            }
            
            # Skip buttons that are occupied by a new-style slider
            if getattr(btn, "slider_parent_position", None):
                return None  # Will be filtered out below
            
            # Check if this is a slider (new system or legacy)
            is_slider = getattr(btn, "is_slider", False)
            old_button_type = getattr(btn, "button_type", "button")
            
            if is_slider:
                # New slider system
                app = btn.resolve_appearance(VariableManager.get_value)
                base.update({
                    "is_slider": True,
                    "slider_size": getattr(btn, "slider_size", 1),
                    "slider_orientation": getattr(btn, "slider_orientation", "vertical"),
                    "slider_variable": getattr(btn, "slider_variable", ""),
                    "label": _resolve_label(app["label"]),
                    "label_color": app["label_color"],
                    "label_font_size": btn.label_font_size,
                    "icon": app["icon"],
                    "background_color": app["background_color"],
                    "has_actions": len(btn.program) > 0,
                })
            elif old_button_type == "slider":
                # Legacy slider system (for backward compat)
                sc = getattr(btn, "slider_config", {})
                base.update({
                    "button_type": "slider",
                    "slider_config": sc,
                    "label": _resolve_label(sc.get("label", "")),
                    "label_color": btn.label_color,
                })
            elif old_button_type == "slider_occupied":
                # Legacy slider occupied cell
                base.update({
                    "button_type": "slider_occupied",
                    "slider_config": getattr(btn, "slider_config", {}),
                })
            else:
                # Regular button
                app = btn.resolve_appearance(VariableManager.get_value)
                base.update({
                    "label": _resolve_label(app["label"]),
                    "label_color": app["label_color"],
                    "label_font_size": btn.label_font_size,
                    "icon": app["icon"],
                    "background_color": app["background_color"],
                    "state": app["state"],
                    "has_actions": len(btn.program) > 0,
                })
            return base

        slider_cells: dict = {}
        for slider in folder.sliders.values():
            for cell in slider.occupied_cells:
                slider_cells[cell] = slider.slider_id

        message = encode(
            "BUTTONS",
            folder_id=folder.folder_id,
            folder_name=folder.name,
            columns=folder.columns,
            rows=folder.rows,
            buttons=[p for p in (_btn_payload(pos, btn) for pos, btn in folder.buttons.items()) if p],
            sub_folders=[{"folder_id": sf.folder_id, "name": sf.name}
                         for sf in folder.sub_folders],
            slider_cells=slider_cells,
        )

        for server in _LIVE_INSTANCES:
            for cid, info in list(server._clients.items()):
                cp = server._clients.get(cid)
                if cp is None:
                    continue
                from macro_deck_python.services.profile_manager import ProfileManager as PM
                client_profile = PM.get_client_profile(cid)
                if client_profile and client_profile.profile_id == profile_id:
                    try:
                        await info.ws.send(message)
                    except Exception:
                        pass
    except Exception as exc:
        logger.warning("_push_buttons_to_clients failed: %s", exc)


# ── REST API handlers ─────────────────────────────────────────────────

async def api_status(request: web.Request) -> web.Response:
    return _json({"status": "running", "config": ConfigManager.as_dict()})


async def api_get_profiles(request: web.Request) -> web.Response:
    profiles = [{"id": p.profile_id, "name": p.name} for p in ProfileManager.get_all()]
    active = ProfileManager.get_active()
    return _json({"profiles": profiles, "active_id": active.profile_id if active else None})


async def api_create_profile(request: web.Request) -> web.Response:
    body = await request.json()
    p = await ProfileManager.create_profile_async(body.get("name", "New Profile"))
    # Pre-create auto-variables for all button positions in the default grid
    for r in range(p.folder.rows):
        for c in range(p.folder.columns):
            await _ensure_button_variable_async(p.name, f"{r}_{c}")
    return _json({"profile_id": p.profile_id, "name": p.name})


async def api_delete_profile(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    profile = ProfileManager.get_profile(pid)
    if profile is None:
        raise web.HTTPNotFound(reason="Profile not found")
    
    # Get all variables associated with this profile
    profile_name = profile.name
    associated_vars = []
    for r in range(profile.folder.rows):
        for c in range(profile.folder.columns):
            var_name = _auto_var_name(profile_name, f"{r}_{c}")
            if VariableManager.get_variable(var_name) is not None:
                associated_vars.append(var_name)
    
    # Check if user requested to delete variables
    delete_vars = False
    try:
        body = await request.json()
        delete_vars = body.get("delete_variables", False)
    except:
        pass  # No body, just proceed with profile deletion
    
    # Delete the profile
    ok = await ProfileManager.delete_profile_async(pid)
    
    # Delete associated variables if requested
    if ok and delete_vars and associated_vars:
        for var_name in associated_vars:
            await VariableManager.delete_async(var_name)
    
    return _json({
        "ok": ok,
        "associated_variables": associated_vars,
        "deleted_variables": associated_vars if delete_vars else []
    })


async def api_set_active_profile(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    ok = await ProfileManager.set_active_async(pid)
    return _json({"ok": ok})


async def api_update_profile(request: web.Request) -> web.Response:
    """PUT /api/profiles/{profile_id} — update name and/or grid dimensions."""
    pid = request.match_info["profile_id"]
    profile = ProfileManager.get_profile(pid)
    if profile is None:
        raise web.HTTPNotFound(reason="Profile not found")
    body = await request.json()
    if "name" in body:
        profile.name = body["name"]
    if "columns" in body:
        try:
            profile.folder.columns = max(1, min(24, int(body["columns"])))
        except (TypeError, ValueError):
            pass
    if "rows" in body:
        try:
            profile.folder.rows = max(1, min(24, int(body["rows"])))
        except (TypeError, ValueError):
            pass
    await ProfileManager.save_async()
    # Ensure auto-variables exist for every cell in the (possibly expanded) grid
    for r in range(profile.folder.rows):
        for c in range(profile.folder.columns):
            await _ensure_button_variable_async(profile.name, f"{r}_{c}")
    return _json({"ok": True, "profile_id": profile.profile_id,
                  "name": profile.name,
                  "columns": profile.folder.columns,
                  "rows": profile.folder.rows})


async def api_get_buttons(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    folder_id = request.rel_url.query.get("folder_id")
    profile = ProfileManager.get_profile(pid)
    if profile is None:
        raise web.HTTPNotFound(reason="Profile not found")
    folder = profile.folder
    if folder_id:
        found = _find_folder(folder, folder_id)
        if found:
            folder = found
    # Inject position into each button dict so the editor JS can use btn.position
    buttons_list = []
    for pos, btn in folder.buttons.items():
        d = btn.to_dict()
        d["position"] = pos
        buttons_list.append(d)
    return _json({
        "folder_id":   folder.folder_id,
        "name":        folder.name,
        "columns":     folder.columns,
        "rows":        folder.rows,
        "buttons":     buttons_list,
        "sub_folders": [{"folder_id": sf.folder_id, "name": sf.name}
                        for sf in folder.sub_folders],
    })


def _auto_var_name(profile_name: str, position: str) -> str:
    """Build the canonical auto-variable name for a button position.
    e.g. profile 'Game', position '0_2'  →  'ProfileGame_x1y3'  (1-based)
    """
    safe = "".join(c for c in profile_name if c.isalnum() or c == "_")
    try:
        row_s, col_s = position.split("_")
        x = int(col_s) + 1   # 1-based column
        y = int(row_s) + 1   # 1-based row
    except (ValueError, AttributeError):
        x, y = 1, 1
    return f"Profile{safe}_x{x}y{y}"


def _ensure_button_variable(profile_name: str, position: str) -> str:
    """Create the auto-variable for this button if it doesn't already exist.
    Returns the variable name."""
    vname = _auto_var_name(profile_name, position)
    if VariableManager.get_variable(vname) is None:
        VariableManager.set_value(vname, False, VariableType.BOOL,
                                  plugin_id=None, save=False)
    return vname


async def _ensure_button_variable_async(profile_name: str, position: str) -> str:
    """Async-safe version of _ensure_button_variable()."""
    vname = _auto_var_name(profile_name, position)
    if VariableManager.get_variable(vname) is None:
        await VariableManager.set_value_async(vname, False, VariableType.BOOL,
                                              plugin_id=None, save=True)
    return vname


async def api_upsert_button(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    profile = ProfileManager.get_profile(pid)
    if profile is None:
        raise web.HTTPNotFound(reason="Profile not found")
    body = await request.json()
    position = body.get("position", "0_0")
    folder_id = body.get("folder_id")
    folder = profile.folder
    if folder_id:
        found = _find_folder(folder, folder_id)
        if found:
            folder = found
    btn = ActionButton.from_dict(body)
    folder.buttons[position] = btn
    await ProfileManager.save_async()
    # Auto-create the positional variable if it doesn't exist yet
    auto_var = await _ensure_button_variable_async(profile.name, position)
    asyncio.ensure_future(_push_buttons_to_clients(pid))
    d = btn.to_dict()
    d["auto_variable"] = auto_var
    return _json(d)


async def api_delete_button(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    position = request.match_info["position"]
    profile = ProfileManager.get_profile(pid)
    if profile is None:
        raise web.HTTPNotFound(reason="Profile not found")
    folder_id = request.rel_url.query.get("folder_id")
    folder = profile.folder
    if folder_id:
        found = _find_folder(folder, folder_id)
        if found:
            folder = found
    folder.buttons.pop(position, None)
    await ProfileManager.save_async()
    asyncio.ensure_future(_push_buttons_to_clients(pid))
    return _json({"ok": True})


async def api_get_variables(request: web.Request) -> web.Response:
    return _json([v.to_dict() for v in VariableManager.get_all()])


async def api_set_variable(request: web.Request) -> web.Response:
    body = await request.json()
    name = body.get("name", "")
    value = body.get("value")
    vtype = VariableType(body.get("type", "String"))
    await VariableManager.set_value_async(name, value, vtype)
    return _json({"ok": True})


async def api_update_variable(request: web.Request) -> web.Response:
    """PUT /api/variables/{name} — rename and/or retype a variable."""
    old_name = request.match_info["name"]
    body = await request.json()
    new_name = body.get("name", old_name).strip()
    new_type_str = body.get("type")

    var = VariableManager.get_variable(old_name)
    if var is None:
        raise web.HTTPNotFound(reason=f"Variable not found: {old_name}")

    new_type = VariableType(new_type_str) if new_type_str else var.type

    if new_name != old_name:
        # Rename: create under new name, delete old
        await VariableManager.set_value_async(new_name, var.value, new_type,
                                      plugin_id=var.plugin_id, save=True)
        await VariableManager.delete_async(old_name)
    else:
        # Just retype
        await VariableManager.set_value_async(old_name, var.value, new_type,
                                      plugin_id=var.plugin_id, save=True)

    return _json({"ok": True, "name": new_name, "type": new_type.value})


async def api_get_auto_variable(request: web.Request) -> web.Response:
    """GET /api/profiles/{profile_id}/buttons/{position}/variable
    Returns (and creates if needed) the auto-variable for a button."""
    pid = request.match_info["profile_id"]
    position = request.match_info["position"]
    profile = ProfileManager.get_profile(pid)
    if profile is None:
        raise web.HTTPNotFound(reason="Profile not found")
    vname = await _ensure_button_variable_async(profile.name, position)
    var = VariableManager.get_variable(vname)
    return _json(var.to_dict() if var else {"name": vname})


async def api_delete_variable(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    await VariableManager.delete_async(name)
    return _json({"ok": True})


async def api_get_plugins(request: web.Request) -> web.Response:
    plugins = [
        {
            "package_id": p.package_id,
            "name": p.name,
            "version": p.version,
            "author": p.author,
            "description": p.description,
            "can_configure": p.can_configure,
        }
        for p in PluginManager.all_plugins()
    ]
    return _json(plugins)


async def api_get_actions(request: web.Request) -> web.Response:
    actions = [
        {
            "plugin_id": a.plugin.package_id if a.plugin else "",
            "action_id": a.action_id,
            "name": a.name,
            "description": a.description,
            "can_configure": a.can_configure,
        }
        for a in PluginManager.all_actions()
    ]
    return _json(actions)


async def api_get_config(request: web.Request) -> web.Response:
    return _json(ConfigManager.as_dict())


async def api_set_config(request: web.Request) -> web.Response:
    body = await request.json()
    for k, v in body.items():
        ConfigManager.set(k, v)
    return _json({"ok": True})


async def api_get_store(request: web.Request) -> web.Response:
    def _serialise(entries):
        return [
            {
                "package_id": e.package_id,
                "name": e.name,
                "author": e.author,
                "description": e.description,
                "version": e.version,
                "type": e.extension_type,
                "icon_url": e.icon_url,
                "installed": e.installed,
                "installed_version": e.installed_version,
            }
            for e in entries
        ]

    entries = ExtensionStore.fetch_extensions()
    return _json(_serialise(entries))


async def api_install_extension(request: web.Request) -> web.Response:
    package_id = request.match_info["package_id"]
    entry = next((e for e in ExtensionStore._cache if e.package_id == package_id), None)
    if entry is None:
        raise web.HTTPNotFound(reason="Extension not found in cache; fetch store first")
    ok = ExtensionStore.install(entry)
    return _json({"ok": ok})


async def api_uninstall_extension(request: web.Request) -> web.Response:
    package_id = request.match_info["package_id"]
    entry = next((e for e in ExtensionStore._cache if e.package_id == package_id), None)
    if entry is None:
        raise web.HTTPNotFound(reason="Extension not found")
    ok = ExtensionStore.uninstall(entry)
    return _json({"ok": ok})


async def api_import_backup(request: web.Request) -> web.Response:
    """Import a MacroDeck backup from uploaded ZIP file."""
    import tempfile
    import zipfile
    import shutil
    from macro_deck_python.plugins.builtin.backup_import.main import BackupConverter
    
    try:
        # Read multipart form data
        reader = await request.multipart()
        field = await reader.next()
        
        if field.name != "backup_file":
            raise ValueError("Expected 'backup_file' field")
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            zip_path = temp_path / "backup.zip"
            extract_path = temp_path / "backup"
            
            # Write uploaded file to temp location
            with open(zip_path, "wb") as f:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    f.write(chunk)
            
            # Extract ZIP
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_path)
            
            # Import from extracted backup
            result = BackupConverter.import_backup(str(extract_path))
            
            # Data is already saved by import_backup and loaded in memory
            # Don't reload from disk as it would overwrite the in-memory state
            
            return _json(result)
            
    except ValueError as e:
        raise web.HTTPBadRequest(reason=str(e))
    except zipfile.BadZipFile:
        raise web.HTTPBadRequest(reason="File is not a valid ZIP archive")
    except Exception as e:
        logger.exception("Backup import error: %s", e)
        raise web.HTTPInternalServerError(reason=f"Import failed: {str(e)}")


# ── serve SPA ─────────────────────────────────────────────────────────

async def serve_index(request: web.Request) -> web.Response:
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return web.FileResponse(index)
    return web.Response(text=_FALLBACK_HTML, content_type="text/html")


# ── CORS middleware ───────────────────────────────────────────────────

async def cors_middleware(app, handler):
    """Permissive CORS — allows the Raspberry Pi browser / any origin."""
    async def middleware(request):
        # Block editor and admin from non-localhost
        if request.path.startswith(('/editor', '/admin')):
            peer = request.remote or ''
            if peer not in ('127.0.0.1', '::1', 'localhost'):
                raise web.HTTPForbidden(
                    reason="Editor is only accessible from localhost for security reasons."
                )
        # Block all mutating API calls (POST/PUT/DELETE) from non-localhost
        _WRITE_METHODS = ('POST', 'PUT', 'DELETE', 'PATCH')
        if request.method in _WRITE_METHODS and request.path.startswith('/api/'):
            peer = request.remote or ''
            if peer not in ('127.0.0.1', '::1', 'localhost'):
                raise web.HTTPForbidden(reason="API writes are only allowed from localhost.")
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            try:
                response = await handler(request)
            except web.HTTPException as exc:
                response = exc
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
    return middleware


# ── missing route handlers ────────────────────────────────────────────

async def serve_pad(request: web.Request) -> web.Response:
    """Serve the button-pad client HTML."""
    return web.Response(text=get_pad_html(), content_type="text/html")


async def serve_editor(request: web.Request) -> web.Response:
    """Serve the button editor HTML."""
    from macro_deck_python.gui.editor_client import get_editor_html
    return web.Response(text=get_editor_html(), content_type="text/html")


async def serve_keyboard_tester(request: web.Request) -> web.Response:
    """Serve the keyboard layout tester HTML."""
    from macro_deck_python.utils.keyboard_tester import create_keyboard_test_html
    return web.Response(text=create_keyboard_test_html(), content_type="text/html")


async def serve_keyboard_mapper(request: web.Request) -> web.Response:
    """Serve the keyboard layout mapper HTML."""
    try:
        mapper_path = Path(__file__).parent.parent.parent / "keyboard_mapper.html"
        if not mapper_path.exists():
            return web.Response(text="keyboard_mapper.html not found", status=404)
        
        with open(mapper_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return web.Response(text=html_content, content_type="text/html")
    except Exception as e:
        logger.error(f"Failed to serve keyboard mapper: {e}")
        return web.Response(text=f"Error: {str(e)}", status=500)


async def api_info(request: web.Request) -> web.Response:
    """Return basic server info (version, websocket port)."""
    from macro_deck_python.core.config_manager import ConfigManager
    return _json({
        "app": "macro_deck_python",
        "ws_port": ConfigManager.get("port", 8191),
        "http_port": ConfigManager.get("web_config_port", 8193),
    })


async def api_keymap_groups(request: web.Request) -> web.Response:
    """Return keyboard key groups for the editor UI."""
    try:
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_GROUPS, KEY_MAP
        result = {}
        for group, keys in KEY_GROUPS.items():
            result[group] = [k for k in keys if k in KEY_MAP]
        return _json({"groups": result})
    except ImportError:
        return _json({"groups": {}})


async def api_keyboard_layout(request: web.Request) -> web.Response:
    """Return keyboard layout information and character mappings."""
    try:
        from macro_deck_python.utils.keyboard_layout import get_current_layout_info
        info = get_current_layout_info()
        return _json(info)
    except Exception as e:
        logger.error(f"Failed to get keyboard layout info: {e}")
        return _json({"error": str(e), "layout": "UNKNOWN"}, status=500)


# ── app factory ───────────────────────────────────────────────────────

def create_app() -> "web.Application":
    if not _AIOHTTP_AVAILABLE:
        raise ImportError("Install aiohttp: pip install aiohttp")
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/profiles", api_get_profiles)
    app.router.add_post("/api/profiles", api_create_profile)
    app.router.add_delete("/api/profiles/{profile_id}", api_delete_profile)
    app.router.add_post("/api/profiles/{profile_id}/activate", api_set_active_profile)
    app.router.add_put("/api/profiles/{profile_id}", api_update_profile)
    app.router.add_get("/api/profiles/{profile_id}/buttons", api_get_buttons)
    app.router.add_post("/api/profiles/{profile_id}/buttons", api_upsert_button)
    app.router.add_delete("/api/profiles/{profile_id}/buttons/{position}", api_delete_button)
    app.router.add_get("/api/variables", api_get_variables)
    app.router.add_post("/api/variables", api_set_variable)
    app.router.add_put("/api/variables/{name}", api_update_variable)
    app.router.add_delete("/api/variables/{name}", api_delete_variable)
    app.router.add_get("/api/profiles/{profile_id}/buttons/{position}/variable",
                       api_get_auto_variable)
    app.router.add_get("/api/plugins", api_get_plugins)
    app.router.add_get("/api/actions", api_get_actions)
    app.router.add_get("/api/config", api_get_config)
    app.router.add_post("/api/config", api_set_config)
    app.router.add_get("/api/store", api_get_store)
    app.router.add_post("/api/store/{package_id}/install", api_install_extension)
    app.router.add_delete("/api/store/{package_id}", api_uninstall_extension)
    app.router.add_post("/api/backup/import", api_import_backup)

    _register_icon_routes(app)
    _register_macrokeys_routes(app)
    _register_slider_routes(app)
    if _STATIC_DIR.exists():
        app.router.add_static("/static", _STATIC_DIR)
    app.router.add_get("/api/info", api_info)
    app.router.add_get("/editor", serve_editor)
    app.router.add_get("/api/keymap/groups", api_keymap_groups)
    app.router.add_get("/api/keyboard/layout", api_keyboard_layout)
    app.router.add_get("/keyboard/tester", serve_keyboard_tester)
    app.router.add_get("/keyboard/mapper", serve_keyboard_mapper)
    app.router.add_get("/pad", serve_pad)
    app.router.add_get("/", serve_pad)      # root → pad client
    app.router.add_get("/admin", serve_index)
    app.router.add_get("/admin/{tail:.*}", serve_index)
    # Return 204 No Content for favicon requests so browsers stop getting
    # a full HTML page (20+ KB) as an "icon".
    app.router.add_get("/favicon.ico", lambda r: web.Response(status=204))
    # Unknown paths that look like static assets return 404 so the browser
    # knows they don't exist.  Paths that have no extension are served as the
    # pad client (keeps deep-link / PWA navigation working without a full SPA
    # router on the server side).
    async def _fallback(request: web.Request) -> web.Response:
        path = request.path.rstrip("/")
        # Anything with a file extension is an asset request → 404
        if "." in path.rsplit("/", 1)[-1]:
            raise web.HTTPNotFound()
        # Everything else → pad client
        return web.Response(text=get_pad_html(), content_type="text/html")
    app.router.add_get("/{tail:.*}", _fallback)
    return app


def _json(data: Any, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, default=str),
        content_type="application/json",
        status=status,
    )


# ── minimal fallback SPA (no static dir needed) ───────────────────────
_FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Deck – Config</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;display:flex;height:100vh}
  nav{width:200px;background:#16213e;padding:20px 0;display:flex;flex-direction:column;gap:4px}
  nav a{padding:12px 20px;cursor:pointer;color:#a0a0c0;text-decoration:none;border-left:3px solid transparent;transition:all .2s}
  nav a.active,nav a:hover{color:#7c83fd;border-left-color:#7c83fd;background:#0f3460}
  main{flex:1;padding:30px;overflow-y:auto}
  h1{font-size:1.5rem;margin-bottom:20px;color:#7c83fd}
  h2{font-size:1.1rem;margin:16px 0 10px;color:#aaa}
  .card{background:#16213e;border-radius:8px;padding:20px;margin-bottom:16px}
  table{width:100%;border-collapse:collapse}
  th,td{padding:8px 12px;text-align:left;border-bottom:1px solid #0f3460}
  th{color:#7c83fd;font-size:.85rem}
  button{padding:8px 16px;background:#7c83fd;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:.9rem}
  button:hover{background:#5a62e0}
  button.danger{background:#e05a5a}
  input,select{background:#0f3460;color:#e0e0e0;border:1px solid #7c83fd44;border-radius:4px;padding:8px 10px;width:100%;margin-bottom:8px}
  .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:.75rem;background:#0f3460;color:#7c83fd}
  #toast{position:fixed;bottom:20px;right:20px;background:#7c83fd;color:#fff;padding:12px 20px;border-radius:8px;display:none}
</style>
</head>
<body>
<nav id="nav">
  <div style="padding:20px;font-size:1.1rem;color:#7c83fd;font-weight:bold">🎛 Macro Deck</div>
  <a href="#" onclick="show('status')" class="active" id="nav-status">Status</a>
  <a href="#" onclick="show('profiles')" id="nav-profiles">Profiles</a>
  <a href="#" onclick="show('variables')" id="nav-variables">Variables</a>
  <a href="#" onclick="show('plugins')" id="nav-plugins">Plugins</a>
  <a href="#" onclick="show('store')" id="nav-store">Extension Store</a>
  <a href="#" onclick="show('backup')" id="nav-backup">Import Backup</a>
  <a href="#" onclick="show('config')" id="nav-config">Settings</a>
</nav>
<main id="main"></main>
<div id="toast"></div>
<script>
const api=async(m,u,b)=>{const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json()};
const apiMultipart=async(url,formData)=>{const r=await fetch(url,{method:'POST',body:formData});return r.json()};
const toast=(msg,err=false)=>{const t=document.getElementById('toast');t.textContent=msg;t.style.background=err?'#e05a5a':'#7c83fd';t.style.display='block';setTimeout(()=>t.style.display='none',3000)};
const show=async(page)=>{
  document.querySelectorAll('nav a').forEach(a=>a.classList.remove('active'));
  document.getElementById('nav-'+page)?.classList.add('active');
  const m=document.getElementById('main');
  if(page==='status'){
    const d=await api('GET','/api/status');
    m.innerHTML=`<h1>Server Status</h1><div class="card"><table><tr><th>Key</th><th>Value</th></tr>${Object.entries(d.config).map(([k,v])=>`<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table></div>`;
  }else if(page==='profiles'){
    const d=await api('GET','/api/profiles');
    const rows=d.profiles.map(p=>`<tr><td>${p.name}</td><td>${p.id}</td><td>${p.id===d.active_id?'<span class="badge">active</span>':''}</td><td><button onclick="activateProfile('${p.id}')">Activate</button> <button class="danger" onclick="deleteProfile('${p.id}')">Delete</button></td></tr>`).join('');
    m.innerHTML=`<h1>Profiles</h1><div class="card"><input id="pname" placeholder="New profile name"><button onclick="createProfile()">+ Create</button></div><div class="card"><table><tr><th>Name</th><th>ID</th><th>Status</th><th>Actions</th></tr>${rows}</table></div>`;
  }else if(page==='variables'){
    const d=await api('GET','/api/variables');
    const rows=d.map(v=>`<tr><td>${v.name}</td><td>${v.type}</td><td>${v.value}</td><td>${v.plugin_id||'<i>user</i>'}</td><td><button class="danger" onclick="deleteVar('${v.name}')">Delete</button></td></tr>`).join('');
    m.innerHTML=`<h1>Variables</h1><div class="card"><input id="vname" placeholder="name"><select id="vtype"><option>String</option><option>Integer</option><option>Float</option><option>Bool</option></select><input id="vval" placeholder="value"><button onclick="createVar()">Set</button></div><div class="card"><table><tr><th>Name</th><th>Type</th><th>Value</th><th>Plugin</th><th></th></tr>${rows}</table></div>`;
  }else if(page==='plugins'){
    const d=await api('GET','/api/plugins');
    const rows=d.map(p=>`<tr><td>${p.name}</td><td>${p.version}</td><td>${p.author}</td><td>${p.description}</td></tr>`).join('');
    m.innerHTML=`<h1>Loaded Plugins</h1><div class="card"><table><tr><th>Name</th><th>Version</th><th>Author</th><th>Description</th></tr>${rows||'<tr><td colspan=4>No plugins loaded</td></tr>'}</table></div>`;
  }else if(page==='store'){
    toast('Fetching extension store…');
    const d=await api('GET','/api/store');
    const rows=d.map(e=>`<tr><td>${e.name}</td><td>${e.type}</td><td>${e.version}</td><td>${e.author}</td><td>${e.installed?`<span class="badge">v${e.installed_version}</span>`:''}</td><td>${e.installed?`<button class="danger" onclick="uninstall('${e.package_id}')">Uninstall</button>`:`<button onclick="install('${e.package_id}')">Install</button>`}</td></tr>`).join('');
    m.innerHTML=`<h1>Extension Store</h1><div class="card"><table><tr><th>Name</th><th>Type</th><th>Version</th><th>Author</th><th>Installed</th><th></th></tr>${rows||'<tr><td colspan=6>No extensions found</td></tr>'}</table></div>`;
  }else if(page==='backup'){
    const preservedProfiles=document.getElementById('imported_profiles_section')?document.getElementById('imported_profiles_section').innerHTML:'';
    m.innerHTML=`<h1>Import MacroDeck Backup</h1><div class="card"><p style="color:#aaa;margin-bottom:16px">Upload a backup ZIP file from the original MacroDeck App to import profiles, buttons, and variables.</p><input type="file" id="backup_file" accept=".zip" style="margin-bottom:16px"><button onclick="importBackup()">Upload & Import</button></div><div id="import_result"></div><div id="imported_profiles_section"></div>`;
    if(preservedProfiles){document.getElementById('imported_profiles_section').innerHTML=preservedProfiles;}else{await restoreBackupsUI();}
  }else if(page==='config'){
    const d=await api('GET','/api/config');
    m.innerHTML=`<h1>Settings</h1><div class="card">${Object.entries(d).map(([k,v])=>`<label style="display:block;margin-bottom:8px;color:#aaa;font-size:.85rem">${k}<input id="cfg_${k}" value="${v}"></label>`).join('')}<button onclick="saveConfig()">Save</button></div>`;
  }
};
window.createProfile=async()=>{const n=document.getElementById('pname').value;if(!n)return;await api('POST','/api/profiles',{name:n});toast('Profile created');show('profiles')};
window.activateProfile=async(id)=>{await api('POST',`/api/profiles/${id}/activate`);toast('Profile activated');show('profiles')};
window.deleteProfile=async(id)=>{const r=await api('GET',`/api/profiles`);const p=r.profiles.find(pr=>pr.id===id);if(!p)return;const confirmed=confirm(`Delete profile "${p.name}"?\n\nThis profile may have associated variables (x1y1, x1y2, etc). Do you want to delete those too?\n\n[OK] = Delete profile and variables\n[Cancel] = Don't delete`);if(!confirmed)return;await api('DELETE',`/api/profiles/${id}`,{delete_variables:true});toast('Deleted');show('profiles')};
window.saveBackupToStorage=async(backupId,backupName,profiles,variables)=>{const backups=JSON.parse(localStorage.getItem('importedBackups')||'{}');backups[backupId]={name:backupName,profiles:profiles,variables:variables};localStorage.setItem('importedBackups',JSON.stringify(backups))};
window.restoreBackupsUI=async()=>{const backups=JSON.parse(localStorage.getItem('importedBackups')||'{}');const profSec=document.getElementById('imported_profiles_section');for(const [backupId,[backupName,data]]of Object.entries(backups).map(e=>[e[0],[e[1].name,e[1]]])){const profList=data.profiles.map(p=>`<div data-profile-id="${p.id}" style="padding:6px 0;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #444"><span>${p.name}</span><button class="danger" style="padding:4px 8px;font-size:0.85rem" onclick="deleteProfileFromBackup('${p.id}')">Delete</button></div>`).join('');const backupContainer=document.createElement('div');backupContainer.id=backupId;backupContainer.className='card';backupContainer.style.marginTop='20px';backupContainer.dataset.importedVars=JSON.stringify(data.variables||[]);backupContainer.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px"><h3 style="margin:0">Imported profiles: ${backupName}</h3><button class="danger" style="padding:4px 8px;font-size:0.85rem" onclick="deleteBackupAll('${backupName}')">Delete All</button></div><div>${profList}</div>`;if(!profSec.querySelector(`#${backupId}`)){profSec.appendChild(backupContainer)}}};
window.deleteProfileFromBackup=async(id)=>{const confirmed=confirm(`Delete this profile?`);if(!confirmed)return;try{await api('DELETE',`/api/profiles/${id}`,{delete_variables:false});toast('Deleted');const profElement=document.querySelector(`[data-profile-id="${id}"]`);if(profElement){const backupContainer=profElement.closest('[id]');profElement.remove();const backups=JSON.parse(localStorage.getItem('importedBackups')||'{}');for(const backup of Object.values(backups)){backup.profiles=backup.profiles.filter(p=>p.id!==id)}localStorage.setItem('importedBackups',JSON.stringify(backups))}}catch(e){alert('Failed to delete: '+e.message)}};
window.deleteBackupAll=async(backupName)=>{const confirmed=confirm(`Delete all profiles from this backup?`);if(!confirmed)return;try{const backupId=backupName.replace(/[^a-zA-Z0-9_-]/g,'_');const backupContainer=document.getElementById(backupId);const profileElements=backupContainer.querySelectorAll('[data-profile-id]');for(const elem of profileElements){const profileId=elem.getAttribute('data-profile-id');await api('DELETE',`/api/profiles/${profileId}`,{delete_variables:true})}const importedVars=backupContainer.dataset.importedVars?JSON.parse(backupContainer.dataset.importedVars):[];for(const varName of importedVars){try{await api('DELETE',`/api/variables/${varName}`)}catch(e){}}profileElements.forEach(e=>e.remove());const backups=JSON.parse(localStorage.getItem('importedBackups')||'{}');delete backups[backupId];localStorage.setItem('importedBackups',JSON.stringify(backups));if(backupContainer.querySelectorAll('[data-profile-id]').length===0){backupContainer.remove()}else{toast('All profiles deleted')}}catch(e){alert('Failed to delete: '+e.message)}};
window.createVar=async()=>{const n=document.getElementById('vname').value,t=document.getElementById('vtype').value,v=document.getElementById('vval').value;await api('POST','/api/variables',{name:n,type:t,value:v});toast('Variable set');show('variables')};
window.deleteVar=async(n)=>{await api('DELETE',`/api/variables/${n}`);toast('Deleted');show('variables')};
window.install=async(id)=>{toast('Installing…');const r=await api('POST',`/api/store/${id}/install`);toast(r.ok?'Installed!':'Install failed',!r.ok);show('store')};
window.uninstall=async(id)=>{const r=await api('DELETE',`/api/store/${id}`);toast(r.ok?'Uninstalled':'Failed',!r.ok);show('store')};
window.importBackup=async()=>{const f=document.getElementById('backup_file').files[0];if(!f)return alert('Please select a file');const backupName=f.name.replace('.zip','');const backupId=backupName.replace(/[^a-zA-Z0-9_-]/g,'_');toast('Uploading & importing...');const fd=new FormData();fd.append('backup_file',f);try{const r=await apiMultipart('/api/backup/import',fd);const res=document.getElementById('import_result');res.innerHTML=`<div class="card" style="margin-top:20px"><h2>Import Results</h2><p>✓ Profiles: ${r.profiles_imported}<br>✓ Variables: ${r.variables_imported}<br>✓ Actions: ${r.actions_converted}</p>${r.warnings.length?`<p style="color:#f0ad4e;margin-top:8px"><strong>⚠ Warnings (${r.warnings.length}):</strong><br>${r.warnings.slice(0,5).map(w=>'  • '+w).join('<br>')}</p>`:''}${r.errors.length?`<p style="color:#e05a5a;margin-top:8px"><strong>✗ Errors (${r.errors.length}):</strong><br>${r.errors.slice(0,5).map(e=>'  • '+e).join('<br>')}</p>`:''}</div>`;if(r.imported_profiles && r.imported_profiles.length>0){await saveBackupToStorage(backupId,backupName,r.imported_profiles,r.imported_variables);await restoreBackupsUI()}toast('Import complete!')}catch(e){alert('Import failed: '+e.message)}};
window.saveConfig=async()=>{const cfg={};document.querySelectorAll('[id^=cfg_]').forEach(i=>{cfg[i.id.replace('cfg_','')]=i.value});await api('POST','/api/config',cfg);toast('Settings saved')};
show('status');
</script>
</body>
</html>"""

# ── icon REST endpoints (appended) ────────────────────────────────────

async def api_list_icons(request: web.Request) -> web.Response:
    from macro_deck_python.services.icon_manager import IconManager
    return _json({
        "user_icons": IconManager.list_user_icons(),
        "packs": IconManager.list_icon_packs(),
    })


async def api_get_icon(request: web.Request) -> web.Response:
    from macro_deck_python.services.icon_manager import IconManager
    icon_id = request.match_info["icon_id"]
    b64 = IconManager.get_icon_b64(icon_id)
    if b64 is None:
        raise web.HTTPNotFound()
    return _json({"icon_id": icon_id, "data": b64})


async def api_upload_icon(request: web.Request) -> web.Response:
    from macro_deck_python.services.icon_manager import IconManager
    reader = await request.multipart()
    field = await reader.next()
    if field is None:
        raise web.HTTPBadRequest(reason="No file uploaded")
    data = await field.read()
    icon_id = IconManager.save_icon(field.filename or "upload", data)
    return _json({"icon_id": icon_id})


async def api_delete_icon(request: web.Request) -> web.Response:
    from macro_deck_python.services.icon_manager import IconManager
    icon_id = request.match_info["icon_id"]
    ok = IconManager.delete_icon(icon_id)
    return _json({"ok": ok})


def _register_icon_routes(app: web.Application) -> None:
    app.router.add_get("/api/icons", api_list_icons)
    app.router.add_get("/api/icons/{icon_id}", api_get_icon)
    app.router.add_post("/api/icons", api_upload_icon)
    app.router.add_delete("/api/icons/{icon_id}", api_delete_icon)


# ── MacroKeys catalogue endpoints (appended) ──────────────────────────

async def api_macrokeys_groups(request: web.Request) -> web.Response:
    """List all key groups."""
    try:
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import GROUPS
        return _json({"groups": GROUPS})
    except ImportError:
        raise web.HTTPNotFound(reason="macro_keys plugin not loaded")


async def api_macrokeys_all_keys(request: web.Request) -> web.Response:
    """Return all keys, grouped."""
    try:
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import BY_GROUP
        result = {}
        for group, keys in BY_GROUP.items():
            result[group] = [
                {"label": k.label, "description": k.description or ""}
                for k in keys
            ]
        return _json(result)
    except ImportError:
        raise web.HTTPNotFound(reason="macro_keys plugin not loaded")


async def api_macrokeys_group(request: web.Request) -> web.Response:
    """Return all keys in a specific group."""
    try:
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import BY_GROUP
        group = request.match_info["group"]
        keys = BY_GROUP.get(group)
        if keys is None:
            raise web.HTTPNotFound(reason=f"Group not found: {group}")
        return _json([{"label": k.label, "description": k.description or ""} for k in keys])
    except ImportError:
        raise web.HTTPNotFound(reason="macro_keys plugin not loaded")


async def api_macrokeys_schema(request: web.Request) -> web.Response:
    """Return the JSON schema for the macro_keys action configuration."""
    try:
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        return _json(MacroKeysAction.config_schema)
    except ImportError:
        raise web.HTTPNotFound(reason="macro_keys plugin not loaded")


def _register_macrokeys_routes(app: web.Application) -> None:
    app.router.add_get("/api/macrokeys/groups",       api_macrokeys_groups)
    app.router.add_get("/api/macrokeys/keys",         api_macrokeys_all_keys)
    app.router.add_get("/api/macrokeys/keys/{group}", api_macrokeys_group)
    app.router.add_get("/api/macrokeys/schema",       api_macrokeys_schema)

# ── slider REST endpoints ─────────────────────────────────────────────

async def api_get_sliders(request: web.Request) -> web.Response:
    from macro_deck_python.models.slider import SliderWidget
    pid = request.match_info["profile_id"]
    from macro_deck_python.services.profile_manager import ProfileManager
    profile = ProfileManager.get_profile(pid)
    if not profile:
        raise web.HTTPNotFound(reason="Profile not found")
    folder_id = request.rel_url.query.get("folder_id")
    folder = profile.folder
    if folder_id:
        found = _find_folder(folder, folder_id)
        if found:
            folder = found
    return _json([s.to_dict() for s in folder.sliders.values()])


async def api_add_slider(request: web.Request) -> web.Response:
    from macro_deck_python.models.slider import SliderWidget
    from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
    pid = request.match_info["profile_id"]
    body = await request.json()
    folder_id = body.pop("folder_id", None)
    try:
        slider = SliderWidget.from_dict(body)
    except Exception as exc:
        raise web.HTTPBadRequest(reason=str(exc))
    ok = SliderManager.add_slider(slider, pid, folder_id)
    return _json({"ok": ok, "slider_id": slider.slider_id})


async def api_update_slider(request: web.Request) -> web.Response:
    from macro_deck_python.models.slider import SliderWidget
    from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
    pid = request.match_info["profile_id"]
    body = await request.json()
    folder_id = body.pop("folder_id", None)
    try:
        slider = SliderWidget.from_dict(body)
    except Exception as exc:
        raise web.HTTPBadRequest(reason=str(exc))
    ok = SliderManager.update_slider(slider, pid, folder_id)
    return _json({"ok": ok})


async def api_delete_slider(request: web.Request) -> web.Response:
    from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
    pid      = request.match_info["profile_id"]
    sid      = request.match_info["slider_id"]
    folder_id = request.rel_url.query.get("folder_id")
    ok = SliderManager.remove_slider(sid, pid, folder_id or None)
    return _json({"ok": ok})


async def api_set_slider_value(request: web.Request) -> web.Response:
    """Directly set a slider value (for testing / automation)."""
    from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
    pid = request.match_info["profile_id"]
    sid = request.match_info["slider_id"]
    body = await request.json()
    value = float(body.get("value", 50))
    slider = SliderManager.apply_change(sid, value)
    if slider is None:
        raise web.HTTPNotFound(reason="Slider not found")
    return _json({"ok": True, "value": slider.current_value})


def _register_slider_routes(app: web.Application) -> None:
    app.router.add_get   ("/api/profiles/{profile_id}/sliders",             api_get_sliders)
    app.router.add_post  ("/api/profiles/{profile_id}/sliders",             api_add_slider)
    app.router.add_put   ("/api/profiles/{profile_id}/sliders/{slider_id}", api_update_slider)
    app.router.add_delete("/api/profiles/{profile_id}/sliders/{slider_id}", api_delete_slider)
    app.router.add_post  ("/api/profiles/{profile_id}/sliders/{slider_id}/value",
                          api_set_slider_value)