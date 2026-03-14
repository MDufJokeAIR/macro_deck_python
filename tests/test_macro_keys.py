"""
test_macro_keys.py — comprehensive tests for the MacroKeys plugin

Tests:
  1.  Key map completeness — all key groups present and populated
  2.  Key map lookups — BY_LABEL, BY_GROUP, GROUPS
  3.  All key labels are unique
  4.  F1–F24 all present with correct pyautogui names
  5.  Modifier keys (left/right shift, ctrl, alt, win)
  6.  Navigation keys (arrows, home, end, page up/down, insert, delete)
  7.  Numpad keys (0–9, operators, enter)
  8.  Media keys (play/pause, stop, next, prev, mute, volume)
  9.  Browser keys (back, forward, refresh, etc.)
  10. OEM / Punctuation keys
  11. KeyDef is immutable (frozen dataclass)
  12. _execute_config — combo mode (mocked injector)
  13. _execute_config — sequence mode (mocked injector)
  14. _execute_config — long press (mocked injector)
  15. _execute_config — double press (mocked injector)
  16. _execute_config — max 5 keys enforced
  17. _execute_config — unknown key label is skipped gracefully
  18. _execute_config — empty keys list is handled gracefully
  19. MacroKeysAction — trigger parses JSON and calls _execute_config
  20. MacroKeysAction — trigger handles invalid JSON gracefully
  21. MacroKeysAction — trigger with empty configuration
  22. KeySequenceAction — types each char individually
  23. Plugin loads via PluginManager
  24. Plugin exposes correct actions (macro_keys + key_sequence_text)
  25. config_schema is valid JSON-Schema-like dict
  26. Backend detection does not crash (even without pynput/pyautogui)
  27. press_combination call order: down all, hold, up reversed
  28. Long-press hold duration is respected (timing)
  29. Double-press calls press_key twice
  30. REST endpoint — /api/macrokeys/groups returns all groups
  31. REST endpoint — /api/macrokeys/keys returns grouped key catalogue
  32. REST endpoint — /api/macrokeys/keys/{group} returns keys for group
  33. REST endpoint — /api/macrokeys/schema returns MacroKeysAction.config_schema
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import time
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))


# ─── helpers ─────────────────────────────────────────────────────────

PLUGIN_DIR = pathlib.Path(__file__).parent.parent / "plugins" / "builtin" / "macro_keys_plugin"

def _reset():
    from macro_deck_python.plugins.plugin_manager import PluginManager
    from macro_deck_python.services.variable_manager import VariableManager
    PluginManager._plugins.clear()
    PluginManager._actions.clear()
    VariableManager._variables.clear()
    VariableManager._on_change_callbacks.clear()


# ═══════════════════════════════════════════════════════════════════════
# 1–11  KEY MAP
# ═══════════════════════════════════════════════════════════════════════

class TestKeyMap(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import (
            ALL_KEYS, BY_LABEL, BY_GROUP, GROUPS
        )
        self.ALL = ALL_KEYS
        self.BY_LABEL = BY_LABEL
        self.BY_GROUP = BY_GROUP
        self.GROUPS = GROUPS

    def test_all_groups_present(self):
        expected = {
            "Letters", "Digits", "Function", "Numpad", "Navigation",
            "Modifiers", "Special", "Media", "Browser",
            "OEM / Punctuation", "App Launch",
        }
        for g in expected:
            self.assertIn(g, self.BY_GROUP, f"Group missing: {g}")

    def test_all_keys_have_labels(self):
        for kd in self.ALL:
            self.assertTrue(kd.label, f"KeyDef with empty label: {kd}")

    def test_all_labels_unique(self):
        labels = [kd.label for kd in self.ALL]
        dupes = [l for l in labels if labels.count(l) > 1]
        self.assertEqual(dupes, [], f"Duplicate labels: {set(dupes)}")

    def test_total_key_count_reasonable(self):
        # There should be well over 100 keys total
        self.assertGreater(len(self.ALL), 100)

    def test_by_label_lookup(self):
        kd = self.BY_LABEL.get("F1")
        self.assertIsNotNone(kd)
        self.assertEqual(kd.label, "F1")
        self.assertEqual(kd.group, "Function")

    def test_f1_to_f24_all_present(self):
        for n in range(1, 25):
            label = f"F{n}"
            kd = self.BY_LABEL.get(label)
            self.assertIsNotNone(kd, f"{label} missing from key map")
            self.assertEqual(kd.pyautogui, f"f{n}")
            self.assertEqual(kd.group, "Function")

    def test_modifier_keys_all_present(self):
        for label in ["Left Shift", "Right Shift", "Left Ctrl", "Right Ctrl",
                      "Left Alt", "Right Alt", "Left Win/⌘", "Right Win/⌘",
                      "Caps Lock", "Num Lock", "Scroll Lock", "Menu"]:
            self.assertIn(label, self.BY_LABEL, f"Modifier missing: {label}")

    def test_navigation_keys_all_present(self):
        for label in ["Up", "Down", "Left", "Right", "Home", "End",
                      "Page Up", "Page Down", "Insert", "Delete"]:
            self.assertIn(label, self.BY_LABEL, f"Nav key missing: {label}")

    def test_numpad_all_present(self):
        for n in range(10):
            self.assertIn(f"Numpad {n}", self.BY_LABEL, f"Numpad {n} missing")
        for sym in ["Numpad *", "Numpad +", "Numpad -", "Numpad .", "Numpad /", "Numpad Enter"]:
            self.assertIn(sym, self.BY_LABEL, f"{sym} missing")

    def test_media_keys_all_present(self):
        for label in ["Play/Pause", "Stop", "Next Track", "Prev Track",
                      "Mute", "Volume Up", "Volume Down"]:
            self.assertIn(label, self.BY_LABEL, f"Media key missing: {label}")

    def test_browser_keys_all_present(self):
        for label in ["Browser Back", "Browser Forward", "Browser Refresh",
                      "Browser Stop", "Browser Search", "Browser Favorites",
                      "Browser Home"]:
            self.assertIn(label, self.BY_LABEL, f"Browser key missing: {label}")

    def test_oem_punctuation_present(self):
        for label in [";", "=", ",", "-", ".", "/", "`", "[", "\\", "]", "'"]:
            self.assertIn(label, self.BY_LABEL, f"OEM key missing: {label}")
        self.assertIn("OEM_8",  self.BY_LABEL)
        self.assertIn("OEM_102",self.BY_LABEL)

    def test_special_keys_present(self):
        for label in ["Space", "Tab", "Enter", "Escape", "Backspace",
                      "Print Screen", "Pause/Break"]:
            self.assertIn(label, self.BY_LABEL, f"Special key missing: {label}")

    def test_letters_a_to_z(self):
        for c in "abcdefghijklmnopqrstuvwxyz":
            self.assertIn(c, self.BY_LABEL, f"Letter missing: {c}")

    def test_digits_0_to_9(self):
        for d in range(10):
            self.assertIn(str(d), self.BY_LABEL, f"Digit missing: {d}")

    def test_keydef_is_frozen(self):
        kd = self.BY_LABEL["F1"]
        with self.assertRaises((TypeError, AttributeError)):
            kd.label = "Modified"  # type: ignore

    def test_all_keys_have_pyautogui_name(self):
        for kd in self.ALL:
            self.assertIsNotNone(kd.pyautogui,
                                 f"{kd.label} has no pyautogui name")

    def test_all_function_keys_have_win_vk(self):
        for n in range(1, 25):
            kd = self.BY_LABEL[f"F{n}"]
            self.assertIsNotNone(kd.win_vk, f"F{n} has no win_vk")

    def test_groups_list_matches_by_group_keys(self):
        self.assertEqual(set(self.GROUPS), set(self.BY_GROUP.keys()))


# ═══════════════════════════════════════════════════════════════════════
# 12–18  _execute_config (mocked injector)
# ═══════════════════════════════════════════════════════════════════════

class TestExecuteConfig(unittest.TestCase):
    """All injector calls are mocked — no real key presses happen."""

    def _cfg(self, keys, mode="combo", **kw):
        return {"keys": keys, "mode": mode, **kw}

    def _entry(self, label, press_type="short", **kw):
        return {"key": label, "press_type": press_type, **kw}

    def test_combo_calls_press_combination(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import BY_LABEL
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc:
            m._execute_config(self._cfg([
                self._entry("Left Ctrl"),
                self._entry("c"),
            ], mode="combo"))
        mock_pc.assert_called_once()
        args = mock_pc.call_args[0]
        key_labels = [kd.label for kd in args[0]]
        self.assertIn("Left Ctrl", key_labels)
        self.assertIn("c", key_labels)

    def test_sequence_calls_press_key_for_each(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_key") as mock_pk, \
             patch("time.sleep"):
            m._execute_config(self._cfg([
                self._entry("a"),
                self._entry("b"),
                self._entry("c"),
            ], mode="sequence"))
        self.assertEqual(mock_pk.call_count, 3)

    def test_sequence_delays_between_keys(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        sleep_calls = []
        with patch.object(m, "press_key"), \
             patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
            m._execute_config(self._cfg([
                self._entry("a"), self._entry("b"),
            ], mode="sequence", sequence_delay_ms=99))
        # One sleep between the two keys
        self.assertIn(0.099, sleep_calls)

    def test_long_press_calls_key_down_and_up(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "key_down") as mock_kd, \
             patch.object(m, "key_up") as mock_ku, \
             patch("time.sleep"):
            m._execute_config(self._cfg([
                self._entry("Left Ctrl"),
                self._entry("F5", press_type="long", long_ms=600),
            ], mode="combo"))
        # key_down called for each key in combo, key_up for reverse
        self.assertEqual(mock_kd.call_count, 2)
        self.assertEqual(mock_ku.call_count, 2)

    def test_double_press_calls_press_combination_twice(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc, \
             patch("time.sleep"):
            m._execute_config(self._cfg([
                self._entry("Left Ctrl"),
                self._entry("z", press_type="double", double_interval_ms=80),
            ], mode="combo"))
        self.assertEqual(mock_pc.call_count, 2)

    def test_sequence_long_press(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "key_down") as mock_kd, \
             patch.object(m, "key_up") as mock_ku, \
             patch("time.sleep"):
            m._execute_config(self._cfg([
                self._entry("F1", press_type="long", long_ms=300),
            ], mode="sequence"))
        mock_kd.assert_called_once()
        mock_ku.assert_called_once()
        self.assertEqual(mock_kd.call_args[0][0].label, "F1")

    def test_sequence_double_press(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_key") as mock_pk, \
             patch("time.sleep"):
            m._execute_config(self._cfg([
                self._entry("Space", press_type="double"),
            ], mode="sequence"))
        self.assertEqual(mock_pk.call_count, 2)

    def test_max_5_keys_enforced(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc:
            m._execute_config(self._cfg([
                self._entry("a"), self._entry("b"), self._entry("c"),
                self._entry("d"), self._entry("e"), self._entry("f"),  # 6th ignored
            ], mode="combo"))
        key_labels = [kd.label for kd in mock_pc.call_args[0][0]]
        self.assertLessEqual(len(key_labels), 5)
        self.assertNotIn("f", key_labels)

    def test_unknown_key_label_skipped(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc:
            m._execute_config(self._cfg([
                self._entry("THIS_KEY_DOES_NOT_EXIST"),
                self._entry("a"),
            ], mode="combo"))
        # Only "a" should be in the call
        if mock_pc.called:
            key_labels = [kd.label for kd in mock_pc.call_args[0][0]]
            self.assertNotIn("THIS_KEY_DOES_NOT_EXIST", key_labels)

    def test_empty_keys_list_no_crash(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination"), \
             patch.object(m, "press_key"):
            m._execute_config({"keys": [], "mode": "combo"})  # must not raise

    def test_single_key_combo(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc:
            m._execute_config(self._cfg([self._entry("F5")], mode="combo"))
        mock_pc.assert_called_once()
        self.assertEqual(mock_pc.call_args[0][0][0].label, "F5")

    def test_defaults_applied(self):
        """Entry with no press_type defaults to 'short'."""
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc:
            m._execute_config({"keys": [{"key": "Enter"}], "mode": "combo"})
        mock_pc.assert_called_once()

    def test_f24_in_combo(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        with patch.object(m, "press_combination") as mock_pc:
            m._execute_config(self._cfg([self._entry("F24")], mode="combo"))
        self.assertEqual(mock_pc.call_args[0][0][0].label, "F24")


# ═══════════════════════════════════════════════════════════════════════
# 19–22  ACTION CLASSES
# ═══════════════════════════════════════════════════════════════════════

class TestMacroKeysAction(unittest.TestCase):
    def _make_action(self, cfg_dict=None):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        a = MacroKeysAction()
        a.configuration = json.dumps(cfg_dict) if cfg_dict else ""
        return a

    def test_trigger_calls_execute_config(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        a = self._make_action({"keys": [{"key": "F5"}], "mode": "combo"})
        with patch.object(m, "_execute_config") as mock_exec:
            a.trigger("c", None)
        mock_exec.assert_called_once()
        self.assertEqual(mock_exec.call_args[0][0]["keys"][0]["key"], "F5")

    def test_trigger_invalid_json_no_crash(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        a = MacroKeysAction()
        a.configuration = "{not valid json!!}"
        a.trigger("c", None)   # must not raise

    def test_trigger_empty_configuration(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        a = self._make_action()
        with patch.object(m, "_execute_config") as mock_exec:
            a.trigger("c", None)
        mock_exec.assert_called_once_with({})

    def test_action_id_and_name(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        a = MacroKeysAction()
        self.assertEqual(a.action_id, "macro_keys")
        self.assertTrue(a.name)
        self.assertTrue(a.can_configure)

    def test_config_schema_has_keys_property(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        schema = MacroKeysAction.config_schema
        self.assertIn("keys", schema["properties"])
        self.assertEqual(schema["properties"]["keys"]["maxItems"], 5)
        self.assertEqual(schema["properties"]["keys"]["minItems"], 1)

    def test_config_schema_press_type_enum(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        items = MacroKeysAction.config_schema["properties"]["keys"]["items"]
        press_type = items["properties"]["press_type"]
        self.assertIn("short",  press_type["enum"])
        self.assertIn("long",   press_type["enum"])
        self.assertIn("double", press_type["enum"])

    def test_config_schema_mode_enum(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import MacroKeysAction
        mode = MacroKeysAction.config_schema["properties"]["mode"]
        self.assertIn("combo",    mode["enum"])
        self.assertIn("sequence", mode["enum"])


class TestKeySequenceAction(unittest.TestCase):
    def test_types_each_char(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        a = m.KeySequenceAction()
        a.configuration = json.dumps({"text": "abc", "delay_ms": 0})
        pressed = []
        orig_pk = m.press_key
        m.press_key = lambda kd: pressed.append(kd.label)
        try:
            with patch("time.sleep"):
                a.trigger("c", None)
        finally:
            m.press_key = orig_pk
        self.assertEqual(pressed, ["a", "b", "c"])

    def test_invalid_json_no_crash(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.main as m
        a = m.KeySequenceAction()
        a.configuration = "BAD JSON"
        a.trigger("c", None)   # must not raise

    def test_action_id(self):
        from macro_deck_python.plugins.builtin.macro_keys_plugin.main import KeySequenceAction
        self.assertEqual(KeySequenceAction.action_id, "key_sequence_text")


# ═══════════════════════════════════════════════════════════════════════
# 23–25  PLUGIN LOADING
# ═══════════════════════════════════════════════════════════════════════

class TestMacroKeysPluginLoad(unittest.TestCase):
    def setUp(self):
        _reset()
        from macro_deck_python.plugins.plugin_manager import PluginManager
        builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
        PluginManager.set_plugins_dir(builtin)
        PluginManager._load_plugin(PLUGIN_DIR)

    def test_plugin_registered(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        self.assertIn("builtin.macro_keys", PluginManager._plugins)

    def test_both_actions_registered(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        acts = PluginManager._actions["builtin.macro_keys"]
        self.assertIn("macro_keys",          acts)
        self.assertIn("key_sequence_text",   acts)

    def test_action_references_plugin(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        act = PluginManager._actions["builtin.macro_keys"]["macro_keys"]
        self.assertIsNotNone(act.plugin)
        self.assertEqual(act.plugin.package_id, "builtin.macro_keys")

    def test_plugin_has_key_catalogue_attrs(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        plugin = PluginManager._plugins["builtin.macro_keys"]
        self.assertTrue(hasattr(plugin, "all_keys"))
        self.assertTrue(hasattr(plugin, "by_label"))
        self.assertTrue(hasattr(plugin, "groups"))
        self.assertGreater(len(plugin.all_keys), 100)


# ═══════════════════════════════════════════════════════════════════════
# 26–29  INJECTOR UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════

class TestInjector(unittest.TestCase):
    def test_press_combination_order(self):
        """down all keys in order, then up in reverse."""
        import macro_deck_python.plugins.builtin.macro_keys_plugin.key_injector as inj
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import BY_LABEL
        order = []
        mock_down = MagicMock(side_effect=lambda k: order.append(("down", k.label)))
        mock_up   = MagicMock(side_effect=lambda k: order.append(("up",   k.label)))
        orig_dispatch = dict(inj._DISPATCH)
        inj._DISPATCH["mock"] = (MagicMock(), mock_down, mock_up)
        orig_backend = inj._BACKEND
        inj._BACKEND = "mock"
        try:
            keys = [BY_LABEL["Left Ctrl"], BY_LABEL["Left Shift"], BY_LABEL["Escape"]]
            with patch("time.sleep"):
                inj.press_combination(keys, hold_ms=0)
        finally:
            inj._DISPATCH = orig_dispatch
            inj._BACKEND  = orig_backend

        down_ops = [o for o in order if o[0] == "down"]
        up_ops   = [o for o in order if o[0] == "up"]
        self.assertEqual([o[1] for o in down_ops], ["Left Ctrl", "Left Shift", "Escape"])
        self.assertEqual([o[1] for o in up_ops],   ["Escape", "Left Shift", "Left Ctrl"])

    def test_backend_detection_no_crash(self):
        """Even without pynput/pyautogui installed, detection raises ImportError (not crash)."""
        import macro_deck_python.plugins.builtin.macro_keys_plugin.key_injector as inj
        # Reset cached backend
        orig = inj._BACKEND
        inj._BACKEND = None
        try:
            # May raise ImportError if no backend — that's fine
            inj._detect_backend()
        except ImportError:
            pass   # expected on this test environment
        finally:
            inj._BACKEND = orig

    def test_press_key_dispatches_to_backend(self):
        import macro_deck_python.plugins.builtin.macro_keys_plugin.key_injector as inj
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import BY_LABEL
        pressed = []
        mock_press = MagicMock(side_effect=lambda k: pressed.append(k.label))
        orig_dispatch = dict(inj._DISPATCH)
        orig_backend  = inj._BACKEND
        inj._DISPATCH["mock"] = (mock_press, MagicMock(), MagicMock())
        inj._BACKEND = "mock"
        try:
            inj.press_key(BY_LABEL["F1"])
        finally:
            inj._DISPATCH = orig_dispatch
            inj._BACKEND  = orig_backend
        self.assertEqual(pressed, ["F1"])


# ═══════════════════════════════════════════════════════════════════════
# 30–33  REST ENDPOINTS (in-process aiohttp)
# ═══════════════════════════════════════════════════════════════════════

class TestMacroKeysRESTEndpoints(unittest.TestCase):
    """
    Test the macrokeys catalogue REST endpoints without needing aiohttp at runtime.
    We bypass the web framework and test the handler logic directly by mocking
    the _json() helper to return a simple dict instead of a web.Response.
    """

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _make_request(self, match_info=None):
        req = MagicMock()
        req.match_info = match_info or {}
        return req

    def _with_json_mock(self):
        """Context manager: replace _json() so it returns its first arg as-is."""
        import macro_deck_python.gui.web_config as wc
        sentinel = {}
        captured = []
        original_json = wc._json

        def fake_json(data):
            captured.append(data)
            return data   # return plain dict, not web.Response

        return patch.object(wc, "_json", side_effect=fake_json), captured, original_json

    def test_groups_returns_all_groups(self):
        from macro_deck_python.gui.web_config import api_macrokeys_groups
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import GROUPS
        import macro_deck_python.gui.web_config as wc
        req = self._make_request()
        captured = []
        with patch.object(wc, "_json", side_effect=lambda d: captured.append(d) or d):
            self._run(api_macrokeys_groups(req))
        data = captured[0]
        self.assertIn("groups", data)
        self.assertEqual(set(data["groups"]), set(GROUPS))

    def test_all_keys_returns_all_groups(self):
        from macro_deck_python.gui.web_config import api_macrokeys_all_keys
        from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import GROUPS
        import macro_deck_python.gui.web_config as wc
        req = self._make_request()
        captured = []
        with patch.object(wc, "_json", side_effect=lambda d: captured.append(d) or d):
            self._run(api_macrokeys_all_keys(req))
        data = captured[0]
        for g in GROUPS:
            self.assertIn(g, data, f"Group {g} missing")
        for g, keys in data.items():
            self.assertIsInstance(keys, list)
            for entry in keys:
                self.assertIn("label", entry)

    def test_group_valid_returns_f1_to_f24(self):
        from macro_deck_python.gui.web_config import api_macrokeys_group
        import macro_deck_python.gui.web_config as wc
        req = self._make_request(match_info={"group": "Function"})
        captured = []
        with patch.object(wc, "_json", side_effect=lambda d: captured.append(d) or d):
            self._run(api_macrokeys_group(req))
        labels = [e["label"] for e in captured[0]]
        for n in range(1, 25):
            self.assertIn(f"F{n}", labels)

    def test_group_invalid_raises_http_not_found(self):
        from macro_deck_python.gui.web_config import api_macrokeys_group
        import macro_deck_python.gui.web_config as wc
        # aiohttp raises HTTPNotFound; if aiohttp missing, skip
        try:
            from aiohttp import web as _web
        except ImportError:
            self.skipTest("aiohttp not installed")
        req = self._make_request(match_info={"group": "DOES_NOT_EXIST"})
        with self.assertRaises(_web.HTTPNotFound):
            self._run(api_macrokeys_group(req))

    def test_schema_returns_config_schema(self):
        from macro_deck_python.gui.web_config import api_macrokeys_schema
        import macro_deck_python.gui.web_config as wc
        req = self._make_request()
        captured = []
        with patch.object(wc, "_json", side_effect=lambda d: captured.append(d) or d):
            self._run(api_macrokeys_schema(req))
        data = captured[0]
        self.assertIn("properties", data)
        self.assertIn("keys", data["properties"])
        self.assertEqual(data["properties"]["keys"]["maxItems"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
