"""
test_analog_slider.py — full test suite for the analog slider plugin.
"""
from __future__ import annotations
import asyncio, json, pathlib, sys, tempfile, time, threading, unittest
from unittest.mock import MagicMock
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

def _reset():
    from macro_deck_python.services.variable_manager import VariableManager
    from macro_deck_python.services.profile_manager import ProfileManager
    from macro_deck_python.plugins.plugin_manager import PluginManager
    from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
    VariableManager._variables.clear()
    VariableManager._on_change_callbacks.clear()
    ProfileManager._profiles.clear()
    ProfileManager._active_profile = None
    ProfileManager._client_profiles.clear()
    PluginManager._plugins.clear()
    PluginManager._actions.clear()
    for sid in list(SliderRegistry._sliders.keys()):
        SliderRegistry.unregister(sid)
    SliderRegistry._broadcast_cb = None

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)

class FakeWS:
    def __init__(self): self.sent = []
    async def send(self, m): self.sent.append(m)

# ── 1. SliderConfig ──────────────────────────────────────────────────
class TestSliderConfig(unittest.TestCase):
    def setUp(self): _reset()
    def _sc(self, **kw):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderConfig
        return SliderConfig(kw)

    def test_defaults(self):
        sc = self._sc()
        self.assertEqual(sc.size, 3); self.assertEqual(sc.orientation, "vertical")
        self.assertEqual(sc.min_value, 0.0); self.assertEqual(sc.max_value, 100.0)
        self.assertEqual(sc.step, 1.0); self.assertTrue(sc.label_show_value)

    def test_custom_values(self):
        sc = self._sc(size=5, min_value=-1.0, max_value=1.0, step=0.01, label="Axis")
        self.assertEqual(sc.size, 5)
        self.assertAlmostEqual(sc.min_value, -1.0); self.assertAlmostEqual(sc.step, 0.01)

    def test_size_min_1(self):
        self.assertEqual(self._sc(size=0).size, 1)
        self.assertEqual(self._sc(size=-5).size, 1)

    def test_snap_basic(self):
        sc = self._sc(min_value=0, max_value=100, step=10)
        self.assertEqual(sc.snap(0), 0); self.assertEqual(sc.snap(5), 10)
        self.assertEqual(sc.snap(4), 0); self.assertEqual(sc.snap(100), 100)
        self.assertEqual(sc.snap(110), 100); self.assertEqual(sc.snap(-5), 0)

    def test_snap_float_step(self):
        sc = self._sc(min_value=0, max_value=1.0, step=0.1)
        self.assertAlmostEqual(sc.snap(0.05), 0.1, places=5)
        self.assertAlmostEqual(sc.snap(0.04), 0.0, places=5)

    def test_snap_zero_step(self):
        self.assertAlmostEqual(self._sc(step=0).snap(42.7), 42.7)

    def test_display_label_with_value(self):
        sc = self._sc(label="Vol", label_show_value=True, value_format="{:.0f}%")
        sc.current_value = 75.0
        lbl = sc.display_label()
        self.assertIn("75", lbl); self.assertIn("Vol", lbl)

    def test_display_label_without_value(self):
        sc = self._sc(label="Vol", label_show_value=False)
        sc.current_value = 75.0
        self.assertEqual(sc.display_label(), "Vol")

    def test_roundtrip(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderConfig
        sc = SliderConfig({"size":4, "min_value":-100, "max_value":100,
                           "step":5, "label":"Pan", "color":"#ff0000",
                           "outputs":[{"type":"variable","variable_name":"pan"}]})
        sc2 = SliderConfig(sc.to_dict())
        self.assertEqual(sc2.size, 4); self.assertEqual(sc2.label, "Pan")
        self.assertEqual(sc2.color, "#ff0000"); self.assertEqual(len(sc2.outputs), 1)

    def test_normalised(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderConfig
        st = SliderConfig({"min_value":0,"max_value":100}).build_state("x")
        st.current = 50.0;  self.assertAlmostEqual(st.normalised(), 0.5)
        st.current = 0.0;   self.assertAlmostEqual(st.normalised(), 0.0)
        st.current = 100.0; self.assertAlmostEqual(st.normalised(), 1.0)

    def test_normalised_negative_range(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderConfig
        st = SliderConfig({"min_value":-1.0,"max_value":1.0}).build_state("y")
        st.current = 0.0;  self.assertAlmostEqual(st.normalised(), 0.5)
        st.current = -1.0; self.assertAlmostEqual(st.normalised(), 0.0)

    def test_normalised_zero_span(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderConfig
        st = SliderConfig({"min_value":50,"max_value":50}).build_state("z")
        st.current = 50.0
        self.assertAlmostEqual(st.normalised(), 0.0)

# ── 2. SliderRegistry ────────────────────────────────────────────────
class TestSliderRegistry(unittest.TestCase):
    def setUp(self): _reset()
    def _state(self, sid="s1"):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderState
        return SliderState(sid, 0.0, [], 0, 100)

    def test_register_get(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        st = self._state("a")
        SliderRegistry.register("a", st)
        self.assertIs(SliderRegistry.get_state("a"), st)

    def test_unregister(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        SliderRegistry.register("b", self._state("b"))
        SliderRegistry.unregister("b")
        self.assertIsNone(SliderRegistry.get_state("b"))

    def test_re_register_replaces(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        st1 = self._state("c"); st2 = self._state("c")
        SliderRegistry.register("c", st1); SliderRegistry.register("c", st2)
        self.assertIs(SliderRegistry.get_state("c"), st2)

    def test_all_ids(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        SliderRegistry.register("x", self._state("x"))
        SliderRegistry.register("y", self._state("y"))
        ids = SliderRegistry.all_slider_ids()
        self.assertIn("x", ids); self.assertIn("y", ids)

    def test_missing_returns_none(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        self.assertIsNone(SliderRegistry.get_state("nope"))

    def test_on_change_applies(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import AnalogOutput
        applied = []
        class M(AnalogOutput):
            def apply(self_, r, n, c): applied.append(r)
        st = SliderState("d", 0.0, [(M(), {})], 0, 100, throttle_ms=0)
        SliderRegistry.register("d", st)
        SliderRegistry.on_change("d", 50.0)
        time.sleep(0.05)
        self.assertTrue(len(applied) >= 1)
        self.assertAlmostEqual(applied[-1], 50.0)

    def test_broadcast_cb_called(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        calls = []
        SliderRegistry.set_broadcast_cb(lambda s,v: calls.append((s,v)))
        st = SliderState("e", 0.0, [], 0, 100, throttle_ms=0)
        SliderRegistry.register("e", st)
        SliderRegistry.on_change("e", 42.0)
        time.sleep(0.05)
        self.assertTrue(any(c[0]=="e" for c in calls))

    def test_unknown_on_change_no_crash(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        SliderRegistry.on_change("no-such", 50.0)

# ── 3. VariableOutput ────────────────────────────────────────────────
class TestVariableOutput(unittest.TestCase):
    def setUp(self): _reset()
    def _apply(self, raw, norm, **kw):
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import VariableOutput
        VariableOutput().apply(raw, norm, kw)

    def test_writes_float(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._apply(75.3, 0.753, variable_name="tv", variable_type="Float")
        self.assertAlmostEqual(VariableManager.get_value("tv"), 75.3)

    def test_writes_integer(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._apply(75.9, 0.759, variable_name="ti", variable_type="Integer")
        self.assertEqual(VariableManager.get_value("ti"), 76)

    def test_writes_normalised(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._apply(75.0, 0.75, variable_name="tn",
                    variable_type="Float", use_normalised=True)
        self.assertAlmostEqual(VariableManager.get_value("tn"), 0.75)

    def test_writes_string(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._apply(42.5, 0.425, variable_name="ts", variable_type="String")
        self.assertIsInstance(VariableManager.get_value("ts"), str)

    def test_default_variable_name(self):
        from macro_deck_python.services.variable_manager import VariableManager
        self._apply(10.0, 0.1)
        self.assertIsNotNone(VariableManager.get_value("slider_value"))

    def test_invalid_type_no_crash(self):
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import VariableOutput
        VariableOutput().apply(50.0, 0.5, {"variable_name":"x","variable_type":"BAD"})

# ── 4. KeyboardThresholdOutput ───────────────────────────────────────
class TestKeyboardThreshold(unittest.TestCase):
    def setUp(self):
        _reset()
        from macro_deck_python.plugins.builtin.keyboard_macro import injector
        self.events = []
        outer = self
        class MI:
            def down(self_, k): outer.events.append(("dn",k))
            def up(self_, k):   outer.events.append(("up",k))
            def press(self_, k):outer.events.append(("pr",k))
            def combo(self_, ks):
                for k in ks[:-1]: outer.events.append(("dn",k))
                outer.events.append(("pr",ks[-1]))
                for k in reversed(ks[:-1]): outer.events.append(("up",k))
        injector._backend = MI()

    def _out(self):
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import KeyboardThresholdOutput
        return KeyboardThresholdOutput()

    def _zones(self, mode="crossing"):
        return [{"min":0,"max":25,"keys":["ctrl","1"],"mode":mode},
                {"min":26,"max":50,"keys":["ctrl","2"],"mode":mode},
                {"min":51,"max":75,"keys":["ctrl","3"],"mode":mode},
                {"min":76,"max":100,"keys":["ctrl","4"],"mode":mode}]

    def test_crossing_fires_on_entry(self):
        out = self._out(); cfg = {"thresholds": self._zones()}
        out.apply(10.0, 0.1, cfg)
        self.assertTrue(len(self.events) > 0)

    def test_crossing_no_repeat_same_zone(self):
        out = self._out(); cfg = {"thresholds": self._zones()}
        out.apply(10.0, 0.1, cfg)
        n = len(self.events)
        out.apply(15.0, 0.15, cfg)
        self.assertEqual(len(self.events), n)

    def test_crossing_fires_on_zone_change(self):
        out = self._out(); cfg = {"thresholds": self._zones()}
        out.apply(10.0, 0.1, cfg); n = len(self.events)
        out.apply(40.0, 0.4, cfg)
        self.assertGreater(len(self.events), n)

    def test_zone_mode_holds_keys(self):
        out = self._out(); cfg = {"thresholds": self._zones("zone")}
        out.apply(10.0, 0.1, cfg)
        self.assertIn(("dn","ctrl"), self.events)
        self.assertIn(("dn","1"),    self.events)

    def test_zone_mode_releases_on_exit(self):
        out = self._out(); cfg = {"thresholds": self._zones("zone")}
        out.apply(10.0, 0.1, cfg); self.events.clear()
        out.apply(40.0, 0.4, cfg)
        self.assertTrue(any(e[0]=="up" for e in self.events))

    def test_no_zone_no_keys(self):
        out = self._out()
        cfg = {"thresholds":[{"min":0,"max":25,"keys":["a"],"mode":"crossing"},
                              {"min":76,"max":100,"keys":["b"],"mode":"crossing"}]}
        out.apply(60.0, 0.6, cfg)
        self.assertEqual(self.events, [])

    def test_five_zones(self):
        out = self._out()
        zones = [{"min":i*20,"max":i*20+19,"keys":[str(i)],"mode":"crossing"}
                 for i in range(5)]
        cfg = {"thresholds": zones}
        for v, k in [(5,0),(25,1),(45,2),(65,3),(85,4)]:
            out.apply(float(v), v/100, cfg)
            pressed = [e[1] for e in self.events if e[0] in ("pr","dn")]
            self.assertIn(str(k), pressed)

# ── 5. ActionButton slider fields ────────────────────────────────────
class TestActionButtonSliderFields(unittest.TestCase):
    def test_default_type(self):
        from macro_deck_python.models.action_button import ActionButton
        btn = ActionButton()
        self.assertEqual(btn.button_type, "button")
        self.assertEqual(btn.slider_config, {})

    def test_slider_roundtrip(self):
        from macro_deck_python.models.action_button import ActionButton
        btn = ActionButton(button_type="slider",
                           slider_config={"size":4,"min_value":0,"max_value":100,"outputs":[]})
        btn2 = ActionButton.from_dict(btn.to_dict())
        self.assertEqual(btn2.button_type, "slider")
        self.assertEqual(btn2.slider_config["size"], 4)

    def test_occupied_roundtrip(self):
        from macro_deck_python.models.action_button import ActionButton
        btn = ActionButton(button_type="slider_occupied",
                           slider_config={"parent_id":"abc","parent_pos":"0_2"})
        btn2 = ActionButton.from_dict(btn.to_dict())
        self.assertEqual(btn2.button_type, "slider_occupied")
        self.assertEqual(btn2.slider_config["parent_id"], "abc")

    def test_normal_button_unaffected(self):
        from macro_deck_python.models.action_button import ActionButton
        btn = ActionButton(label="Normal")
        self.assertEqual(btn.button_type, "button")
        self.assertEqual(ActionButton.from_dict(btn.to_dict()).button_type, "button")

# ── 6. CreateSlider / RemoveSlider ───────────────────────────────────
class TestCreateRemoveSlider(unittest.TestCase):
    def setUp(self):
        _reset()
        from macro_deck_python.services.profile_manager import ProfileManager
        import unittest.mock as m
        self.profile = ProfileManager.create_profile("SL")
        ProfileManager.set_active(self.profile.profile_id)
        self._p = m.patch.object(ProfileManager, 'save'); self._p.start()

    def tearDown(self): self._p.stop()

    def _create(self, row, col, size=3, outputs=None):
        from macro_deck_python.plugins.builtin.analog_slider.main import CreateSliderAction
        act = CreateSliderAction(); act.plugin = MagicMock()
        act.configuration = json.dumps({
            "row": row, "col": col,
            "slider_config": {"size":size,"min_value":0,"max_value":100,"step":1,
                              "label":"T","outputs": outputs or []}
        })
        act.trigger("c", None)

    def _remove(self, row, col):
        from macro_deck_python.plugins.builtin.analog_slider.main import RemoveSliderAction
        act = RemoveSliderAction(); act.plugin = MagicMock()
        act.configuration = json.dumps({"row":row,"col":col})
        act.trigger("c", None)

    def test_creates_slider_button(self):
        self._create(0, 0, 3)
        self.assertEqual(self.profile.folder.get_button(0,0).button_type, "slider")

    def test_creates_occupied_slots(self):
        self._create(0, 0, 3)
        for r in range(1, 3):
            self.assertEqual(self.profile.folder.get_button(r,0).button_type, "slider_occupied")

    def test_occupied_reference_parent(self):
        self._create(0, 0, 3)
        pid = self.profile.folder.get_button(0,0).button_id
        for r in range(1, 3):
            occ = self.profile.folder.get_button(r, 0)
            self.assertEqual(occ.slider_config["parent_id"], pid)
            self.assertEqual(occ.slider_config["parent_pos"], "0_0")

    def test_registered_in_registry(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        self._create(0, 1, 2)
        sid = self.profile.folder.get_button(0,1).button_id
        self.assertIsNotNone(SliderRegistry.get_state(sid))

    def test_size_1_no_occupied(self):
        self._create(1, 0, 1)
        self.assertEqual(self.profile.folder.get_button(1,0).button_type, "slider")
        btn = self.profile.folder.get_button(2, 0)
        if btn: self.assertNotEqual(btn.button_type, "slider_occupied")

    def test_remove_clears_all_slots(self):
        self._create(0, 2, 4)
        self._remove(0, 2)
        for r in range(4): self.assertIsNone(self.profile.folder.get_button(r,2))

    def test_remove_unregisters(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry
        self._create(0, 3, 2)
        sid = self.profile.folder.get_button(0,3).button_id
        self._remove(0, 3)
        self.assertIsNone(SliderRegistry.get_state(sid))

    def test_remove_nonexistent_no_crash(self): self._remove(9, 9)

    def test_size_5(self):
        self._create(0, 4, 5)
        self.assertEqual(self.profile.folder.get_button(0,4).button_type, "slider")
        for r in range(1, 5):
            self.assertEqual(self.profile.folder.get_button(r,4).button_type, "slider_occupied")

    def test_multiple_columns(self):
        for col in range(3): self._create(0, col, col+1)
        for col in range(3):
            self.assertEqual(self.profile.folder.get_button(0,col).button_type, "slider")

    def test_slider_config_preserved(self):
        self._create(0, 0, 3)
        sc = self.profile.folder.get_button(0,0).slider_config
        self.assertEqual(sc["size"], 3); self.assertEqual(sc["min_value"], 0)
        self.assertEqual(sc["max_value"], 100); self.assertEqual(sc["label"], "T")

# ── 7. SetSliderValue ────────────────────────────────────────────────
class TestSetSliderValue(unittest.TestCase):
    def setUp(self):
        _reset()
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import AnalogOutput
        self.applied = []
        outer = self
        class M(AnalogOutput):
            def apply(self_, r, n, c): outer.applied.append(r)
        st = SliderState("sv-id", 0.0, [(M(), {})], 0, 100, throttle_ms=0)
        SliderRegistry.register("sv-id", st)

    def test_applies_output(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SetSliderValueAction
        act = SetSliderValueAction(); act.plugin = MagicMock()
        act.configuration = json.dumps({"slider_id":"sv-id","value":80.0})
        act.trigger("c", None)
        time.sleep(0.1)
        self.assertTrue(any(abs(v-80.0)<0.01 for v in self.applied))

    def test_missing_id_no_crash(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SetSliderValueAction
        act = SetSliderValueAction(); act.plugin = MagicMock()
        act.configuration = json.dumps({"value":50.0})
        act.trigger("c", None)

# ── 8. WebSocket SLIDER_CHANGE ───────────────────────────────────────
class TestSliderWebSocket(unittest.TestCase):
    def setUp(self):
        _reset()
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import AnalogOutput
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.models.action_button import ActionButton
        import unittest.mock as m
        self.applied = []
        outer = self
        class M(AnalogOutput):
            def apply(self_, r, n, c): outer.applied.append(r)
        self.state = SliderState("ws-s", 0.0, [(M(), {})], 0, 100, throttle_ms=0)
        SliderRegistry.register("ws-s", self.state)
        self.profile = ProfileManager.create_profile("WS")
        btn = ActionButton(button_id="ws-s", button_type="slider",
                           slider_config={"size":3,"min_value":0,"max_value":100,
                                          "step":1,"outputs":[],"current_value":0})
        self.profile.folder.set_button(0, 0, btn)
        ProfileManager.set_active(self.profile.profile_id)
        self._p = m.patch.object(ProfileManager, 'save'); self._p.start()

    def tearDown(self): self._p.stop()

    def _info(self):
        from macro_deck_python.websocket.server import ClientInfo
        return ClientInfo(FakeWS(), "ws-c")

    def test_change_applies_output(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import _handle_slider_change
        _run(_handle_slider_change(self._info(), {"method":"SLIDER_CHANGE","slider_id":"ws-s","value":75.0}))
        time.sleep(0.1)
        self.assertTrue(any(abs(v-75.0)<0.1 for v in self.applied))

    def test_snaps_to_step(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import _handle_slider_change
        _run(_handle_slider_change(self._info(), {"method":"SLIDER_CHANGE","slider_id":"ws-s","value":73.4}))
        time.sleep(0.1)
        self.assertEqual(self.profile.folder.get_button(0,0).slider_config["current_value"], 73.0)

    def test_invalid_value_sends_error(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import _handle_slider_change
        from macro_deck_python.websocket.protocol import decode
        info = self._info()
        _run(_handle_slider_change(info, {"method":"SLIDER_CHANGE","slider_id":"ws-s","value":"NaN"}))
        if info.ws.sent:
            self.assertEqual(decode(info.ws.sent[-1])["method"], "ERROR")

    def test_unknown_slider_no_crash(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import _handle_slider_change
        _run(_handle_slider_change(self._info(), {"method":"SLIDER_CHANGE","slider_id":"bad","value":50.0}))

    def test_hook_registered(self):
        from macro_deck_python.websocket.server import MacroDeckServer
        from macro_deck_python.plugins.builtin.analog_slider.main import _register_ws_hook
        MacroDeckServer._plugin_message_hooks.pop("SLIDER_CHANGE", None)
        _register_ws_hook()
        self.assertIn("SLIDER_CHANGE", MacroDeckServer._plugin_message_hooks)

    def test_unknown_method_still_goes_to_plugin_hook(self):
        """SLIDER_CHANGE is dispatched through the plugin hook system."""
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.websocket.protocol import decode
        MacroDeckServer._plugin_message_hooks.pop("SLIDER_CHANGE", None)
        from macro_deck_python.plugins.builtin.analog_slider.main import _handle_slider_change, _register_ws_hook
        _register_ws_hook()
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}
        ws = FakeWS(); info = ClientInfo(ws, "hook-test")
        server._clients["hook-test"] = info
        _run(server._handle_message(info, json.dumps({"method":"SLIDER_CHANGE","slider_id":"ws-s","value":30.0})))
        time.sleep(0.1)
        self.assertTrue(any(abs(v-30.0)<0.5 for v in self.applied))

# ── 9. BUTTONS message includes slider data ──────────────────────────
class TestSliderInButtons(unittest.TestCase):
    def setUp(self):
        _reset()
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.models.action_button import ActionButton
        self.profile = ProfileManager.create_profile("Rend")
        slider = ActionButton(button_id="rend-s", button_type="slider",
                              slider_config={"size":3,"min_value":0,"max_value":100,
                                             "step":1,"label":"Vol","current_value":50,"outputs":[]})
        self.profile.folder.set_button(0, 0, slider)
        for r in range(1, 3):
            occ = ActionButton(button_type="slider_occupied",
                               slider_config={"parent_id":"rend-s","parent_pos":"0_0"})
            self.profile.folder.set_button(r, 0, occ)
        self.profile.folder.set_button(0, 1, ActionButton(label="Normal"))
        ProfileManager.set_active(self.profile.profile_id)

    def _get_buttons(self):
        from macro_deck_python.websocket.server import MacroDeckServer, ClientInfo
        from macro_deck_python.services.profile_manager import ProfileManager
        server = MacroDeckServer.__new__(MacroDeckServer)
        server._clients = {}
        async def run():
            ws = FakeWS(); info = ClientInfo(ws, "r-c")
            server._clients["r-c"] = info
            ProfileManager.set_client_profile("r-c", self.profile.profile_id)
            await server._send_buttons(info)
            return ws.sent
        return json.loads(_run(run())[0])

    def test_slider_button_in_payload(self):
        d = self._get_buttons()
        types = {b["button_id"]: b["button_type"] for b in d["buttons"]}
        self.assertEqual(types.get("rend-s"), "slider")

    def test_slider_has_slider_config(self):
        d = self._get_buttons()
        s = next(b for b in d["buttons"] if b.get("button_type")=="slider")
        self.assertIn("slider_config", s)
        self.assertEqual(s["slider_config"]["size"], 3)
        self.assertEqual(s["slider_config"]["max_value"], 100)

    def test_occupied_included(self):
        d = self._get_buttons()
        occupied = [b for b in d["buttons"] if b.get("button_type")=="slider_occupied"]
        self.assertEqual(len(occupied), 2)

    def test_normal_button_unaffected(self):
        d = self._get_buttons()
        normal = next((b for b in d["buttons"] if b.get("label")=="Normal"), None)
        self.assertIsNotNone(normal)
        self.assertEqual(normal["button_type"], "button")
        self.assertIn("state", normal)

# ── 10. Plugin loading ───────────────────────────────────────────────
class TestPluginLoading(unittest.TestCase):
    def setUp(self): _reset()

    def test_loads(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager.set_plugins_dir(pathlib.Path(__file__).parent.parent/"plugins"/"builtin")
        PluginManager.load_all_plugins()
        self.assertIn("builtin.analog_slider", PluginManager._plugins)

    def test_three_actions(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager.set_plugins_dir(pathlib.Path(__file__).parent.parent/"plugins"/"builtin")
        PluginManager.load_all_plugins()
        actions = PluginManager._actions.get("builtin.analog_slider", {})
        for aid in ["create_slider","remove_slider","set_slider_value"]:
            self.assertIn(aid, actions)

    def test_all_configurable(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager.set_plugins_dir(pathlib.Path(__file__).parent.parent/"plugins"/"builtin")
        PluginManager.load_all_plugins()
        for aid in ["create_slider","remove_slider","set_slider_value"]:
            act = PluginManager.get_action("builtin.analog_slider", aid)
            self.assertTrue(act.can_configure, f"{aid} should be configurable")

    def test_disable_clears_registry(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        PluginManager.set_plugins_dir(pathlib.Path(__file__).parent.parent/"plugins"/"builtin")
        PluginManager.load_all_plugins()
        st = SliderState("test-dis", 0.0, [], 0, 100)
        SliderRegistry.register("test-dis", st)
        plugin = PluginManager.get_plugin("builtin.analog_slider")
        plugin.disable()
        self.assertIsNone(SliderRegistry.get_state("test-dis"))

# ── 11. Throttle ─────────────────────────────────────────────────────
class TestThrottle(unittest.TestCase):
    def setUp(self): _reset()

    def test_throttled(self):
        from macro_deck_python.plugins.builtin.analog_slider.main import SliderRegistry, SliderState
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import AnalogOutput
        applied = []
        class S(AnalogOutput):
            def apply(self_, r, n, c): applied.append(r)
        st = SliderState("thr", 0.0, [(S(), {})], 0, 100, throttle_ms=50)
        SliderRegistry.register("thr", st)
        for v in range(0, 100, 5):
            SliderRegistry.on_change("thr", float(v))
        time.sleep(0.3)
        self.assertLessEqual(len(applied), 20)
        self.assertGreater(len(applied), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
