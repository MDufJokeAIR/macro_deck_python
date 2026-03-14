"""
MacroDeck WebSocket Server.
Listens on 0.0.0.0:8191 (default).
Every connected phone/tablet/browser is a "client".
"""
from __future__ import annotations
import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional, Set

# websockets is imported lazily inside start() so the rest of the module
# (MacroDeckServer, ClientInfo) can be imported for testing without it installed.
try:
    import websockets as _websockets
    from websockets.server import WebSocketServerProtocol
    _WEBSOCKETS_AVAILABLE = True
except ImportError:
    _websockets = None  # type: ignore
    _WEBSOCKETS_AVAILABLE = False
    # Use a dummy type annotation placeholder for type checkers
    class WebSocketServerProtocol:  # type: ignore
        pass

from macro_deck_python.models.variable import VariableType
from macro_deck_python.services.action_executor import execute_button
from macro_deck_python.services.profile_manager import ProfileManager
from macro_deck_python.services.variable_manager import VariableManager
from macro_deck_python.utils.template import render_label
from macro_deck_python.utils.folder_utils import find_folder as _find_folder
from macro_deck_python.websocket.protocol import decode, encode

logger = logging.getLogger("macro_deck.websocket")

DEFAULT_PORT = 8191
API_VERSION = 20   # matches Macro Deck 2.x wire protocol version


class ClientInfo:
    def __init__(self, ws: "WebSocketServerProtocol", client_id: str):
        self.ws = ws
        self.client_id = client_id
        self.device_type: str = "unknown"
        self.api_version: int = 0
        self.profile_id: Optional[str] = None


class MacroDeckServer:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._clients: Dict[str, ClientInfo] = {}   # client_id → ClientInfo
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Register variable-change hook to push updates to all clients
        VariableManager.on_change(self._on_variable_changed)

    # ── connection lifecycle ──────────────────────────────────────────

    async def handler(self, ws: "WebSocketServerProtocol", path: str) -> None:
        # Capture event loop on first connection
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        
        client_id = str(uuid.uuid4())
        info = ClientInfo(ws, client_id)
        self._clients[client_id] = info
        logger.info("Client connected: %s  (total: %d)", client_id, len(self._clients))

        try:
            await ws.send(encode("CONNECTED", client_id=client_id))
            async for raw in ws:
                await self._handle_message(info, raw)
        except Exception as exc:
            logger.debug("Client %s disconnected: %s", client_id, exc)
        finally:
            self._clients.pop(client_id, None)
            logger.info("Client disconnected: %s  (total: %d)", client_id, len(self._clients))

    # ── message dispatch ──────────────────────────────────────────────

    async def _handle_message(self, info: ClientInfo, raw: str) -> None:
        try:
            msg = decode(raw)
        except json.JSONDecodeError:
            await info.ws.send(encode("ERROR", message="Invalid JSON"))
            return

        method = msg.get("method", "")
        logger.debug("← %s  %s", info.client_id[:8], method)

        dispatch = {
            "CONNECT":               self._on_connect,
            "CONNECTED":             self._on_connect,  # C# client sends CONNECTED to identify
            "BUTTON_PRESS":          self._on_button_press,
            "GET_BUTTONS":           self._on_get_buttons,
            "GET_PROFILES":          self._on_get_profiles,
            "SET_PROFILE":           self._on_set_profile,
            "GET_VARIABLES":         self._on_get_variables,
            "SET_VARIABLE":          self._on_set_variable,
            "GET_CONNECTED_CLIENTS": self._on_get_connected_clients,
            "PING":                  self._on_ping,
        }

        handler = dispatch.get(method)
        if handler:
            await handler(info, msg)
        else:
            await info.ws.send(encode("ERROR", message=f"Unknown method: {method}"))

    # ── individual handlers ───────────────────────────────────────────

    async def _on_connect(self, info: ClientInfo, msg: dict) -> None:
        info.device_type = msg.get("device_type", "unknown")
        # Ensure api_version is an integer
        api_version = msg.get("api_version", 0)
        info.api_version = int(api_version) if isinstance(api_version, str) else api_version
        
        info.profile_id = msg.get("profile_id")
        if info.profile_id:
            ProfileManager.set_client_profile(info.client_id, info.profile_id)
        
        # Send full initialization sequence
        # 1. Send available profiles
        await self._on_get_profiles(info, {})
        
        # 2. Send all variables
        await self._on_get_variables(info, {})
        
        # 3. Send button layout
        await self._send_buttons(info)

    async def _on_button_press(self, info: ClientInfo, msg: dict) -> None:
        profile = ProfileManager.get_client_profile(info.client_id)
        if profile is None:
            await info.ws.send(encode("ERROR", message="No active profile"))
            return

        folder_id = msg.get("folder_id")
        position = msg.get("position", "")   # "row_col"
        button_id = msg.get("button_id")

        folder = _find_folder(profile.folder, folder_id)
        if folder is None:
            folder = profile.folder

        # Look up button by position or id
        btn = None
        if position:
            btn = folder.buttons.get(position)
        if btn is None and button_id:
            btn = next((b for b in folder.buttons.values() if b.button_id == button_id), None)

        if btn is None:
            await info.ws.send(encode("ERROR", message="Button not found"))
            return

        # Toggle state if state-binding not set
        if btn.state_binding is None:
            btn.state = not btn.state
            ProfileManager.save()
        else:
            # State is driven by variable; nothing to toggle manually
            pass

        # Broadcast updated state to all clients
        await self._broadcast(encode("BUTTON_STATE", button_id=btn.button_id, state=btn.state))

        # Execute actions in background
        execute_button(btn, info.client_id)

    async def _on_get_buttons(self, info: ClientInfo, msg: dict) -> None:
        await self._send_buttons(info, folder_id=msg.get("folder_id"))

    async def _on_get_profiles(self, info: ClientInfo, msg: dict) -> None:
        profiles = ProfileManager.get_all()
        active = ProfileManager.get_active()
        payload = {
            "profiles": [{"id": p.profile_id, "name": p.name} for p in profiles],
            "active_id": active.profile_id if active else None,
        }
        await info.ws.send(encode("PROFILES", **payload))

    async def _on_set_profile(self, info: ClientInfo, msg: dict) -> None:
        profile_id = msg.get("profile_id", "")
        ok = ProfileManager.set_active(profile_id)
        if ok:
            ProfileManager.set_client_profile(info.client_id, profile_id)
            await self._send_buttons(info)
        else:
            await info.ws.send(encode("ERROR", message=f"Profile not found: {profile_id}"))

    async def _on_get_variables(self, info: ClientInfo, msg: dict) -> None:
        variables = [v.to_dict() for v in VariableManager.get_all()]
        await info.ws.send(encode("VARIABLES", variables=variables))

    async def _on_set_variable(self, info: ClientInfo, msg: dict) -> None:
        name = msg.get("name", "")
        value = msg.get("value")
        vtype_str = msg.get("type", "String")
        try:
            vtype = VariableType(vtype_str)
        except ValueError:
            vtype = VariableType.STRING
        VariableManager.set_value(name, value, vtype, plugin_id=None, save=True)
        # _on_variable_changed will broadcast to all clients

    async def _on_get_connected_clients(self, info: ClientInfo, msg: dict) -> None:
        clients = [
            {"client_id": c.client_id, "device_type": c.device_type}
            for c in self._clients.values()
        ]
        await info.ws.send(encode("CONNECTED_CLIENTS", clients=clients))

    async def _on_ping(self, info: ClientInfo, msg: dict) -> None:
        await info.ws.send(encode("PONG"))

    # ── helpers ───────────────────────────────────────────────────────

    async def _send_buttons(self, info: ClientInfo, folder_id: Optional[str] = None) -> None:
        profile = ProfileManager.get_client_profile(info.client_id)
        if profile is None:
            return
        folder = profile.folder
        if folder_id:
            found = _find_folder(folder, folder_id)
            if found:
                folder = found

        def _resolve_label(label: str) -> str:
            return render_label(label, VariableManager.get_value)

        def _resolve_state(btn) -> bool:
            if btn.state_binding:
                val = VariableManager.get_value(btn.state_binding)
                if val is not None:
                    return bool(val)
            return btn.state

        buttons_payload = []
        for pos, btn in folder.buttons.items():
            row, col = pos.split("_")
            buttons_payload.append({
                "button_id": btn.button_id,
                "position": pos,
                "row": int(row),
                "col": int(col),
                "label": _resolve_label(btn.label),
                "label_color": btn.label_color,
                "label_font_size": btn.label_font_size,
                "icon": btn.icon,
                "background_color": btn.background_color,
                "state": _resolve_state(btn),
                "has_actions": len(btn.actions) > 0 or len(btn.conditions) > 0,
            })

        sub_folders = [
            {"folder_id": sf.folder_id, "name": sf.name}
            for sf in folder.sub_folders
        ]

        await info.ws.send(encode(
            "BUTTONS",
            folder_id=folder.folder_id,
            folder_name=folder.name,
            columns=folder.columns,
            rows=folder.rows,
            buttons=buttons_payload,
            sub_folders=sub_folders,
        ))

    async def _broadcast(self, message: str) -> None:
        if not self._clients:
            return
        dead = []
        for cid, info in self._clients.items():
            try:
                await info.ws.send(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self._clients.pop(cid, None)

    def _on_variable_changed(self, variable) -> None:
        """Called from any thread when a variable changes."""
        if self._loop is None:
            return  # Server not yet running
        
        try:
            asyncio.run_coroutine_threadsafe(
                self._broadcast(encode("VARIABLE_CHANGED", variable=variable.to_dict())),
                self._loop
            )
        except Exception:
            pass

        # Update state-bound buttons
        try:
            asyncio.run_coroutine_threadsafe(
                self._push_state_bound_buttons(variable.name),
                self._loop
            )
        except Exception as exc:
            logger.debug("Error pushing state-bound buttons: %s", exc)

    async def _push_state_bound_buttons(self, variable_name: str) -> None:
        """When a Bool variable changes, push updated states to all clients."""
        for info in list(self._clients.values()):
            profile = ProfileManager.get_client_profile(info.client_id)
            if profile is None:
                continue
            for pos, btn in profile.folder.buttons.items():
                if btn.state_binding == variable_name:
                    new_state = bool(VariableManager.get_value(variable_name))
                    if btn.state != new_state:
                        btn.state = new_state
                    try:
                        await info.ws.send(
                            encode("BUTTON_STATE", button_id=btn.button_id, state=btn.state)
                        )
                    except Exception:
                        pass

    # ── start ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not _WEBSOCKETS_AVAILABLE:
            raise ImportError("Install websockets: pip install websockets")
        logger.info("Starting WebSocket server on ws://%s:%d", self.host, int(self.port))
        
        # Custom request handler to accept Connection: keep-alive
        async def process_request(request):
            # Accept all upgrade requests, even with keep-alive headers
            # Return None to accept, or raise an exception to reject
            return None
        
        # Allow Connection: keep-alive for broader client compatibility
        async with _websockets.serve(
            self.handler, 
            self.host, 
            self.port,
            compression=None  # Disable compression for compatibility
        ):
            await asyncio.Future()   # run forever


