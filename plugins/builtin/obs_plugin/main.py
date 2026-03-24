"""
Built-in plugin: OBS WebSocket integration.
Connects to OBS Studio via obs-websocket v5 protocol.
Publishes streaming/recording state as Bool variables.
Actions: start/stop stream, start/stop recording, switch scene,
         toggle source visibility, set audio volume.
Requires: obs-websocket-py  (pip install obs-websocket-py)
Falls back gracefully when OBS is not running.
"""
from __future__ import annotations
import json, logging, threading
from typing import List, Optional, TYPE_CHECKING
from macro_deck_python.models.variable import VariableType
from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction, PluginConfiguration
from macro_deck_python.services.variable_manager import VariableManager
if TYPE_CHECKING:
    from macro_deck_python.models.action_button import ActionButton
logger = logging.getLogger("plugin.obs")

# ── OBS connection helper ─────────────────────────────────────────────
class _OBSBridge:
    def __init__(self):
        self._ws = None
        self._lock = threading.Lock()

    def connect(self, host: str, port: int, password: str) -> bool:
        try:
            import obsws_python as obs  # type: ignore
            with self._lock:
                self._ws = obs.ReqClient(host=host, port=port, password=password, timeout=3)
            logger.info("Connected to OBS at %s:%d", host, port)
            return True
        except ImportError:
            logger.warning("obsws_python not installed; OBS plugin disabled")
            return False
        except Exception as exc:
            logger.warning("OBS connection failed: %s", exc)
            return False

    def disconnect(self):
        with self._lock:
            self._ws = None

    def call(self, method: str, **kwargs):
        with self._lock:
            if self._ws is None:
                return None
        try:
            fn = getattr(self._ws, method)
            return fn(**kwargs) if kwargs else fn()
        except Exception as exc:
            logger.error("OBS call %s failed: %s", method, exc)
            return None

_bridge = _OBSBridge()

def _pid(plugin):
    return plugin.package_id if plugin else "builtin.obs"


# ── Actions ──────────────────────────────────────────────────────────

class StartStreamAction(PluginAction):
    action_id = "start_stream"; name = "Start Streaming"
    description = "Start OBS streaming"; can_configure = False
    def trigger(self, client_id, action_button):
        _bridge.call("start_stream")

class StopStreamAction(PluginAction):
    action_id = "stop_stream"; name = "Stop Streaming"
    description = "Stop OBS streaming"; can_configure = False
    def trigger(self, client_id, action_button):
        _bridge.call("stop_stream")

class ToggleStreamAction(PluginAction):
    action_id = "toggle_stream"; name = "Toggle Streaming"
    description = "Toggle OBS streaming on/off"; can_configure = False
    def trigger(self, client_id, action_button):
        _bridge.call("toggle_stream")

class StartRecordAction(PluginAction):
    action_id = "start_record"; name = "Start Recording"
    description = "Start OBS recording"; can_configure = False
    def trigger(self, client_id, action_button):
        _bridge.call("start_record")

class StopRecordAction(PluginAction):
    action_id = "stop_record"; name = "Stop Recording"
    description = "Stop OBS recording"; can_configure = False
    def trigger(self, client_id, action_button):
        _bridge.call("stop_record")

class ToggleRecordAction(PluginAction):
    action_id = "toggle_record"; name = "Toggle Recording"
    description = "Toggle OBS recording on/off"; can_configure = False
    def trigger(self, client_id, action_button):
        _bridge.call("toggle_record")

class SwitchSceneAction(PluginAction):
    action_id = "switch_scene"; name = "Switch Scene"
    description = "Switch to a specific OBS scene"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        scene = cfg.get("scene_name", "")
        if scene:
            _bridge.call("set_current_program_scene", sceneName=scene)

class ToggleSourceAction(PluginAction):
    action_id = "toggle_source"; name = "Toggle Source Visibility"
    description = "Show/hide a source in a scene"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        scene = cfg.get("scene_name", "")
        source = cfg.get("source_name", "")
        if not scene or not source:
            return
        try:
            resp = _bridge.call("get_scene_item_id", sceneName=scene, sourceName=source)
            if resp is None: return
            item_id = resp.scene_item_id
            vis_resp = _bridge.call("get_scene_item_enabled", sceneName=scene, sceneItemId=item_id)
            if vis_resp is None: return
            _bridge.call("set_scene_item_enabled",
                         sceneName=scene, sceneItemId=item_id,
                         sceneItemEnabled=not vis_resp.scene_item_enabled)
        except Exception as exc:
            logger.error("ToggleSource: %s", exc)

class SetVolumeAction(PluginAction):
    action_id = "set_volume"; name = "Set Audio Volume"
    description = "Set volume of an audio source (0.0–1.0)"; can_configure = True
    def trigger(self, client_id, action_button):
        cfg = json.loads(self.configuration) if self.configuration else {}
        source = cfg.get("source_name", "")
        vol = float(cfg.get("volume", 1.0))
        if source:
            _bridge.call("set_input_volume", inputName=source, inputVolumeMultiplier=vol)


# ── Main plugin ───────────────────────────────────────────────────────

class Main(IMacroDeckPlugin):
    package_id = "builtin.obs"; name = "OBS Studio"
    version = "1.0.0"; author = "MacroDeck"
    description = "Control OBS Studio via WebSocket"
    can_configure = True

    _poll_thread: Optional[threading.Thread] = None
    _stop: threading.Event

    def enable(self):
        self.actions: List[PluginAction] = [
            StartStreamAction(), StopStreamAction(), ToggleStreamAction(),
            StartRecordAction(), StopRecordAction(), ToggleRecordAction(),
            SwitchSceneAction(), ToggleSourceAction(), SetVolumeAction(),
        ]
        self._stop = threading.Event()
        host = PluginConfiguration.get_value(self, "host", "127.0.0.1")
        port = int(PluginConfiguration.get_value(self, "port", "4455"))
        password = PluginConfiguration.get_value(self, "password", "")
        if _bridge.connect(host, port, password):
            self._start_polling()

    def disable(self):
        self._stop.set()
        _bridge.disconnect()

    def open_configurator(self):
        logger.info("OBS configurator: set host/port/password via PluginConfiguration")

    def _start_polling(self):
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="obs-poll")
        self._poll_thread.start()

    def _poll_loop(self):
        """Poll OBS every 2 seconds and update variables."""
        while not self._stop.wait(2.0):
            try:
                status = _bridge.call("get_stream_status")
                if status:
                    VariableManager.set_value("obs_streaming", status.output_active,
                                              VariableType.BOOL, self.package_id, save=False)
                rec = _bridge.call("get_record_status")
                if rec:
                    VariableManager.set_value("obs_recording", rec.output_active,
                                              VariableType.BOOL, self.package_id, save=False)
                scene = _bridge.call("get_current_program_scene")
                if scene:
                    VariableManager.set_value("obs_current_scene", scene.scene_name,
                                              VariableType.STRING, self.package_id, save=False)
            except Exception as exc:
                logger.debug("OBS poll error: %s", exc)
