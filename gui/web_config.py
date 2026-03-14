"""
Web-based configuration UI server (replaces the WinForms GUI).
Serves an HTML5 single-page app on http://localhost:8192
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
from macro_deck_python.models.action_button import ActionButton, ActionEntry
from macro_deck_python.models.profile import Profile, Folder
from macro_deck_python.models.variable import Variable, VariableType
from macro_deck_python.plugins.plugin_manager import PluginManager
from macro_deck_python.services.extension_store import ExtensionStore
from macro_deck_python.services.profile_manager import ProfileManager
from macro_deck_python.services.variable_manager import VariableManager
from macro_deck_python.utils.folder_utils import find_folder as _find_folder

logger = logging.getLogger("macro_deck.webui")

_STATIC_DIR = Path(__file__).parent.parent / "gui" / "static"


# ── REST API handlers ─────────────────────────────────────────────────

async def api_status(request: web.Request) -> web.Response:
    return _json({"status": "running", "config": ConfigManager.as_dict()})


async def api_get_profiles(request: web.Request) -> web.Response:
    profiles = [{"id": p.profile_id, "name": p.name} for p in ProfileManager.get_all()]
    active = ProfileManager.get_active()
    return _json({"profiles": profiles, "active_id": active.profile_id if active else None})


async def api_create_profile(request: web.Request) -> web.Response:
    body = await request.json()
    p = ProfileManager.create_profile(body.get("name", "New Profile"))
    return _json({"profile_id": p.profile_id, "name": p.name})


async def api_delete_profile(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    ok = ProfileManager.delete_profile(pid)
    return _json({"ok": ok})


async def api_set_active_profile(request: web.Request) -> web.Response:
    pid = request.match_info["profile_id"]
    ok = ProfileManager.set_active(pid)
    return _json({"ok": ok})


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
    return _json(folder.to_dict())


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
    ProfileManager.save()
    return _json(btn.to_dict())


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
    ProfileManager.save()
    return _json({"ok": True})


async def api_get_variables(request: web.Request) -> web.Response:
    return _json([v.to_dict() for v in VariableManager.get_all()])


async def api_set_variable(request: web.Request) -> web.Response:
    body = await request.json()
    name = body.get("name", "")
    value = body.get("value")
    vtype = VariableType(body.get("type", "String"))
    VariableManager.set_value(name, value, vtype)
    return _json({"ok": True})


async def api_delete_variable(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    VariableManager.delete(name)
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


# ── serve SPA ─────────────────────────────────────────────────────────

async def serve_index(request: web.Request) -> web.Response:
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return web.FileResponse(index)
    return web.Response(text=_FALLBACK_HTML, content_type="text/html")


# ── app factory ───────────────────────────────────────────────────────

def create_app() -> "web.Application":
    if not _AIOHTTP_AVAILABLE:
        raise ImportError("Install aiohttp: pip install aiohttp")
    
    # CORS middleware to allow cross-origin requests from phones/tablets
    @web.middleware
    async def cors_middleware(request, handler):
        response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS, PUT"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response
    
    async def handle_options(request):
        return web.Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS, PUT",
                "Access-Control-Allow-Headers": "Content-Type",
            }
        )
    
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_options("/{tail:.*}", handle_options)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/profiles", api_get_profiles)
    app.router.add_post("/api/profiles", api_create_profile)
    app.router.add_delete("/api/profiles/{profile_id}", api_delete_profile)
    app.router.add_post("/api/profiles/{profile_id}/activate", api_set_active_profile)
    app.router.add_get("/api/profiles/{profile_id}/buttons", api_get_buttons)
    app.router.add_post("/api/profiles/{profile_id}/buttons", api_upsert_button)
    app.router.add_delete("/api/profiles/{profile_id}/buttons/{position}", api_delete_button)
    app.router.add_get("/api/variables", api_get_variables)
    app.router.add_post("/api/variables", api_set_variable)
    app.router.add_delete("/api/variables/{name}", api_delete_variable)
    app.router.add_get("/api/plugins", api_get_plugins)
    app.router.add_get("/api/actions", api_get_actions)
    app.router.add_get("/api/config", api_get_config)
    app.router.add_post("/api/config", api_set_config)
    app.router.add_get("/api/store", api_get_store)
    app.router.add_post("/api/store/{package_id}/install", api_install_extension)
    app.router.add_delete("/api/store/{package_id}", api_uninstall_extension)

    _register_icon_routes(app)
    _register_macrokeys_routes(app)
    if _STATIC_DIR.exists():
        app.router.add_static("/static", _STATIC_DIR)
    app.router.add_get("/{tail:.*}", serve_index)
    return app


def _json(data: Any) -> web.Response:
    return web.Response(
        text=json.dumps(data, default=str),
        content_type="application/json",
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
  <a href="#" onclick="show('config')" id="nav-config">Settings</a>
</nav>
<main id="main"></main>
<div id="toast"></div>
<script>
const api=async(m,u,b)=>{const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):undefined});return r.json()};
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
  }else if(page==='config'){
    const d=await api('GET','/api/config');
    m.innerHTML=`<h1>Settings</h1><div class="card">${Object.entries(d).map(([k,v])=>`<label style="display:block;margin-bottom:8px;color:#aaa;font-size:.85rem">${k}<input id="cfg_${k}" value="${v}"></label>`).join('')}<button onclick="saveConfig()">Save</button></div>`;
  }
};
window.createProfile=async()=>{const n=document.getElementById('pname').value;if(!n)return;await api('POST','/api/profiles',{name:n});toast('Profile created');show('profiles')};
window.activateProfile=async(id)=>{await api('POST',`/api/profiles/${id}/activate`);toast('Profile activated');show('profiles')};
window.deleteProfile=async(id)=>{if(!confirm('Delete?'))return;await api('DELETE',`/api/profiles/${id}`);toast('Deleted');show('profiles')};
window.createVar=async()=>{const n=document.getElementById('vname').value,t=document.getElementById('vtype').value,v=document.getElementById('vval').value;await api('POST','/api/variables',{name:n,type:t,value:v});toast('Variable set');show('variables')};
window.deleteVar=async(n)=>{await api('DELETE',`/api/variables/${n}`);toast('Deleted');show('variables')};
window.install=async(id)=>{toast('Installing…');const r=await api('POST',`/api/store/${id}/install`);toast(r.ok?'Installed!':'Install failed',!r.ok);show('store')};
window.uninstall=async(id)=>{const r=await api('DELETE',`/api/store/${id}`);toast(r.ok?'Uninstalled':'Failed',!r.ok);show('store')};
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
