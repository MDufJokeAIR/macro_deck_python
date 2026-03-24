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
from macro_deck_python.services.action_executor import execute_button, set_event_loop, set_appearance_update_callback
from macro_deck_python.services.profile_manager import ProfileManager
from macro_deck_python.services.variable_manager import VariableManager
from macro_deck_python.utils.template import render_label
from macro_deck_python.utils.folder_utils import find_folder as _find_folder
from macro_deck_python.websocket.protocol import decode, encode
from macro_deck_python.models.slider import SliderWidget

logger = logging.getLogger("macro_deck.websocket")

# ── suppress harmless websockets noise from plain-HTTP / TCP probes ──────────
class _WsNoiseFilter(logging.Filter):
    """Suppress harmless websockets handshake errors caused by plain-HTTP probes."""
    _SKIP = (
        "invalid Connection header",
        "did not receive a valid HTTP request",
        "connection closed while reading HTTP request",
        "connection rejected (200 OK)",
        "connection failed (500 Internal Server Error)",
    )
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(skip in msg for skip in self._SKIP)

logging.getLogger("websockets.server").addFilter(_WsNoiseFilter())
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_PORT = 8191
API_VERSION = 20   # matches Macro Deck 2.x wire protocol version


class ClientInfo:
    def __init__(self, ws: "WebSocketServerProtocol", client_id: str):
        self.ws = ws
        self.client_id = client_id
        self.device_type: str = "unknown"
        self.api_version: int = 0
        self.profile_id: Optional[str] = None


# Set of live server instances (for class-level broadcast)
_LIVE_INSTANCES: set = set()

class MacroDeckServer:
    # Plugin-registered message hooks: method → list of async handlers
    _plugin_message_hooks: Dict[str, list] = {}

    @classmethod
    def register_message_hook(cls, method: str, handler) -> None:
        """Register an async handler for a WebSocket method (called by plugins)."""
        if method not in cls._plugin_message_hooks:
            cls._plugin_message_hooks[method] = []
        if handler not in cls._plugin_message_hooks[method]:
            cls._plugin_message_hooks[method].append(handler)

    @classmethod
    async def _broadcast_class(cls, message: str) -> None:
        """Broadcast to all connected clients (class-level, no instance needed)."""
        # We need to reach any live instance. Use a weak registry.
        for instance in _LIVE_INSTANCES:
            await instance._broadcast(message)

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self._clients: Dict[str, ClientInfo] = {}   # client_id → ClientInfo
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # set in start()
        _LIVE_INSTANCES.add(self)

        # Register variable-change hook to push updates to all clients
        VariableManager.on_change(self._on_variable_changed)
        
        # Register profile-change hook to broadcast profile switches to all clients
        ProfileManager.on_change(self._on_profile_changed)
        
        # Register appearance-update callback for STYLE block execution
        set_appearance_update_callback(self._on_button_appearance_changed)

    # ── connection lifecycle ──────────────────────────────────────────

    async def handler(self, ws: "WebSocketServerProtocol", path: str = "/") -> None:
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
            "BUTTON_PRESS":          self._on_button_press,
            "GET_BUTTONS":           self._on_get_buttons,
            "GET_PROFILES":          self._on_get_profiles,
            "SET_PROFILE":           self._on_set_profile,
            "GET_VARIABLES":         self._on_get_variables,
            "SET_VARIABLE":          self._on_set_variable,
            "GET_CONNECTED_CLIENTS": self._on_get_connected_clients,
            "PING":                  self._on_ping,
            "GET_SLIDERS":           self._on_get_sliders,
            "ADD_SLIDER":            self._on_add_slider,
            "REMOVE_SLIDER":         self._on_remove_slider,
            "UPDATE_SLIDER":         self._on_update_slider,
        }

        handler = dispatch.get(method)
        if handler:
            await handler(info, msg)
        else:
            # Try plugin-registered hooks first
            hooks = self.__class__._plugin_message_hooks.get(method, [])
            if hooks:
                for hook in hooks:
                    try:
                        await hook(info, msg)
                    except Exception as exc:
                        logger.error("Plugin hook %s error: %s", method, exc)
            else:
                await info.ws.send(encode("ERROR", message=f"Unknown method: {method}"))

    # ── individual handlers ───────────────────────────────────────────

    async def _on_connect(self, info: ClientInfo, msg: dict) -> None:
        info.device_type = msg.get("device_type", "unknown")
        info.api_version = msg.get("api_version", 0)
        info.profile_id = msg.get("profile_id")
        if info.profile_id:
            ProfileManager.set_client_profile(info.client_id, info.profile_id)
        # Send initial button layout
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

        # Only toggle state if a state_binding variable drives it;
        # otherwise leave state as-is (changed only via Set Variable actions).
        if btn.state_binding is not None:
            # State is driven by variable; the variable-change hook will update it
            pass

        # Broadcast updated state to all clients
        await self._broadcast(encode("BUTTON_STATE", button_id=btn.button_id, state=btn.state))

        # Execute actions in background, then push fresh button layout so
        # condition-driven appearance (label/color) re-evaluates on all clients
        execute_button(btn, info.client_id)
        await self._send_buttons(info)

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

        def _button_payload(pos, btn) -> dict:
            row, col = pos.split("_")
            base = {
                "button_id":   btn.button_id,
                "button_type": getattr(btn, "button_type", "button"),
                "position":    pos,
                "row":         int(row),
                "col":         int(col),
            }
            btype = getattr(btn, "button_type", "button")
            if btype == "slider":
                sc = getattr(btn, "slider_config", {})
                base.update({
                    "slider_config": sc,
                    "label": _resolve_label(sc.get("label", "")),
                    "label_color":   btn.label_color,
                })
            elif btype == "slider_occupied":
                base.update({"slider_config": getattr(btn, "slider_config", {})})
            else:
                # Resolve appearance through conditions
                app = btn.resolve_appearance(VariableManager.get_value)
                base.update({
                    "label":            _resolve_label(app["label"]),
                    "label_color":      app["label_color"],
                    "label_font_size":  btn.label_font_size,
                    "icon":             app["icon"],
                    "background_color": app["background_color"],
                    "state":            app["state"],
                    "has_actions":      len(btn.program) > 0,
                })
            return base

        buttons_payload = [_button_payload(pos, btn) for pos, btn in folder.buttons.items()]

        sub_folders = [
            {"folder_id": sf.folder_id, "name": sf.name}
            for sf in folder.sub_folders
        ]

        # Include slider occupancy so clients know which cells are sliders
        slider_cells: dict = {}
        for slider in folder.sliders.values():
            for cell in slider.occupied_cells:
                slider_cells[cell] = slider.slider_id

        await info.ws.send(encode(
            "BUTTONS",
            folder_id=folder.folder_id,
            folder_name=folder.name,
            columns=folder.columns,
            rows=folder.rows,
            buttons=buttons_payload,
            sub_folders=sub_folders,
            slider_cells=slider_cells,
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

    @staticmethod
    def _button_depends_on_variable(btn, variable_name: str) -> bool:
        """Check if a button depends on a variable via state_binding or conditions."""
        # Direct state binding
        if btn.state_binding == variable_name:
            return True
        
        # Check if any condition in the button's program depends on this variable
        def _check_blocks(blocks):
            for b in blocks:
                if b.type == "if":
                    # Check conditions (new format)
                    if b.conditions:
                        for cond in b.conditions:
                            if cond.get("variable_name") == variable_name:
                                return True
                    # Fallback for legacy format
                    elif b.variable_name == variable_name:
                        return True
                    # Recursively check nested blocks
                    if _check_blocks(b.then_blocks) or _check_blocks(b.else_blocks):
                        return True
            return False
        
        return _check_blocks(btn.program)

    def _on_variable_changed(self, variable) -> None:
        """Called from any thread when a variable changes.

        Uses run_coroutine_threadsafe so it's safe to call from background
        threads (e.g. the sys-vars polling thread). asyncio.ensure_future /
        get_event_loop() are NOT thread-safe in Python 3.10+.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(
            self._broadcast(encode("VARIABLE_CHANGED", variable=variable.to_dict())),
            loop,
        )
        asyncio.run_coroutine_threadsafe(
            self._push_state_bound_buttons(variable.name),
            loop,
        )

    async def _push_state_bound_buttons(self, variable_name: str) -> None:
        """When a variable changes, update state on any bound buttons then
        push a full BUTTONS message so condition-driven appearance re-evaluates."""
        affected: set = set()
        for info in list(self._clients.values()):
            profile = ProfileManager.get_client_profile(info.client_id)
            if profile is None:
                continue
            state_changed = False
            has_dependent_btns = False
            
            # Check all buttons for dependencies on this variable
            for pos, btn in profile.folder.buttons.items():
                # Update button state if it's bound to this variable
                if btn.state_binding == variable_name:
                    new_state = bool(VariableManager.get_value(variable_name))
                    if btn.state != new_state:
                        btn.state = new_state
                        state_changed = True
                
                # Check if button has conditions depending on this variable
                if self._button_depends_on_variable(btn, variable_name):
                    has_dependent_btns = True
            
            # Push refresh if state changed OR if any button has conditions depending on this variable
            if state_changed or has_dependent_btns:
                affected.add(info.client_id)
        
        # Push a full BUTTONS refresh to each affected client so colours update
        for client_id in affected:
            info = self._clients.get(client_id)
            if info:
                try:
                    await self._send_buttons(info)
                except Exception:
                    pass

    def _on_profile_changed(self, profile_id: str) -> None:
        """Called when the active profile changes (from any thread).
        
        Broadcasts updated profile to all clients via WebSocket.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        # Get the new profile and send it to all clients
        profile = ProfileManager.get_profile(profile_id)
        if profile is None:
            logger.error("Profile not found: %s", profile_id)
            return
        # Broadcast profile change to all clients
        asyncio.run_coroutine_threadsafe(
            self._broadcast(encode("PROFILE_CHANGED", profile_id=profile_id)),
            loop,
        )
        # Also send updated buttons for the new profile to all clients
        asyncio.run_coroutine_threadsafe(
            self._broadcast_buttons_for_profile(profile_id),
            loop,
        )

    async def _broadcast_buttons_for_profile(self, profile_id: str) -> None:
        """Send the buttons for the given profile to all connected clients."""
        profile = ProfileManager.get_profile(profile_id)
        if profile is None:
            return
        for info in list(self._clients.values()):
            try:
                await self._send_buttons(info)
            except Exception as exc:
                logger.debug("Error sending buttons to client: %s", exc)

    async def _on_button_appearance_changed(self, button_id: str) -> None:
        """Called when a button's appearance changes due to STYLE block execution.
        
        Sends updated button data to all clients so the appearance change is visible.
        This is called from action executor threads, so we push to async loop safely.
        """
        # Find the button and send updated buttons to all clients
        for profile in ProfileManager.get_all():
            def _find_button(folder):
                for btn in folder.buttons.values():
                    if btn and btn.button_id == button_id:
                        return btn
                for subfolder in folder.sub_folders:
                    found = _find_button(subfolder)
                    if found:
                        return found
                return None
            
            btn = _find_button(profile.folder)
            if btn is not None:
                # Send updated buttons to all clients viewing this profile
                for info in list(self._clients.values()):
                    if ProfileManager.get_client_profile(info.client_id) == profile:
                        try:
                            await self._send_buttons(info)
                        except Exception as exc:
                            logger.debug("Error sending button update to client: %s", exc)
                break

    # ── slider handlers ───────────────────────────────────────────────

    async def _on_slider_change(self, info: ClientInfo, msg: dict) -> None:
        """Client dragged a slider. Apply value and broadcast to all clients."""
        from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
        slider_id = msg.get("slider_id", "")
        try:
            new_value = float(msg.get("value", 0))
        except (TypeError, ValueError):
            await info.ws.send(encode("ERROR", message="SLIDER_CHANGE: invalid value"))
            return
        slider = SliderManager.apply_change(slider_id, new_value)
        if slider is None:
            await info.ws.send(encode("ERROR", message=f"Slider not found: {slider_id}"))
            return
        # Broadcast updated state to all clients (including sender so UI stays in sync)
        await self._broadcast(encode(
            "SLIDER_STATE",
            slider_id=slider.slider_id,
            value=slider.current_value,
        ))

    async def _on_get_sliders(self, info: ClientInfo, msg: dict) -> None:
        profile = ProfileManager.get_client_profile(info.client_id)
        if not profile:
            await info.ws.send(encode("SLIDERS", sliders=[]))
            return
        folder_id = msg.get("folder_id")
        folder = profile.folder
        if folder_id:
            found = _find_folder(folder, folder_id)
            if found:
                folder = found
        sliders = [s.to_dict() for s in folder.sliders.values()]
        await info.ws.send(encode("SLIDERS",
                                  folder_id=folder.folder_id,
                                  sliders=sliders))

    async def _on_add_slider(self, info: ClientInfo, msg: dict) -> None:
        from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
        profile = ProfileManager.get_client_profile(info.client_id)
        if not profile:
            await info.ws.send(encode("ERROR", message="No active profile"))
            return
        try:
            slider = SliderWidget.from_dict(msg.get("slider", {}))
        except Exception as exc:
            await info.ws.send(encode("ERROR", message=f"Invalid slider data: {exc}"))
            return
        folder_id = msg.get("folder_id")
        ok = SliderManager.add_slider(slider, profile.profile_id, folder_id)
        if ok:
            await self._broadcast(encode("SLIDER_ADDED", slider=slider.to_dict()))
        else:
            await info.ws.send(encode("ERROR", message="Could not add slider"))

    async def _on_remove_slider(self, info: ClientInfo, msg: dict) -> None:
        from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
        profile = ProfileManager.get_client_profile(info.client_id)
        if not profile:
            await info.ws.send(encode("ERROR", message="No active profile"))
            return
        slider_id = msg.get("slider_id", "")
        folder_id = msg.get("folder_id")
        ok = SliderManager.remove_slider(slider_id, profile.profile_id, folder_id)
        if ok:
            await self._broadcast(encode("SLIDER_REMOVED", slider_id=slider_id))
        else:
            await info.ws.send(encode("ERROR", message=f"Slider not found: {slider_id}"))

    async def _on_update_slider(self, info: ClientInfo, msg: dict) -> None:
        from macro_deck_python.plugins.builtin.analog_slider.slider_manager import SliderManager
        profile = ProfileManager.get_client_profile(info.client_id)
        if not profile:
            await info.ws.send(encode("ERROR", message="No active profile"))
            return
        try:
            slider = SliderWidget.from_dict(msg.get("slider", {}))
        except Exception as exc:
            await info.ws.send(encode("ERROR", message=f"Invalid slider data: {exc}"))
            return
        folder_id = msg.get("folder_id")
        ok = SliderManager.update_slider(slider, profile.profile_id, folder_id)
        if ok:
            await self._broadcast(encode("SLIDER_UPDATED", slider=slider.to_dict()))
        else:
            await info.ws.send(encode("ERROR", message="Could not update slider"))

    # ── start ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not _WEBSOCKETS_AVAILABLE:
            raise ImportError("Install websockets: pip install websockets")
        self._loop = asyncio.get_running_loop()   # capture loop for thread-safe callbacks
        set_event_loop(self._loop)  # pass loop to action executor for STYLE block updates
        self.port = int(self.port)  # guard against port being passed as a string
        logger.info("Starting WebSocket server on ws://%s:%d", self.host, self.port)

        async def _process_request(connection_or_path, request_or_headers):
            """Return 200 OK for plain HTTP probes.
            Handles both websockets API styles:
              - Legacy (<11):  _process_request(path: str, headers: Headers)
              - Modern (>=13): _process_request(connection, request)
            """
            # Detect which API we're dealing with
            if isinstance(connection_or_path, str):
                # Legacy API: (path, headers)
                headers = request_or_headers
                upgrade = headers.get("Upgrade", "").lower()
                if upgrade != "websocket":
                    # Legacy API returns (http_status, headers, body)
                    from http import HTTPStatus
                    return (HTTPStatus.OK, [], b"OK\r\n")
                return None
            else:
                # Modern API: (connection, request)
                request = request_or_headers
                try:
                    upgrade = request.headers.get("Upgrade", "").lower()
                except AttributeError:
                    upgrade = "websocket"  # assume valid WS if we can't read headers
                if upgrade != "websocket":
                    try:
                        from websockets.http11 import Response
                        from websockets.datastructures import Headers
                        return Response(
                            status_code=200,
                            reason_phrase="OK",
                            headers=Headers([
                                ("Content-Type", "text/plain"),
                                ("Content-Length", "2"),
                            ]),
                            body=b"OK",
                        )
                    except ImportError:
                        from http import HTTPStatus
                        return (HTTPStatus.OK, [], b"OK\r\n")
                return None

        async with _websockets.serve(
            self.handler, self.host, self.port,
            process_request=_process_request,
            origins=None,          # accept connections from any origin (browsers, Pi, etc.)
            ping_interval=20,      # keepalive every 20s
            ping_timeout=30,       # disconnect after 30s no pong
            max_size=10 * 1024 * 1024,  # 10 MB max message
        ):
            await asyncio.Future()   # run forever