"""
test_integration.py — end-to-end integration tests for macro_deck_python.

Tests:
  1. Full button-press pipeline (plugins → executor → variable change → label update)
  2. WebSocket server message handling (in-process asyncio simulation)
  3. Icon manager save/retrieve/delete roundtrip
  4. Encrypted credential store (Fernet)
  5. Commands plugin actions (toggle_variable, set_variable, delay)
  6. Profile-scoped per-client routing end-to-end
  7. Variable change cascades to state-bound buttons
  8. Multi-condition buttons
"""
from __future__ import annotations
import asyncio
import base64
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))


# ─── helpers ─────────────────────────────────────────────────────────

def _reset():
    """Reset all global state between tests."""
    from macro_deck_python.services.variable_manager import VariableManager
    from macro_deck_python.services.profile_manager import ProfileManager
    from macro_deck_python.plugins.plugin_manager import PluginManager
    VariableManager._variables.clear()
    VariableManager._on_change_callbacks.clear()
    ProfileManager._profiles.clear()
    ProfileManager._active_profile = None
    ProfileManager._client_profiles.clear()
    PluginManager._plugins.clear()
    PluginManager._actions.clear()


def _load_builtins():
    from macro_deck_python.plugins.plugin_manager import PluginManager
    builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
    PluginManager.set_plugins_dir(builtin)
    PluginManager.load_all_plugins()


def _make_mock_plugin(pid: str, log: list):
    """Register a mock plugin/action that appends to log on trigger."""
    from macro_deck_python.plugins.plugin_manager import PluginManager
    from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction

    class MA(PluginAction):
        action_id = "mock"
        name = "Mock"
        description = ""
        def trigger(self_, cid, btn):
            cfg = json.loads(self_.configuration) if self_.configuration else {}
            log.append({"client": cid, **cfg})

    class MP(IMacroDeckPlugin):
        name = version = author = description = ""
        def enable(self_): self_.actions = [MA()]

    p = MP()
    p.package_id = pid
    p.enable()
    PluginManager._plugins[pid] = p
    PluginManager._actions[pid] = {"mock": p.actions[0]}
    p.actions[0].plugin = p
    return p


# ═══════════════════════════════════════════════════════════════════════
# 1. FULL PIPELINE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════

class TestFullPipeline(unittest.TestCase):
    def setUp(self):
        _reset()
        self.log = []
        _make_mock_plugin("pipe.test", self.log)
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.variable_manager import VariableManager
        VariableManager.set_value("level", 5, VariableType.INTEGER, save=False)

    def _make_button(self):
        from macro_deck_python.models.action_button import ActionButton, ActionEntry, Condition
        btn = ActionButton(label="Level: {level}")
        btn.actions.append(ActionEntry("pipe.test", "mock", json.dumps({"step": "base"})))
        btn.conditions.append(Condition(
            "level", ">", "3",
            actions_true=[ActionEntry("pipe.test", "mock", json.dumps({"step": "high"}))],
            actions_false=[ActionEntry("pipe.test", "mock", json.dumps({"step": "low"}))],
        ))
        return btn

    def test_pipeline_fires_all(self):
        from macro_deck_python.services.action_executor import execute_button
        btn = self._make_button()
        execute_button(btn, "client-X")
        time.sleep(0.2)
        steps = [e["step"] for e in self.log]
        self.assertIn("base", steps)
        self.assertIn("high", steps)
        self.assertNotIn("low", steps)

    def test_label_renders_variable(self):
        from macro_deck_python.utils.template import render_label
        from macro_deck_python.services.variable_manager import VariableManager
        btn = self._make_button()
        label = render_label(btn.label, VariableManager.get_value)
        self.assertEqual(label, "Level: 5")

    def test_variable_change_updates_label(self):
        from macro_deck_python.utils.template import render_label
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        VariableManager.set_value("level", 99, VariableType.INTEGER, save=False)
        btn = self._make_button()
        label = render_label(btn.label, VariableManager.get_value)
        self.assertEqual(label, "Level: 99")

    def test_callback_chain(self):
        """Variable change → multiple downstream callbacks all fire."""
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        results = []
        VariableManager.on_change(lambda v: results.append(f"cb1:{v.name}"))
        VariableManager.on_change(lambda v: results.append(f"cb2:{v.name}"))
        VariableManager.set_value("level", 10, VariableType.INTEGER, save=False)
        self.assertIn("cb1:level", results)
        self.assertIn("cb2:level", results)

    def test_state_binding_reflects_variable(self):
        from macro_deck_python.models.action_button import ActionButton
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.variable_manager import VariableManager
        btn = ActionButton(state_binding="is_live")
        VariableManager.set_value("is_live", True, VariableType.BOOL, save=False)
        val = VariableManager.get_value(btn.state_binding)
        self.assertTrue(bool(val))
        VariableManager.set_value("is_live", False, VariableType.BOOL, save=False)
        val = VariableManager.get_value(btn.state_binding)
        self.assertFalse(bool(val))


# ═══════════════════════════════════════════════════════════════════════
# 2. WEBSOCKET SERVER (in-process asyncio)
# ═══════════════════════════════════════════════════════════════════════

class FakeWS:
    """Simulates a websockets.WebSocketServerProtocol."""
    def __init__(self, incoming: list):
        self._incoming = iter(incoming)
        self.sent: list[str] = []

    async def send(self, msg: str):
        self.sent.append(msg)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._incoming)
        except StopIteration:
            raise StopAsyncIteration


class TestWebSocketServer(unittest.TestCase):
    def setUp(self):
        _reset()
        self.log = []
        _make_mock_plugin("ws.test", self.log)
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.models.action_button import ActionButton, ActionEntry
        self.profile = ProfileManager.create_profile("WS Test")
        btn = ActionButton(label="WS Btn")
        btn.actions.append(ActionEntry("ws.test", "mock", json.dumps({"src": "ws_press"})))
        self.profile.folder.set_button(0, 0, btn)
        ProfileManager.set_active(self.profile.profile_id)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _server(self):
        from macro_deck_python.websocket.server import MacroDeckServer
        return MacroDeckServer.__new__(MacroDeckServer)

    def test_connect_message(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "test-client-001")
            server._clients["test-client-001"] = info
            await server._on_connect(info, {
                "method": "CONNECT",
                "device_type": "browser",
                "api_version": 20,
            })
            return ws.sent

        sent = self._run(run())
        methods = [decode(m)["method"] for m in sent]
        self.assertIn("BUTTONS", methods)

    def test_ping_pong(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "ping-client")
            await server._on_ping(info, {"method": "PING"})
            return ws.sent

        sent = self._run(run())
        self.assertEqual(decode(sent[0])["method"], "PONG")

    def test_get_profiles(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "prof-client")
            await server._on_get_profiles(info, {"method": "GET_PROFILES"})
            return ws.sent

        sent = self._run(run())
        d = decode(sent[0])
        self.assertEqual(d["method"], "PROFILES")
        profile_ids = [p["id"] for p in d["profiles"]]
        self.assertIn(self.profile.profile_id, profile_ids)

    def test_get_variables(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        VariableManager.set_value("ws_var", 42, VariableType.INTEGER, save=False)
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "var-client")
            await server._on_get_variables(info, {"method": "GET_VARIABLES"})
            return ws.sent

        sent = self._run(run())
        d = decode(sent[0])
        self.assertEqual(d["method"], "VARIABLES")
        names = [v["name"] for v in d["variables"]]
        self.assertIn("ws_var", names)

    def test_set_variable(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.services.variable_manager import VariableManager
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}
        VariableManager._on_change_callbacks.clear()

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "setvar-client")
            await server._on_set_variable(info, {
                "method": "SET_VARIABLE",
                "name": "remote_var",
                "value": "hello",
                "type": "String",
            })

        self._run(run())
        self.assertEqual(VariableManager.get_value("remote_var"), "hello")

    def test_unknown_method_returns_error(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "err-client")
            await server._handle_message(info, json.dumps({"method": "DOES_NOT_EXIST"}))
            return ws.sent

        sent = self._run(run())
        d = decode(sent[0])
        self.assertEqual(d["method"], "ERROR")

    def test_invalid_json_returns_error(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "bad-json-client")
            await server._handle_message(info, "{not json!!}")
            return ws.sent

        sent = self._run(run())
        d = decode(sent[0])
        self.assertEqual(d["method"], "ERROR")

    def test_button_press_triggers_action(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.services.profile_manager import ProfileManager
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "press-client")
            server._clients["press-client"] = info
            ProfileManager.set_client_profile("press-client", self.profile.profile_id)
            await server._on_button_press(info, {
                "method": "BUTTON_PRESS",
                "position": "0_0",
            })
            return ws.sent

        self._run(run())
        time.sleep(0.2)   # let executor thread finish
        sources = [e.get("src") for e in self.log]
        self.assertIn("ws_press", sources)

    def test_set_profile_switches(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.websocket.protocol import decode
        p2 = ProfileManager.create_profile("P2")
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}

        async def run():
            ws = FakeWS([])
            info = ClientInfo(ws, "switch-client")
            server._clients["switch-client"] = info
            await server._on_set_profile(info, {
                "method": "SET_PROFILE",
                "profile_id": p2.profile_id,
            })
            return ws.sent, info

        sent, info = self._run(run())
        self.assertEqual(ProfileManager.get_client_profile("switch-client").profile_id,
                         p2.profile_id)
        methods = [decode(m)["method"] for m in sent]
        self.assertIn("BUTTONS", methods)

    def test_broadcast(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}
        wss = [FakeWS([]) for _ in range(3)]
        for i, ws in enumerate(wss):
            info = ClientInfo(ws, f"bc-{i}")
            server._clients[f"bc-{i}"] = info

        async def run():
            await server._broadcast(json.dumps({"method": "TEST_BROADCAST"}))

        self._run(run())
        for ws in wss:
            self.assertEqual(len(ws.sent), 1)
            self.assertEqual(json.loads(ws.sent[0])["method"], "TEST_BROADCAST")


# ═══════════════════════════════════════════════════════════════════════
# 3. ICON MANAGER
# ═══════════════════════════════════════════════════════════════════════

class TestIconManager(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.services.icon_manager import IconManager, _ICONS_DIR, _PACKS_DIR
        # Point to temp dirs so tests don't touch ~/.macro_deck
        self._tmp = pathlib.Path(tempfile.mkdtemp())
        import macro_deck_python.services.icon_manager as im
        self._orig_icons = im._ICONS_DIR
        self._orig_packs = im._PACKS_DIR
        im._ICONS_DIR = self._tmp / "icons"
        im._PACKS_DIR = self._tmp / "packs"
        im._ICONS_DIR.mkdir()
        im._PACKS_DIR.mkdir()
        IconManager._cache.clear()

    def tearDown(self):
        import macro_deck_python.services.icon_manager as im
        im._ICONS_DIR = self._orig_icons
        im._PACKS_DIR = self._orig_packs
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_save_and_retrieve(self):
        from macro_deck_python.services.icon_manager import IconManager
        data = b"\x89PNG\r\n" + b"x" * 100   # fake PNG bytes
        icon_id = IconManager.save_icon("test.png", data)
        self.assertIsNotNone(icon_id)
        b64 = IconManager.get_icon_b64(icon_id)
        self.assertIsNotNone(b64)
        self.assertEqual(base64.b64decode(b64), data)

    def test_content_addressable(self):
        """Same content → same icon_id."""
        from macro_deck_python.services.icon_manager import IconManager
        data = b"PNG_CONTENT_123"
        id1 = IconManager.save_icon("a.png", data)
        id2 = IconManager.save_icon("b.png", data)
        self.assertEqual(id1, id2)

    def test_different_content_different_id(self):
        from macro_deck_python.services.icon_manager import IconManager
        id1 = IconManager.save_icon("a.png", b"DATA_A")
        id2 = IconManager.save_icon("b.png", b"DATA_B")
        self.assertNotEqual(id1, id2)

    def test_delete(self):
        from macro_deck_python.services.icon_manager import IconManager
        data = b"PNG_TO_DELETE"
        icon_id = IconManager.save_icon("del.png", data)
        self.assertTrue(IconManager.delete_icon(icon_id))
        # After deletion, get_icon_b64 returns placeholder (not None)
        result = IconManager.get_icon_b64(icon_id)
        self.assertIsNotNone(result)  # placeholder returned

    def test_list_user_icons(self):
        from macro_deck_python.services.icon_manager import IconManager
        id1 = IconManager.save_icon("i1.png", b"D1")
        id2 = IconManager.save_icon("i2.png", b"D2")
        icons = IconManager.list_user_icons()
        self.assertIn(id1, icons)
        self.assertIn(id2, icons)

    def test_placeholder_for_missing(self):
        from macro_deck_python.services.icon_manager import IconManager
        result = IconManager.get_icon_b64("nonexistent_icon_id_xyz")
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 0)

    def test_cache_hit(self):
        from macro_deck_python.services.icon_manager import IconManager
        data = b"CACHED_PNG"
        icon_id = IconManager.save_icon("cached.png", data)
        IconManager._cache.clear()
        # First call populates cache
        b64_1 = IconManager.get_icon_b64(icon_id)
        self.assertIn(icon_id, IconManager._cache)
        # Second call comes from cache
        b64_2 = IconManager.get_icon_b64(icon_id)
        self.assertEqual(b64_1, b64_2)

    def test_is_inline(self):
        from macro_deck_python.services.icon_manager import IconManager
        self.assertTrue(IconManager.is_inline("data:image/png;base64,abc"))
        self.assertTrue(IconManager.is_inline("a" * 65))
        self.assertFalse(IconManager.is_inline("short_id"))
        self.assertFalse(IconManager.is_inline(None))
        self.assertFalse(IconManager.is_inline(""))

    def test_to_data_url(self):
        from macro_deck_python.services.icon_manager import IconManager
        b64 = "abc123=="
        url = IconManager.to_data_url(b64)
        self.assertTrue(url.startswith("data:image/png;base64,"))
        # Already a data URL — unchanged
        already = "data:image/jpeg;base64,xyz"
        self.assertEqual(IconManager.to_data_url(already), already)


# ═══════════════════════════════════════════════════════════════════════
# 4. ENCRYPTED CREDENTIALS
# ═══════════════════════════════════════════════════════════════════════

class TestEncryptedCredentials(unittest.TestCase):
    def setUp(self):
        import macro_deck_python.plugins.base as base_mod
        self._tmp = pathlib.Path(tempfile.mkdtemp())
        self._orig_dir = base_mod.PluginCredentials._CREDS_DIR
        self._orig_key = base_mod._KEY_FILE
        base_mod.PluginCredentials._CREDS_DIR = self._tmp / "creds"
        base_mod._KEY_FILE = self._tmp / ".key"
        base_mod.PluginCredentials._CREDS_DIR.mkdir()

    def tearDown(self):
        import macro_deck_python.plugins.base as base_mod
        base_mod.PluginCredentials._CREDS_DIR = self._orig_dir
        base_mod._KEY_FILE = self._orig_key
        import shutil; shutil.rmtree(self._tmp, ignore_errors=True)

    def _plugin(self, pid):
        from macro_deck_python.plugins.base import IMacroDeckPlugin
        class FP(IMacroDeckPlugin):
            package_id = pid; name = version = author = description = ""
            def enable(self): pass
        return FP()

    def test_encrypt_decrypt_roundtrip(self):
        from macro_deck_python.plugins.base import PluginCredentials
        p = self._plugin("enc.test")
        PluginCredentials.set_credentials(p, {"user": "alice", "pass": "s3cr3t!"})
        creds = PluginCredentials.get_plugin_credentials(p)
        self.assertEqual(len(creds), 1)
        self.assertEqual(creds[0]["user"], "alice")
        self.assertEqual(creds[0]["pass"], "s3cr3t!")

    def test_stored_values_are_not_plaintext(self):
        from macro_deck_python.plugins.base import PluginCredentials
        import json as _json
        p = self._plugin("enc.check")
        PluginCredentials.set_credentials(p, {"secret": "my_password_123"})
        raw_file = (PluginCredentials._CREDS_DIR / f"{p.package_id}.json").read_text()
        self.assertNotIn("my_password_123", raw_file)

    def test_multiple_credential_sets(self):
        from macro_deck_python.plugins.base import PluginCredentials
        p = self._plugin("enc.multi")
        PluginCredentials.set_credentials(p, {"account": "user1", "token": "tok1"})
        PluginCredentials.set_credentials(p, {"account": "user2", "token": "tok2"})
        creds = PluginCredentials.get_plugin_credentials(p)
        self.assertEqual(len(creds), 2)
        accounts = [c["account"] for c in creds]
        self.assertIn("user1", accounts)
        self.assertIn("user2", accounts)

    def test_delete_credentials(self):
        from macro_deck_python.plugins.base import PluginCredentials
        p = self._plugin("enc.del")
        PluginCredentials.set_credentials(p, {"k": "v"})
        PluginCredentials.delete_credentials(p)
        creds = PluginCredentials.get_plugin_credentials(p)
        self.assertEqual(creds, [])

    def test_empty_for_new_plugin(self):
        from macro_deck_python.plugins.base import PluginCredentials
        p = self._plugin("enc.new.never.set")
        self.assertEqual(PluginCredentials.get_plugin_credentials(p), [])

    def test_key_file_permissions(self):
        from macro_deck_python.plugins.base import PluginCredentials, _get_fernet
        p = self._plugin("enc.perms")
        PluginCredentials.set_credentials(p, {"x": "y"})
        import macro_deck_python.plugins.base as bm
        key_file = bm._KEY_FILE
        self.assertTrue(key_file.exists())
        import stat
        mode = oct(stat.S_IMODE(key_file.stat().st_mode))
        self.assertEqual(mode, oct(0o600))


# ═══════════════════════════════════════════════════════════════════════
# 5. COMMANDS PLUGIN ACTIONS
# ═══════════════════════════════════════════════════════════════════════

class TestCommandsPlugin(unittest.TestCase):
    def setUp(self):
        _reset()
        _load_builtins()
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.variable_manager import VariableManager
        VariableManager.set_value("my_bool", False, VariableType.BOOL, save=False)
        VariableManager.set_value("my_str", "initial", VariableType.STRING, save=False)

    def _trigger(self, action_id: str, cfg: dict):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.models.action_button import ActionButton
        act = PluginManager.get_action("builtin.commands", action_id)
        self.assertIsNotNone(act, f"action {action_id} not found")
        act.configuration = json.dumps(cfg)
        act.trigger("test-client", ActionButton())

    def test_toggle_variable_false_to_true(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._trigger("toggle_variable", {"variable_name": "my_bool"})
        self.assertTrue(bool(VariableManager.get_value("my_bool")))

    def test_toggle_variable_twice(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._trigger("toggle_variable", {"variable_name": "my_bool"})
        self._trigger("toggle_variable", {"variable_name": "my_bool"})
        self.assertFalse(bool(VariableManager.get_value("my_bool")))

    def test_set_variable_string(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._trigger("set_variable", {"variable_name": "my_str", "value": "changed", "type": "String"})
        self.assertEqual(VariableManager.get_value("my_str"), "changed")

    def test_set_variable_integer(self):
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        self._trigger("set_variable", {"variable_name": "new_int", "value": "42", "type": "Integer"})
        self.assertEqual(VariableManager.get_value("new_int"), 42)

    def test_delay_waits(self):
        start = time.time()
        self._trigger("delay", {"milliseconds": 150})
        elapsed = time.time() - start
        self.assertGreaterEqual(elapsed, 0.14)
        self.assertLess(elapsed, 1.0)

    def test_run_command_no_wait(self):
        """run_command with wait=False should return immediately."""
        start = time.time()
        self._trigger("run_command", {"command": "echo hello", "wait": False})
        elapsed = time.time() - start
        self.assertLess(elapsed, 0.5)

    def test_toggle_missing_variable_creates_it(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._trigger("toggle_variable", {"variable_name": "brand_new_bool"})
        # get_value returns None if not set, but toggle sets it to True (not False)
        val = VariableManager.get_value("brand_new_bool")
        self.assertIsNotNone(val)


# ═══════════════════════════════════════════════════════════════════════
# 6. MULTI-CONDITION BUTTONS
# ═══════════════════════════════════════════════════════════════════════

class TestMultiConditionButton(unittest.TestCase):
    def setUp(self):
        _reset()
        self.log = []
        _make_mock_plugin("mc.test", self.log)
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.variable_manager import VariableManager
        VariableManager.set_value("vol", 80, VariableType.INTEGER, save=False)
        VariableManager.set_value("muted", False, VariableType.BOOL, save=False)

    def _btn(self):
        from macro_deck_python.models.action_button import ActionButton, ActionEntry, Condition
        btn = ActionButton()
        # Condition 1: vol > 50
        btn.conditions.append(Condition("vol", ">", "50",
            actions_true=[ActionEntry("mc.test", "mock", json.dumps({"c": "vol_high"}))],
            actions_false=[ActionEntry("mc.test", "mock", json.dumps({"c": "vol_low"}))],
        ))
        # Condition 2: muted == False
        btn.conditions.append(Condition("muted", "==", "False",
            actions_true=[ActionEntry("mc.test", "mock", json.dumps({"c": "not_muted"}))],
            actions_false=[ActionEntry("mc.test", "mock", json.dumps({"c": "muted"}))],
        ))
        return btn

    def test_both_conditions_evaluated(self):
        from macro_deck_python.services.action_executor import execute_button
        execute_button(self._btn(), "mc-client")
        time.sleep(0.2)
        cs = [e["c"] for e in self.log]
        self.assertIn("vol_high", cs)
        self.assertIn("not_muted", cs)
        self.assertNotIn("vol_low", cs)
        self.assertNotIn("muted", cs)

    def test_second_condition_independent(self):
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.action_executor import execute_button
        VariableManager.set_value("vol", 10, VariableType.INTEGER, save=False)
        execute_button(self._btn(), "mc-client")
        time.sleep(0.2)
        cs = [e["c"] for e in self.log]
        self.assertIn("vol_low", cs)
        self.assertIn("not_muted", cs)


# ═══════════════════════════════════════════════════════════════════════
# 7. PER-CLIENT PROFILE ROUTING
# ═══════════════════════════════════════════════════════════════════════

class TestClientProfileRouting(unittest.TestCase):
    def setUp(self):
        _reset()
        self.log = []
        _make_mock_plugin("route.test", self.log)
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.models.action_button import ActionButton, ActionEntry
        self.p_work = ProfileManager.create_profile("Work")
        self.p_game = ProfileManager.create_profile("Gaming")
        btn_w = ActionButton(label="Work Btn")
        btn_w.actions.append(ActionEntry("route.test","mock",json.dumps({"profile":"work"})))
        btn_g = ActionButton(label="Game Btn")
        btn_g.actions.append(ActionEntry("route.test","mock",json.dumps({"profile":"gaming"})))
        self.p_work.folder.set_button(0, 0, btn_w)
        self.p_game.folder.set_button(0, 0, btn_g)
        ProfileManager.set_active(self.p_work.profile_id)

    def test_clients_see_different_profiles(self):
        from macro_deck_python.services.profile_manager import ProfileManager
        ProfileManager.set_client_profile("c-work", self.p_work.profile_id)
        ProfileManager.set_client_profile("c-game", self.p_game.profile_id)
        self.assertEqual(ProfileManager.get_client_profile("c-work").name, "Work")
        self.assertEqual(ProfileManager.get_client_profile("c-game").name, "Gaming")

    def test_unknown_client_gets_active_profile(self):
        from macro_deck_python.services.profile_manager import ProfileManager
        profile = ProfileManager.get_client_profile("unknown-client")
        self.assertIs(profile, ProfileManager.get_active())

    def test_button_press_routes_to_correct_profile(self):
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.services.action_executor import execute_button
        ProfileManager.set_client_profile("c-work", self.p_work.profile_id)
        ProfileManager.set_client_profile("c-game", self.p_game.profile_id)
        btn_w = self.p_work.folder.get_button(0, 0)
        btn_g = self.p_game.folder.get_button(0, 0)
        execute_button(btn_w, "c-work")
        execute_button(btn_g, "c-game")
        time.sleep(0.2)
        profiles = [e["profile"] for e in self.log]
        self.assertIn("work", profiles)
        self.assertIn("gaming", profiles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
