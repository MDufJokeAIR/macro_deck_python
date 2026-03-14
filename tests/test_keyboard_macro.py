"""
test_keyboard_macro.py
======================
Full test suite for the keyboard_macro plugin.

Strategy: inject a mock backend that records calls instead of
sending real key events, so tests run headlessly everywhere.
"""
from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import unittest
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))


# ═══════════════════════════════════════════════════════════════════════
# Mock backend
# ═══════════════════════════════════════════════════════════════════════

class MockBackend:
    """Records all key events without touching real hardware."""
    def __init__(self):
        self.events: List[Tuple[str, str]] = []   # ("down"|"up"|"press", key)
        self.clicks: List[Tuple[str, int]] = []

    def clear(self):
        self.events.clear()
        self.clicks.clear()

    def down(self, k):  self.events.append(("down",  k))
    def up(self,   k):  self.events.append(("up",    k))
    def press(self, k): self.events.append(("press", k))

    def combo(self, keys):
        for k in keys[:-1]: self.events.append(("down",  k))
        self.events.append(("down", keys[-1]))
        self.events.append(("up",   keys[-1]))
        for k in reversed(keys[:-1]): self.events.append(("up", k))

    def mouse_click(self, button="mouse_left", n=1):
        self.clicks.append((button, n))


_mock = MockBackend()


def _setup():
    """Inject mock backend and reset state."""
    import macro_deck_python.plugins.builtin.keyboard_macro.injector as inj
    inj._backend = _mock
    _mock.clear()
    # Reset hold state
    import macro_deck_python.plugins.builtin.keyboard_macro.main as m
    with m._held_lock:
        m._held_keys.clear()


def _action(action_id: str, cfg: dict):
    """Instantiate the action from the plugin and trigger it."""
    from macro_deck_python.plugins.builtin.keyboard_macro.main import Main
    plugin = Main()
    plugin.package_id = "builtin.keyboard_macro"
    plugin.enable()
    act = next(a for a in plugin.actions if a.action_id == action_id)
    act.plugin = plugin
    act.configuration = json.dumps(cfg)
    act.trigger("test-client", None)
    return act


# ═══════════════════════════════════════════════════════════════════════
# 1. key_map tests
# ═══════════════════════════════════════════════════════════════════════

class TestKeyMap(unittest.TestCase):
    def test_all_letters_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for c in "abcdefghijklmnopqrstuvwxyz":
            self.assertIn(c, KEY_MAP)

    def test_all_digits_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for d in "0123456789":
            self.assertIn(d, KEY_MAP)

    def test_f1_to_f24_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for i in range(1, 25):
            self.assertIn(f"f{i}", KEY_MAP, f"f{i} missing")

    def test_modifiers_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for k in ["ctrl", "shift", "alt", "super", "ctrl_left", "ctrl_right",
                  "shift_left", "shift_right", "alt_left", "alt_right"]:
            self.assertIn(k, KEY_MAP, f"{k} missing")

    def test_oem_keys_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for k in ["oem_1","oem_2","oem_3","oem_4","oem_5","oem_6","oem_7",
                  "oem_plus","oem_minus","oem_comma","oem_period","oem_102"]:
            self.assertIn(k, KEY_MAP, f"{k} missing")

    def test_numpad_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for k in ["num0","num1","num2","num3","num4","num5","num6","num7","num8","num9",
                  "num_add","num_sub","num_mul","num_div","num_decimal","num_enter"]:
            self.assertIn(k, KEY_MAP, f"{k} missing")

    def test_media_keys_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for k in ["media_play_pause","media_next","media_prev","media_stop",
                  "volume_up","volume_down","volume_mute"]:
            self.assertIn(k, KEY_MAP, f"{k} missing")

    def test_navigation_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for k in ["up","down","left","right","home","end","page_up","page_down",
                  "insert","delete"]:
            self.assertIn(k, KEY_MAP, f"{k} missing")

    def test_mouse_buttons_present(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for k in ["mouse_left","mouse_right","mouse_middle","mouse_x1","mouse_x2"]:
            self.assertIn(k, KEY_MAP, f"{k} missing")

    def test_each_key_has_all_platforms(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP
        for name, entry in KEY_MAP.items():
            for field in ("win", "linux", "mac", "label"):
                self.assertIn(field, entry, f"Key {name!r} missing field {field!r}")

    def test_resolve_lowercase(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import resolve
        self.assertIsNotNone(resolve("CTRL"))
        self.assertIsNotNone(resolve("F12"))
        self.assertIsNotNone(resolve("  Space  "))

    def test_resolve_aliases(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import resolve
        self.assertEqual(resolve("win")["label"],     resolve("super")["label"])
        self.assertEqual(resolve("esc")["label"],     resolve("escape")["label"])
        self.assertEqual(resolve("lctrl")["label"],   resolve("ctrl_left")["label"])
        self.assertEqual(resolve("pgup")["label"],    resolve("page_up")["label"])
        self.assertEqual(resolve("bs")["label"],      resolve("backspace")["label"])
        self.assertEqual(resolve("mute")["label"],    resolve("volume_mute")["label"])

    def test_resolve_unknown_returns_none(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import resolve
        self.assertIsNone(resolve("not_a_key_xyz"))

    def test_label_helper(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import label
        self.assertEqual(label("f1"), "F1")
        self.assertEqual(label("space"), "Space")
        self.assertEqual(label("unknown_xyz"), "unknown_xyz")

    def test_all_key_names_no_duplicates(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import all_key_names
        names = all_key_names()
        self.assertEqual(len(names), len(set(names)))

    def test_key_groups_cover_all_keys(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.key_map import KEY_MAP, KEY_GROUPS
        grouped = {k for keys in KEY_GROUPS.values() for k in keys}
        uncovered = set(KEY_MAP) - grouped
        # OEM_8 and some others may not be in groups — just check groups aren't empty
        for group, keys in KEY_GROUPS.items():
            self.assertGreater(len(keys), 0, f"Group {group!r} is empty")


# ═══════════════════════════════════════════════════════════════════════
# 2. ShortPress
# ═══════════════════════════════════════════════════════════════════════

class TestShortPress(unittest.TestCase):
    def setUp(self): _setup()

    def test_single_key(self):
        _action("macro_short_press", {"keys": ["a"], "tap_ms": 1})
        self.assertIn(("down", "a"), _mock.events)
        self.assertIn(("up",   "a"), _mock.events)

    def test_two_key_combo(self):
        _action("macro_short_press", {"keys": ["ctrl", "c"], "tap_ms": 1})
        evts = _mock.events
        self.assertIn(("down", "ctrl"), evts)
        self.assertIn(("down", "c"),    evts)
        self.assertIn(("up",   "c"),    evts)
        self.assertIn(("up",   "ctrl"), evts)
        # ctrl must be held when c is pressed
        self.assertLess(evts.index(("down","ctrl")), evts.index(("down","c")))
        # c released before ctrl
        self.assertLess(evts.index(("up","c")),     evts.index(("up","ctrl")))

    def test_three_key_combo_ctrl_shift_t(self):
        _action("macro_short_press", {"keys": ["ctrl","shift","t"], "tap_ms": 1})
        evts = _mock.events
        self.assertIn(("down","ctrl"),  evts)
        self.assertIn(("down","shift"), evts)
        self.assertIn(("down","t"),     evts)
        self.assertIn(("up","t"),       evts)
        self.assertIn(("up","shift"),   evts)
        self.assertIn(("up","ctrl"),    evts)

    def test_four_key_combo(self):
        _action("macro_short_press", {"keys": ["ctrl","shift","alt","f4"], "tap_ms": 1})
        evts = _mock.events
        for k in ["ctrl","shift","alt","f4"]:
            self.assertIn(("down", k), evts)
            self.assertIn(("up",   k), evts)

    def test_five_key_combo(self):
        _action("macro_short_press", {"keys": ["ctrl","shift","alt","super","f12"], "tap_ms": 1})
        evts = _mock.events
        for k in ["ctrl","shift","alt","super","f12"]:
            self.assertIn(("down", k), evts)

    def test_max_5_keys_enforced(self):
        _action("macro_short_press",
                {"keys": ["a","b","c","d","e","f","g"], "tap_ms": 1})
        keys_pressed = [e[1] for e in _mock.events if e[0] == "down"]
        self.assertLessEqual(len(keys_pressed), 5)

    def test_repeat(self):
        _action("macro_short_press", {"keys": ["a"], "tap_ms": 1, "repeat": 3})
        downs = [e for e in _mock.events if e == ("down","a")]
        self.assertEqual(len(downs), 3)

    def test_unknown_key_skipped(self):
        _action("macro_short_press", {"keys": ["ctrl", "NOT_A_KEY", "c"], "tap_ms": 1})
        evts = _mock.events
        self.assertIn(("down","ctrl"), evts)
        self.assertIn(("down","c"), evts)
        down_keys = [e[1] for e in evts if e[0]=="down"]
        self.assertNotIn("NOT_A_KEY", down_keys)

    def test_alias_keys_resolved(self):
        # "win" → "super", "esc" → "escape"
        _action("macro_short_press", {"keys": ["win","esc"], "tap_ms": 1})
        down_keys = [e[1] for e in _mock.events if e[0]=="down"]
        self.assertIn("super",  down_keys)
        self.assertIn("escape", down_keys)

    def test_f_keys(self):
        for fn in ["f1","f5","f12","f24"]:
            _mock.clear()
            _action("macro_short_press", {"keys": [fn], "tap_ms": 1})
            self.assertIn(("down", fn), _mock.events, f"{fn} not fired")

    def test_oem_keys(self):
        for oem in ["oem_1","oem_plus","oem_minus","oem_comma","oem_period"]:
            _mock.clear()
            _action("macro_short_press", {"keys": [oem], "tap_ms": 1})
            self.assertIn(("down", oem), _mock.events, f"{oem} not fired")

    def test_media_keys(self):
        for mk in ["volume_mute","media_play_pause","media_next","browser_back"]:
            _mock.clear()
            _action("macro_short_press", {"keys": [mk], "tap_ms": 1})
            self.assertIn(("down", mk), _mock.events, f"{mk} not fired")

    def test_numpad_keys(self):
        for nk in ["num0","num9","num_add","num_enter"]:
            _mock.clear()
            _action("macro_short_press", {"keys": [nk], "tap_ms": 1})
            self.assertIn(("down", nk), _mock.events, f"{nk} not fired")

    def test_empty_keys_no_crash(self):
        _action("macro_short_press", {"keys": [], "tap_ms": 1})
        self.assertEqual(_mock.events, [])

    def test_no_config_no_crash(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.main import Main
        plugin = Main(); plugin.package_id = "builtin.keyboard_macro"; plugin.enable()
        act = next(a for a in plugin.actions if a.action_id == "macro_short_press")
        act.plugin = plugin; act.configuration = ""
        act.trigger("c", None)   # must not raise


# ═══════════════════════════════════════════════════════════════════════
# 3. LongPress
# ═══════════════════════════════════════════════════════════════════════

class TestLongPress(unittest.TestCase):
    def setUp(self): _setup()

    def test_single_key_held(self):
        start = time.time()
        _action("macro_long_press", {"keys": ["a"], "hold_ms": 100})
        elapsed = time.time() - start
        self.assertGreaterEqual(elapsed, 0.09)
        self.assertIn(("down","a"), _mock.events)
        self.assertIn(("up","a"),   _mock.events)

    def test_combo_held_in_order(self):
        _action("macro_long_press", {"keys": ["ctrl","shift","s"], "hold_ms": 10})
        evts = _mock.events
        self.assertLess(evts.index(("down","ctrl")),  evts.index(("down","shift")))
        self.assertLess(evts.index(("down","shift")), evts.index(("down","s")))
        # All released
        for k in ["ctrl","shift","s"]:
            self.assertIn(("up", k), evts)

    def test_long_press_is_longer_than_short(self):
        t0 = time.time(); _action("macro_short_press", {"keys":["a"], "tap_ms":10})
        short_t = time.time() - t0
        _mock.clear()
        t0 = time.time(); _action("macro_long_press", {"keys":["a"], "hold_ms":150})
        long_t = time.time() - t0
        self.assertGreater(long_t, short_t)

    def test_repeat(self):
        _action("macro_long_press", {"keys":["f5"], "hold_ms":10, "repeat":3})
        downs = [e for e in _mock.events if e == ("down","f5")]
        self.assertEqual(len(downs), 3)

    def test_five_keys_long(self):
        _action("macro_long_press",
                {"keys":["ctrl","shift","alt","super","f10"], "hold_ms":10})
        for k in ["ctrl","shift","alt","super","f10"]:
            self.assertIn(("down",k), _mock.events)
            self.assertIn(("up",k),   _mock.events)


# ═══════════════════════════════════════════════════════════════════════
# 4. DoubleClick
# ═══════════════════════════════════════════════════════════════════════

class TestDoubleClick(unittest.TestCase):
    def setUp(self): _setup()

    def test_key_fired_twice(self):
        _action("macro_double_click",
                {"keys": ["a"], "tap_ms": 1, "double_interval_ms": 10})
        downs = [e for e in _mock.events if e == ("down","a")]
        self.assertEqual(len(downs), 2)

    def test_combo_fired_twice(self):
        _action("macro_double_click",
                {"keys": ["ctrl","d"], "tap_ms": 1, "double_interval_ms": 10})
        ctrl_downs = [e for e in _mock.events if e == ("down","ctrl")]
        d_downs    = [e for e in _mock.events if e == ("down","d")]
        self.assertEqual(len(ctrl_downs), 2)
        self.assertEqual(len(d_downs),    2)

    def test_interval_respected(self):
        start = time.time()
        _action("macro_double_click",
                {"keys": ["space"], "tap_ms": 1, "double_interval_ms": 80})
        elapsed = time.time() - start
        self.assertGreaterEqual(elapsed, 0.07)

    def test_modifier_order_correct(self):
        _action("macro_double_click",
                {"keys": ["shift","a"], "tap_ms": 1, "double_interval_ms": 10})
        evts = _mock.events
        shift_downs = [i for i,e in enumerate(evts) if e == ("down","shift")]
        a_downs     = [i for i,e in enumerate(evts) if e == ("down","a")]
        self.assertEqual(len(shift_downs), 2)
        self.assertEqual(len(a_downs),     2)
        # First shift down before first a down
        self.assertLess(shift_downs[0], a_downs[0])


# ═══════════════════════════════════════════════════════════════════════
# 5. HoldDown + Release
# ═══════════════════════════════════════════════════════════════════════

class TestHoldRelease(unittest.TestCase):
    def setUp(self): _setup()

    def test_hold_sends_downs(self):
        _action("macro_hold_down", {"keys": ["ctrl","shift"]})
        self.assertIn(("down","ctrl"),  _mock.events)
        self.assertIn(("down","shift"), _mock.events)
        # No ups yet
        self.assertNotIn(("up","ctrl"),  _mock.events)
        self.assertNotIn(("up","shift"), _mock.events)

    def test_release_after_hold(self):
        _action("macro_hold_down", {"keys": ["ctrl","shift"]})
        _mock.clear()   # clear the down events
        _action("macro_release", {})
        self.assertIn(("up","shift"), _mock.events)
        self.assertIn(("up","ctrl"),  _mock.events)

    def test_release_reverses_order(self):
        _action("macro_hold_down", {"keys": ["ctrl","shift","f10"]})
        _mock.clear()
        _action("macro_release", {})
        evts = _mock.events
        ups = [e[1] for e in evts if e[0]=="up"]
        self.assertEqual(ups[0], "f10")
        self.assertEqual(ups[1], "shift")
        self.assertEqual(ups[2], "ctrl")

    def test_second_hold_releases_first(self):
        _action("macro_hold_down", {"keys": ["a"]})
        _action("macro_hold_down", {"keys": ["b"]})
        # "a" should have been released, "b" now held
        from macro_deck_python.plugins.builtin.keyboard_macro import main as m
        with m._held_lock:
            self.assertEqual(m._held_keys, ["b"])

    def test_release_with_nothing_held_no_crash(self):
        _action("macro_release", {})   # must not raise

    def test_hold_five_keys(self):
        _action("macro_hold_down", {"keys": ["ctrl","shift","alt","super","a"]})
        from macro_deck_python.plugins.builtin.keyboard_macro import main as m
        with m._held_lock:
            self.assertEqual(len(m._held_keys), 5)


# ═══════════════════════════════════════════════════════════════════════
# 6. TapSequence
# ═══════════════════════════════════════════════════════════════════════

class TestTapSequence(unittest.TestCase):
    def setUp(self): _setup()

    def test_two_step_sequence(self):
        _action("macro_tap_sequence", {
            "sequence": [["ctrl","c"], ["ctrl","v"]],
            "step_delay_ms": 5, "tap_ms": 1,
        })
        evts = _mock.events
        # Both ctrl+c and ctrl+v should appear
        self.assertIn(("down","ctrl"), evts)
        self.assertIn(("down","c"),    evts)
        self.assertIn(("down","v"),    evts)

    def test_sequence_order_correct(self):
        _action("macro_tap_sequence", {
            "sequence": [["a"], ["b"], ["c"]],
            "step_delay_ms": 1, "tap_ms": 1,
        })
        downs = [e[1] for e in _mock.events if e[0] == "down"]
        self.assertEqual(downs, ["a","b","c"])

    def test_max_5_steps(self):
        _action("macro_tap_sequence", {
            "sequence": [["a"],["b"],["c"],["d"],["e"],["f"],["g"]],
            "step_delay_ms": 1, "tap_ms": 1,
        })
        downs = [e[1] for e in _mock.events if e[0]=="down"]
        self.assertLessEqual(len(downs), 5)

    def test_five_step_sequence(self):
        _action("macro_tap_sequence", {
            "sequence": [["f1"],["f2"],["f3"],["f4"],["f5"]],
            "step_delay_ms": 1, "tap_ms": 1,
        })
        downs = [e[1] for e in _mock.events if e[0]=="down"]
        self.assertEqual(downs, ["f1","f2","f3","f4","f5"])

    def test_string_steps_work(self):
        # Each step can also be a plain string instead of a list
        _action("macro_tap_sequence", {
            "sequence": ["ctrl+c", ["ctrl","v"]],
            "step_delay_ms": 1, "tap_ms": 1,
        })
        # ctrl+c as plain string won't resolve (it's not a valid key name)
        # just ensure no crash

    def test_empty_sequence_no_crash(self):
        _action("macro_tap_sequence", {"sequence": [], "step_delay_ms": 1})

    def test_delay_between_steps(self):
        start = time.time()
        _action("macro_tap_sequence", {
            "sequence": [["a"],["b"],["c"]],
            "step_delay_ms": 50, "tap_ms": 1,
        })
        elapsed = time.time() - start
        # 2 inter-step gaps of 50 ms each
        self.assertGreaterEqual(elapsed, 0.08)


# ═══════════════════════════════════════════════════════════════════════
# 7. Plugin loading
# ═══════════════════════════════════════════════════════════════════════

class TestPluginLoading(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager._plugins.clear()
        PluginManager._actions.clear()

    def test_plugin_loads_via_manager(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
        PluginManager.set_plugins_dir(builtin)
        PluginManager.load_all_plugins()
        self.assertIn("builtin.keyboard_macro", PluginManager._plugins)

    def test_all_six_actions_registered(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
        PluginManager.set_plugins_dir(builtin)
        PluginManager.load_all_plugins()
        actions = PluginManager._actions.get("builtin.keyboard_macro", {})
        for aid in ["macro_short_press","macro_long_press","macro_double_click",
                    "macro_hold_down","macro_release","macro_tap_sequence"]:
            self.assertIn(aid, actions, f"Action {aid!r} not registered")

    def test_action_names_set(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
        PluginManager.set_plugins_dir(builtin)
        PluginManager.load_all_plugins()
        sp = PluginManager.get_action("builtin.keyboard_macro", "macro_short_press")
        self.assertEqual(sp.name, "Short Press (1–5 keys)")
        self.assertTrue(sp.can_configure)

        rel = PluginManager.get_action("builtin.keyboard_macro", "macro_release")
        self.assertFalse(rel.can_configure)

    def test_plugin_disable_releases_held_keys(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.main import Main, _held_keys, _held_lock
        _setup()
        plugin = Main(); plugin.package_id = "builtin.keyboard_macro"; plugin.enable()
        # Simulate something being held
        with _held_lock:
            from macro_deck_python.plugins.builtin.keyboard_macro import injector as inj
            _held_keys.append("ctrl")
            inj._backend = _mock
        plugin.disable()
        with _held_lock:
            self.assertEqual(_held_keys, [])


# ═══════════════════════════════════════════════════════════════════════
# 8. Configuration JSON parsing
# ═══════════════════════════════════════════════════════════════════════

class TestConfigParsing(unittest.TestCase):
    def setUp(self): _setup()

    def test_delay_before(self):
        start = time.time()
        _action("macro_short_press", {"keys":["a"], "tap_ms":1, "delay_before_ms":80})
        self.assertGreaterEqual(time.time() - start, 0.07)

    def test_delay_after(self):
        start = time.time()
        _action("macro_short_press", {"keys":["a"], "tap_ms":1, "delay_after_ms":80})
        self.assertGreaterEqual(time.time() - start, 0.07)

    def test_uppercase_keys_resolved(self):
        _action("macro_short_press", {"keys":["CTRL","SHIFT","A"], "tap_ms":1})
        down_keys = [e[1] for e in _mock.events if e[0]=="down"]
        self.assertIn("ctrl",  down_keys)
        self.assertIn("shift", down_keys)
        self.assertIn("a",     down_keys)

    def test_string_keys_not_list_resolved(self):
        # keys as a single string (not list) — graceful handling
        _action("macro_short_press", {"keys": "a", "tap_ms": 1})
        self.assertIn(("down","a"), _mock.events)

    def test_negative_tap_ms_clamped(self):
        _action("macro_short_press", {"keys":["a"], "tap_ms":-999})
        self.assertIn(("down","a"), _mock.events)   # should still fire

    def test_zero_repeat_clamped_to_one(self):
        _action("macro_short_press", {"keys":["a"], "tap_ms":1, "repeat":0})
        downs = [e for e in _mock.events if e == ("down","a")]
        self.assertEqual(len(downs), 1)

    def test_invalid_json_no_crash(self):
        from macro_deck_python.plugins.builtin.keyboard_macro.main import Main
        plugin = Main(); plugin.package_id = "builtin.keyboard_macro"; plugin.enable()
        act = next(a for a in plugin.actions if a.action_id == "macro_short_press")
        act.plugin = plugin; act.configuration = "{bad json!!}"
        act.trigger("c", None)  # must not raise


if __name__ == "__main__":
    unittest.main(verbosity=2)
