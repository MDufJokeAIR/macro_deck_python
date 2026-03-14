"""
test_all.py — full unit test suite for macro_deck_python (unittest.TestCase format)
Run: python -m unittest discover -s macro_deck_python/tests -v
"""
from __future__ import annotations
import json, pathlib, sys, tempfile, threading, time, unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))


# ════════════════════════════════════════════════════════════════════
# MODELS
# ════════════════════════════════════════════════════════════════════

class TestVariable(unittest.TestCase):
    def _mk(self):
        from macro_deck_python.models.variable import Variable, VariableType
        return Variable, VariableType

    def test_cast_int(self):
        V, VT = self._mk()
        self.assertEqual(V("n", "42", VT.INTEGER).cast(), 42)

    def test_cast_float(self):
        V, VT = self._mk()
        self.assertAlmostEqual(V("f", "3.14", VT.FLOAT).cast(), 3.14)

    def test_cast_bool_truthy(self):
        V, VT = self._mk()
        for s in ("true", "True", "1", "yes"):
            self.assertTrue(V("b", s, VT.BOOL).cast(), s)

    def test_cast_bool_falsy(self):
        V, VT = self._mk()
        for s in ("false", "False", "0", "no"):
            self.assertFalse(V("b", s, VT.BOOL).cast(), s)

    def test_cast_string(self):
        V, VT = self._mk()
        self.assertEqual(V("s", 123, VT.STRING).cast(), "123")

    def test_cast_bad_value_returns_raw(self):
        V, VT = self._mk()
        v = V("n", "not_a_number", VT.INTEGER)
        self.assertEqual(v.cast(), "not_a_number")

    def test_roundtrip(self):
        V, VT = self._mk()
        v = V("cpu", 87.5, VT.FLOAT, "plugin.sys", save=True)
        v2 = V.from_dict(v.to_dict())
        self.assertEqual(v.name, v2.name)
        self.assertEqual(v.type, v2.type)
        self.assertEqual(v.plugin_id, v2.plugin_id)
        self.assertAlmostEqual(float(v2.value), 87.5)

    def test_all_types_roundtrip(self):
        V, VT = self._mk()
        for val, vt in [(1, VT.INTEGER), (1.5, VT.FLOAT), ("hi", VT.STRING), (True, VT.BOOL)]:
            v = V("x", val, vt)
            v2 = V.from_dict(v.to_dict())
            self.assertEqual(v2.type, vt)


class TestActionButton(unittest.TestCase):
    def test_empty_roundtrip(self):
        from macro_deck_python.models.action_button import ActionButton
        b = ActionButton()
        self.assertEqual(b.button_id, ActionButton.from_dict(b.to_dict()).button_id)

    def test_full_roundtrip(self):
        from macro_deck_python.models.action_button import ActionButton, ActionEntry, Condition
        b = ActionButton(label="{cpu:.1f}%", state_binding="is_live",
                         background_color="#ff0000", label_color="#00ff00",
                         label_font_size=16)
        b.actions.append(ActionEntry("p.a", "act1", '{"k":"v"}', "summary"))
        b.conditions.append(Condition("is_live", "==", "True",
            actions_true=[ActionEntry("p", "a")],
            actions_false=[ActionEntry("p", "b")]))
        b2 = ActionButton.from_dict(b.to_dict())
        self.assertEqual(b2.state_binding, "is_live")
        self.assertEqual(b2.background_color, "#ff0000")
        self.assertEqual(b2.label_font_size, 16)
        self.assertEqual(b2.actions[0].configuration, '{"k":"v"}')
        self.assertEqual(b2.actions[0].configuration_summary, "summary")
        self.assertEqual(len(b2.conditions[0].actions_true), 1)
        self.assertEqual(len(b2.conditions[0].actions_false), 1)

    def test_action_entry_roundtrip(self):
        from macro_deck_python.models.action_button import ActionEntry
        e = ActionEntry("myplugin", "myaction", '{"x":1}', "x=1")
        e2 = ActionEntry.from_dict(e.to_dict())
        self.assertEqual(e2.plugin_id, "myplugin")
        self.assertEqual(e2.action_id, "myaction")
        self.assertEqual(e2.configuration_summary, "x=1")

    def test_condition_both_branches_roundtrip(self):
        from macro_deck_python.models.action_button import ActionEntry, Condition
        c = Condition("vol", ">", "50",
                      actions_true=[ActionEntry("p", "loud")],
                      actions_false=[ActionEntry("p", "quiet")])
        c2 = Condition.from_dict(c.to_dict())
        self.assertEqual(c2.variable_name, "vol")
        self.assertEqual(c2.operator, ">")
        self.assertEqual(c2.compare_value, "50")
        self.assertEqual(c2.actions_true[0].action_id, "loud")
        self.assertEqual(c2.actions_false[0].action_id, "quiet")

    def test_multiple_actions_preserved(self):
        from macro_deck_python.models.action_button import ActionButton, ActionEntry
        b = ActionButton()
        for i in range(5):
            b.actions.append(ActionEntry(f"p{i}", f"a{i}"))
        b2 = ActionButton.from_dict(b.to_dict())
        self.assertEqual(len(b2.actions), 5)
        self.assertEqual(b2.actions[3].plugin_id, "p3")

    def test_multiple_conditions_preserved(self):
        from macro_deck_python.models.action_button import ActionButton, Condition
        b = ActionButton()
        for i in range(3):
            b.conditions.append(Condition(f"var{i}", "==", str(i)))
        b2 = ActionButton.from_dict(b.to_dict())
        self.assertEqual(len(b2.conditions), 3)


class TestProfileFolder(unittest.TestCase):
    def test_set_get_remove(self):
        from macro_deck_python.models.profile import Folder
        from macro_deck_python.models.action_button import ActionButton
        f = Folder()
        f.set_button(0, 0, ActionButton(label="Mute"))
        self.assertEqual(f.get_button(0, 0).label, "Mute")
        f.remove_button(0, 0)
        self.assertIsNone(f.get_button(0, 0))

    def test_multiple_buttons(self):
        from macro_deck_python.models.profile import Folder
        from macro_deck_python.models.action_button import ActionButton
        f = Folder(columns=8, rows=4)
        for r in range(4):
            for c in range(8):
                f.set_button(r, c, ActionButton(label=f"{r}_{c}"))
        self.assertEqual(len(f.buttons), 32)
        self.assertEqual(f.get_button(3, 7).label, "3_7")

    def test_nested_subfolder_roundtrip(self):
        from macro_deck_python.models.profile import Profile, Folder
        from macro_deck_python.models.action_button import ActionButton
        p = Profile(name="Work")
        sub = Folder(name="OBS")
        sub.set_button(1, 1, ActionButton(label="Scene 1"))
        p.folder.sub_folders.append(sub)
        p2 = Profile.from_dict(p.to_dict())
        self.assertEqual(p2.folder.sub_folders[0].name, "OBS")
        self.assertEqual(p2.folder.sub_folders[0].get_button(1, 1).label, "Scene 1")

    def test_deep_nesting_roundtrip(self):
        from macro_deck_python.models.profile import Profile, Folder
        from macro_deck_python.models.action_button import ActionButton
        p = Profile(name="Deep")
        level1 = Folder(name="L1")
        level2 = Folder(name="L2")
        level3 = Folder(name="L3")
        level3.set_button(0, 0, ActionButton(label="DeepBtn"))
        level2.sub_folders.append(level3)
        level1.sub_folders.append(level2)
        p.folder.sub_folders.append(level1)
        p2 = Profile.from_dict(p.to_dict())
        l3 = p2.folder.sub_folders[0].sub_folders[0].sub_folders[0]
        self.assertEqual(l3.name, "L3")
        self.assertEqual(l3.get_button(0, 0).label, "DeepBtn")

    def test_profile_id_preserved(self):
        from macro_deck_python.models.profile import Profile
        p = Profile(name="PID Test")
        p2 = Profile.from_dict(p.to_dict())
        self.assertEqual(p.profile_id, p2.profile_id)


# ════════════════════════════════════════════════════════════════════
# UTILS
# ════════════════════════════════════════════════════════════════════

class TestTemplate(unittest.TestCase):
    def _r(self, tpl, store):
        from macro_deck_python.utils.template import render_label
        return render_label(tpl, store.get if isinstance(store, dict) else store)

    def test_simple_substitution(self):
        self.assertEqual(self._r("Hi {name}", {"name": "World"}), "Hi World")

    def test_format_spec_float(self):
        self.assertEqual(self._r("{t:.2f}°", {"t": 36.666}), "36.67°")

    def test_format_spec_int_padding(self):
        self.assertEqual(self._r("{n:04d}", {"n": 7}), "0007")

    def test_unknown_variable_preserved(self):
        self.assertEqual(self._r("{unknown_var}", {}), "{unknown_var}")

    def test_static_no_vars(self):
        self.assertEqual(self._r("Static Label", {}), "Static Label")

    def test_multiple_vars(self):
        self.assertEqual(self._r("{a}+{b}={c}", {"a": 1, "b": 2, "c": 3}), "1+2=3")

    def test_mixed_known_unknown(self):
        result = self._r("{known} and {unknown}", {"known": "yes"})
        self.assertEqual(result, "yes and {unknown}")

    def test_empty_template(self):
        self.assertEqual(self._r("", {}), "")

    def test_integer_type(self):
        self.assertEqual(self._r("Count: {n}", {"n": 42}), "Count: 42")

    def test_bool_type(self):
        self.assertEqual(self._r("Live: {live}", {"live": True}), "Live: True")


class TestCondition(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        VariableManager._variables.clear()
        VariableManager._on_change_callbacks.clear()
        for name, val, vt in [
            ("vol", 80, VariableType.INTEGER),
            ("muted", True, VariableType.BOOL),
            ("tag", "Alice", VariableType.STRING),
            ("ratio", 0.75, VariableType.FLOAT),
        ]:
            VariableManager.set_value(name, val, vt, save=False)

    def _e(self, n, op, v):
        from macro_deck_python.utils.condition import evaluate_condition
        return evaluate_condition(n, op, v)

    def test_gt_true(self):      self.assertTrue(self._e("vol", ">", "50"))
    def test_gt_false(self):     self.assertFalse(self._e("vol", ">", "100"))
    def test_lt_true(self):      self.assertTrue(self._e("vol", "<", "100"))
    def test_lt_false(self):     self.assertFalse(self._e("vol", "<", "50"))
    def test_eq_true(self):      self.assertTrue(self._e("vol", "==", "80"))
    def test_eq_false(self):     self.assertFalse(self._e("vol", "==", "99"))
    def test_neq_true(self):     self.assertTrue(self._e("vol", "!=", "99"))
    def test_neq_false(self):    self.assertFalse(self._e("vol", "!=", "80"))
    def test_gte_eq(self):       self.assertTrue(self._e("vol", ">=", "80"))
    def test_gte_gt(self):       self.assertTrue(self._e("vol", ">=", "79"))
    def test_gte_false(self):    self.assertFalse(self._e("vol", ">=", "81"))
    def test_lte_eq(self):       self.assertTrue(self._e("vol", "<=", "80"))
    def test_lte_lt(self):       self.assertTrue(self._e("vol", "<=", "81"))
    def test_lte_false(self):    self.assertFalse(self._e("vol", "<=", "79"))
    def test_bool_true(self):    self.assertTrue(self._e("muted", "==", "True"))
    def test_bool_false(self):   self.assertFalse(self._e("muted", "==", "False"))
    def test_string_eq(self):    self.assertTrue(self._e("tag", "==", "Alice"))
    def test_string_neq(self):   self.assertTrue(self._e("tag", "!=", "Bob"))
    def test_float_lt(self):     self.assertTrue(self._e("ratio", "<", "1.0"))
    def test_float_gt(self):     self.assertTrue(self._e("ratio", ">", "0.0"))
    def test_missing_var(self):  self.assertFalse(self._e("nope", "==", "x"))


class TestFolderUtils(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.models.profile import Folder
        from macro_deck_python.models.action_button import ActionButton
        self.root = Folder(name="Root")
        self.s1 = Folder(name="OBS")
        self.s2 = Folder(name="Audio")
        self.s3 = Folder(name="Mic")
        self.root.sub_folders += [self.s1, self.s2]
        self.s2.sub_folders.append(self.s3)
        self.s3.set_button(0, 0, ActionButton(label="Mute"))

    def _f(self, fid):
        from macro_deck_python.utils.folder_utils import find_folder
        return find_folder(self.root, fid)

    def test_direct_child(self):  self.assertIs(self._f(self.s1.folder_id), self.s1)
    def test_second_child(self):  self.assertIs(self._f(self.s2.folder_id), self.s2)
    def test_deep_nested(self):   self.assertIs(self._f(self.s3.folder_id), self.s3)
    def test_root_itself(self):   self.assertIs(self._f(self.root.folder_id), self.root)
    def test_none_id(self):       self.assertIsNone(self._f(None))
    def test_missing_id(self):    self.assertIsNone(self._f("bad-id-xyz"))

    def test_button_reachable_via_found_folder(self):
        folder = self._f(self.s3.folder_id)
        self.assertEqual(folder.get_button(0, 0).label, "Mute")


# ════════════════════════════════════════════════════════════════════
# SERVICES
# ════════════════════════════════════════════════════════════════════

class TestVariableManager(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        self.VM = VariableManager
        self.VT = VariableType
        self.VM._variables.clear()
        self.VM._on_change_callbacks.clear()

    def test_set_and_get(self):
        self.VM.set_value("x", 42, self.VT.INTEGER, save=False)
        self.assertEqual(self.VM.get_value("x"), 42)

    def test_overwrite_value(self):
        self.VM.set_value("x", 1, self.VT.INTEGER, save=False)
        self.VM.set_value("x", 2, self.VT.INTEGER, save=False)
        self.assertEqual(self.VM.get_value("x"), 2)

    def test_missing_returns_none(self):
        self.assertIsNone(self.VM.get_value("__no_such_var__"))

    def test_get_variable_object(self):
        self.VM.set_value("obj_test", "hi", self.VT.STRING, save=False)
        v = self.VM.get_variable("obj_test")
        self.assertIsNotNone(v)
        self.assertEqual(v.name, "obj_test")

    def test_callback_fired_on_change(self):
        seen = []
        self.VM.on_change(lambda v: seen.append(v.name))
        self.VM.set_value("cb_var", "hello", self.VT.STRING, save=False)
        self.assertIn("cb_var", seen)

    def test_multiple_callbacks_all_fire(self):
        calls = []
        self.VM.on_change(lambda v: calls.append("A"))
        self.VM.on_change(lambda v: calls.append("B"))
        self.VM.on_change(lambda v: calls.append("C"))
        self.VM.set_value("multi", 1, self.VT.INTEGER, save=False)
        self.assertEqual(sorted(calls), ["A", "B", "C"])

    def test_delete_removes_variable(self):
        self.VM.set_value("del_me", "bye", self.VT.STRING, save=False)
        self.VM.delete("del_me")
        self.assertIsNone(self.VM.get_value("del_me"))

    def test_delete_nonexistent_no_error(self):
        self.VM.delete("does_not_exist_at_all")  # should not raise

    def test_get_all_returns_all(self):
        self.VM.set_value("a", 1, self.VT.INTEGER, save=False)
        self.VM.set_value("b", 2, self.VT.INTEGER, save=False)
        names = [v.name for v in self.VM.get_all()]
        self.assertIn("a", names)
        self.assertIn("b", names)

    def test_save_load_persists_saved_vars(self):
        self.VM.set_value("p1", 99, self.VT.INTEGER, save=True)
        self.VM.set_value("p2", "hello", self.VT.STRING, save=True)
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.VM.save(tmp)
        self.VM._variables.clear()
        self.VM.load(tmp)
        self.assertEqual(self.VM.get_value("p1"), 99)
        self.assertEqual(self.VM.get_value("p2"), "hello")
        tmp.unlink()

    def test_ephemeral_vars_not_saved(self):
        self.VM.set_value("eph", "gone", self.VT.STRING, save=False)
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.VM.save(tmp)
        self.VM._variables.clear()
        self.VM.load(tmp)
        self.assertIsNone(self.VM.get_value("eph"))
        tmp.unlink()

    def test_save_empty_store(self):
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.VM.save(tmp)
        data = json.loads(tmp.read_text())
        self.assertEqual(data, [])
        tmp.unlink()

    def test_load_missing_file_no_error(self):
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.VM.load(tmp)   # file doesn't exist — should not raise
        self.assertEqual(self.VM.get_all(), [])

    def test_thread_safety_concurrent_writes(self):
        errors = []
        def writer(n):
            try:
                for i in range(100):
                    self.VM.set_value(f"t{n}_{i}", i, self.VT.INTEGER, save=False)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=writer, args=(n,)) for n in range(6)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors, [], f"Thread errors: {errors}")

    def test_callback_error_does_not_stop_others(self):
        results = []
        self.VM.on_change(lambda v: (_ for _ in ()).throw(RuntimeError("bad cb")))  # raises
        self.VM.on_change(lambda v: results.append("ok"))
        self.VM.set_value("err_test", 1, self.VT.INTEGER, save=False)
        self.assertIn("ok", results)


class TestProfileManager(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.services.profile_manager import ProfileManager
        self.PM = ProfileManager
        self.PM._profiles.clear()
        self.PM._active_profile = None
        self.PM._client_profiles.clear()

    def test_create_and_retrieve(self):
        p = self.PM.create_profile("MyProfile")
        self.assertEqual(self.PM.get_profile(p.profile_id).name, "MyProfile")

    def test_get_all(self):
        p1 = self.PM.create_profile("P1")
        p2 = self.PM.create_profile("P2")
        ids = [p.profile_id for p in self.PM.get_all()]
        self.assertIn(p1.profile_id, ids)
        self.assertIn(p2.profile_id, ids)

    def test_set_active(self):
        p = self.PM.create_profile("Active")
        self.PM.set_active(p.profile_id)
        self.assertIs(self.PM.get_active(), p)

    def test_set_active_invalid_returns_false(self):
        self.assertFalse(self.PM.set_active("nonexistent-id"))

    def test_delete_profile(self):
        p = self.PM.create_profile("Del")
        self.assertTrue(self.PM.delete_profile(p.profile_id))
        self.assertIsNone(self.PM.get_profile(p.profile_id))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.PM.delete_profile("bad-id"))

    def test_delete_active_reassigns_to_remaining(self):
        p1 = self.PM.create_profile("P1")
        p2 = self.PM.create_profile("P2")
        self.PM.set_active(p1.profile_id)
        self.PM.delete_profile(p1.profile_id)
        self.assertIsNotNone(self.PM.get_active())
        self.assertNotEqual(self.PM.get_active().profile_id, p1.profile_id)

    def test_client_profile_override(self):
        p1 = self.PM.create_profile("Default")
        p2 = self.PM.create_profile("Gaming")
        self.PM.set_active(p1.profile_id)
        self.PM.set_client_profile("client-g", p2.profile_id)
        self.assertIs(self.PM.get_client_profile("client-g"), p2)

    def test_unknown_client_falls_back_to_active(self):
        p = self.PM.create_profile("Active")
        self.PM.set_active(p.profile_id)
        self.assertIs(self.PM.get_client_profile("unknown-xyz"), p)

    def test_save_load_roundtrip(self):
        from macro_deck_python.models.action_button import ActionButton
        p = self.PM.create_profile("Saved")
        p.folder.set_button(0, 0, ActionButton(label="Btn"))
        self.PM.set_active(p.profile_id)
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.PM.save(tmp)
        self.PM._profiles.clear(); self.PM._active_profile = None
        self.PM.load(tmp)
        loaded = self.PM.get_profile(p.profile_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.folder.get_button(0, 0).label, "Btn")
        self.assertEqual(self.PM.get_active().profile_id, p.profile_id)
        tmp.unlink()

    def test_load_missing_file_creates_default(self):
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.PM.load(tmp)
        self.assertIsNotNone(self.PM.get_active())
        self.assertEqual(self.PM.get_active().name, "Default")
        tmp.unlink(missing_ok=True)

    def test_multiple_profiles_saved_and_loaded(self):
        for name in ["Alpha", "Beta", "Gamma", "Delta"]:
            self.PM.create_profile(name)
        tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.PM.save(tmp)
        self.PM._profiles.clear(); self.PM._active_profile = None
        self.PM.load(tmp)
        names = [p.name for p in self.PM.get_all()]
        for name in ["Alpha", "Beta", "Gamma", "Delta"]:
            self.assertIn(name, names)
        tmp.unlink()


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.core.config_manager import ConfigManager
        self.CM = ConfigManager
        self.CM._cfg.clear()
        self._tmp = pathlib.Path(tempfile.mktemp(suffix=".json"))
        self.CM._active_path = self._tmp

    def tearDown(self):
        self._tmp.unlink(missing_ok=True)

    def test_defaults_for_missing_file(self):
        self.CM.load(self._tmp)
        self.assertEqual(self.CM.get("port"), 8191)
        self.assertEqual(self.CM.get("host"), "0.0.0.0")
        self.assertEqual(self.CM.get("deck_rows"), 3)
        self.assertEqual(self.CM.get("deck_cols"), 5)

    def test_set_persists_to_active_path(self):
        self.CM.load(self._tmp)
        self.CM.set("port", 9876)
        self.CM._cfg.clear()
        self.CM.load()
        self.assertEqual(self.CM.get("port"), 9876)

    def test_custom_key(self):
        self.CM.load(self._tmp)
        self.CM.set("my_custom_key", "hello_world")
        self.assertEqual(self.CM.get("my_custom_key"), "hello_world")

    def test_missing_key_returns_default(self):
        self.CM.load(self._tmp)
        self.assertEqual(self.CM.get("no_such_key", "fallback"), "fallback")

    def test_missing_key_returns_none_by_default(self):
        self.CM.load(self._tmp)
        self.assertIsNone(self.CM.get("absolutely_not_a_key"))

    def test_as_dict_contains_all_defaults(self):
        self.CM.load(self._tmp)
        d = self.CM.as_dict()
        for key in ("port", "host", "theme", "log_level", "deck_rows", "deck_cols"):
            self.assertIn(key, d)

    def test_overwrite_then_reload(self):
        self.CM.load(self._tmp)
        self.CM.set("theme", "light")
        self.CM.set("port", 1234)
        self.CM._cfg.clear()
        self.CM.load()
        self.assertEqual(self.CM.get("theme"), "light")
        self.assertEqual(self.CM.get("port"), 1234)


# ════════════════════════════════════════════════════════════════════
# PLUGINS
# ════════════════════════════════════════════════════════════════════

class TestPluginManager(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        self.PM = PluginManager
        self.PM._plugins.clear()
        self.PM._actions.clear()
        builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
        self.PM.set_plugins_dir(builtin)
        self.PM.load_all_plugins()

    def test_keyboard_plugin_loaded(self):
        ids = [p.package_id for p in self.PM.all_plugins()]
        self.assertIn("builtin.keyboard", ids)

    def test_system_variables_plugin_loaded(self):
        ids = [p.package_id for p in self.PM.all_plugins()]
        self.assertIn("builtin.system_variables", ids)

    def test_commands_plugin_loaded(self):
        ids = [p.package_id for p in self.PM.all_plugins()]
        self.assertIn("builtin.commands", ids)

    def test_hotkey_action_exists(self):
        act = self.PM.get_action("builtin.keyboard", "hotkey")
        self.assertIsNotNone(act)
        self.assertEqual(act.name, "Press Hotkey")

    def test_type_text_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.keyboard", "type_text"))

    def test_key_press_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.keyboard", "key_press"))

    def test_run_command_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.commands", "run_command"))

    def test_toggle_variable_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.commands", "toggle_variable"))

    def test_set_variable_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.commands", "set_variable"))

    def test_delay_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.commands", "delay"))

    def test_open_url_action_exists(self):
        self.assertIsNotNone(self.PM.get_action("builtin.commands", "open_url"))

    def test_missing_plugin_returns_none(self):
        self.assertIsNone(self.PM.get_plugin("no.such.plugin"))

    def test_missing_action_returns_none(self):
        self.assertIsNone(self.PM.get_action("no.plugin", "no.action"))

    def test_action_has_plugin_reference(self):
        act = self.PM.get_action("builtin.keyboard", "hotkey")
        self.assertIsNotNone(act.plugin)
        self.assertEqual(act.plugin.package_id, "builtin.keyboard")

    def test_all_actions_returns_list(self):
        actions = self.PM.all_actions()
        self.assertIsInstance(actions, list)
        self.assertGreater(len(actions), 0)


class TestPluginConfiguration(unittest.TestCase):
    def _plugin(self, pid="test.cfg"):
        from macro_deck_python.plugins.base import IMacroDeckPlugin
        class FP(IMacroDeckPlugin):
            name = version = author = description = ""
            def enable(self): pass
        p = FP(); p.package_id = pid
        return p

    def test_set_and_get(self):
        from macro_deck_python.plugins.base import PluginConfiguration
        p = self._plugin("cfg.a")
        PluginConfiguration.set_value(p, "key", "value")
        self.assertEqual(PluginConfiguration.get_value(p, "key"), "value")

    def test_missing_key_returns_default(self):
        from macro_deck_python.plugins.base import PluginConfiguration
        p = self._plugin("cfg.b")
        self.assertEqual(PluginConfiguration.get_value(p, "missing", "def"), "def")

    def test_missing_key_returns_empty_string(self):
        from macro_deck_python.plugins.base import PluginConfiguration
        p = self._plugin("cfg.c")
        self.assertEqual(PluginConfiguration.get_value(p, "missing"), "")

    def test_overwrite(self):
        from macro_deck_python.plugins.base import PluginConfiguration
        p = self._plugin("cfg.d")
        PluginConfiguration.set_value(p, "k", "v1")
        PluginConfiguration.set_value(p, "k", "v2")
        self.assertEqual(PluginConfiguration.get_value(p, "k"), "v2")

    def test_isolated_per_plugin(self):
        from macro_deck_python.plugins.base import PluginConfiguration
        p1 = self._plugin("cfg.iso1")
        p2 = self._plugin("cfg.iso2")
        PluginConfiguration.set_value(p1, "key", "for_p1")
        PluginConfiguration.set_value(p2, "key", "for_p2")
        self.assertEqual(PluginConfiguration.get_value(p1, "key"), "for_p1")
        self.assertEqual(PluginConfiguration.get_value(p2, "key"), "for_p2")


class TestActionExecutor(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.plugins.base import IMacroDeckPlugin, PluginAction
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.models.variable import VariableType
        PluginManager._plugins.clear()
        PluginManager._actions.clear()
        VariableManager._variables.clear()
        VariableManager._on_change_callbacks.clear()
        VariableManager.set_value("flag", True, VariableType.BOOL, save=False)
        VariableManager.set_value("count", 5, VariableType.INTEGER, save=False)
        self.log = []
        outer = self

        class MA(PluginAction):
            action_id = "mock"; name = "Mock"; description = ""
            def trigger(self_, cid, btn):
                outer.log.append(json.loads(self_.configuration) if self_.configuration else {})

        class MP(IMacroDeckPlugin):
            name = version = author = description = ""
            def enable(self_): self_.actions = [MA()]

        plug = MP(); plug.package_id = "x.exec"; plug.enable()
        PluginManager._plugins["x.exec"] = plug
        PluginManager._actions["x.exec"] = {"mock": plug.actions[0]}
        plug.actions[0].plugin = plug

    def _btn(self, conditions=None):
        from macro_deck_python.models.action_button import ActionButton, ActionEntry, Condition
        b = ActionButton()
        b.actions.append(ActionEntry("x.exec", "mock", json.dumps({"src": "base"})))
        for cond in (conditions or []):
            b.conditions.append(cond)
        return b

    def test_base_action_fires(self):
        from macro_deck_python.services.action_executor import execute_button
        execute_button(self._btn(), "c1")
        time.sleep(0.15)
        self.assertIn("base", [t["src"] for t in self.log])

    def test_condition_true_branch_fires(self):
        from macro_deck_python.models.action_button import ActionEntry, Condition
        from macro_deck_python.services.action_executor import execute_button
        cond = Condition("flag", "==", "True",
                         actions_true=[ActionEntry("x.exec", "mock", json.dumps({"src": "T"}))],
                         actions_false=[ActionEntry("x.exec", "mock", json.dumps({"src": "F"}))])
        execute_button(self._btn([cond]), "c1")
        time.sleep(0.15)
        srcs = [t["src"] for t in self.log]
        self.assertIn("T", srcs)
        self.assertNotIn("F", srcs)

    def test_condition_false_branch_fires(self):
        from macro_deck_python.models.action_button import ActionEntry, Condition
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.services.action_executor import execute_button
        VariableManager.set_value("flag", False, VariableType.BOOL, save=False)
        cond = Condition("flag", "==", "True",
                         actions_true=[ActionEntry("x.exec", "mock", json.dumps({"src": "T"}))],
                         actions_false=[ActionEntry("x.exec", "mock", json.dumps({"src": "F"}))])
        execute_button(self._btn([cond]), "c1")
        time.sleep(0.15)
        srcs = [t["src"] for t in self.log]
        self.assertIn("F", srcs)
        self.assertNotIn("T", srcs)

    def test_base_and_condition_both_run(self):
        from macro_deck_python.models.action_button import ActionEntry, Condition
        from macro_deck_python.services.action_executor import execute_button
        cond = Condition("flag", "==", "True",
                         actions_true=[ActionEntry("x.exec", "mock", json.dumps({"src": "T"}))],
                         actions_false=[])
        execute_button(self._btn([cond]), "c1")
        time.sleep(0.15)
        self.assertEqual(len(self.log), 2)

    def test_numeric_condition(self):
        from macro_deck_python.models.action_button import ActionEntry, Condition
        from macro_deck_python.services.action_executor import execute_button
        cond = Condition("count", ">", "3",
                         actions_true=[ActionEntry("x.exec", "mock", json.dumps({"src": "high"}))],
                         actions_false=[ActionEntry("x.exec", "mock", json.dumps({"src": "low"}))])
        execute_button(self._btn([cond]), "c1")
        time.sleep(0.15)
        srcs = [t["src"] for t in self.log]
        self.assertIn("high", srcs)
        self.assertNotIn("low", srcs)

    def test_missing_plugin_does_not_crash(self):
        from macro_deck_python.models.action_button import ActionButton, ActionEntry
        from macro_deck_python.services.action_executor import execute_button
        b = ActionButton()
        b.actions.append(ActionEntry("no.plugin", "no.action", "{}"))
        execute_button(b, "c1")   # must not raise
        time.sleep(0.15)

    def test_client_id_passed_to_trigger(self):
        from macro_deck_python.services.action_executor import execute_button
        execute_button(self._btn(), "my-special-client")
        time.sleep(0.15)
        self.assertEqual(len(self.log), 1)  # just verifies it ran


# ════════════════════════════════════════════════════════════════════
# WEBSOCKET PROTOCOL
# ════════════════════════════════════════════════════════════════════

class TestProtocol(unittest.TestCase):
    def test_encode_decode_method_only(self):
        from macro_deck_python.websocket.protocol import encode, decode
        self.assertEqual(decode(encode("PING"))["method"], "PING")

    def test_encode_with_extra_fields(self):
        from macro_deck_python.websocket.protocol import encode, decode
        d = decode(encode("BTN", pos="0_0", pid="p1"))
        self.assertEqual(d["method"], "BTN")
        self.assertEqual(d["pos"], "0_0")
        self.assertEqual(d["pid"], "p1")

    def test_invalid_json_raises(self):
        from macro_deck_python.websocket.protocol import decode
        import json
        with self.assertRaises(json.JSONDecodeError):
            decode("{bad json!!}")

    def test_nested_payload(self):
        from macro_deck_python.websocket.protocol import encode, decode
        d = decode(encode("VARS", vars=[{"name": "x", "value": 1}]))
        self.assertEqual(d["vars"][0]["name"], "x")

    def test_encode_produces_valid_json(self):
        from macro_deck_python.websocket.protocol import encode
        raw = encode("TEST", a=1, b="two", c=[3, 4])
        parsed = json.loads(raw)
        self.assertEqual(parsed["a"], 1)
        self.assertEqual(parsed["b"], "two")
        self.assertEqual(parsed["c"], [3, 4])

    def test_boolean_fields(self):
        from macro_deck_python.websocket.protocol import encode, decode
        d = decode(encode("STATE", state=True))
        self.assertTrue(d["state"])


# ════════════════════════════════════════════════════════════════════
# SYSTEM VARIABLES PLUGIN
# ════════════════════════════════════════════════════════════════════

class TestSysVarsPlugin(unittest.TestCase):
    def setUp(self):
        from macro_deck_python.services.variable_manager import VariableManager
        from macro_deck_python.plugins.plugin_manager import PluginManager
        VariableManager._variables.clear()
        VariableManager._on_change_callbacks.clear()
        PluginManager._plugins.clear()
        PluginManager._actions.clear()
        builtin = pathlib.Path(__file__).parent.parent / "plugins" / "builtin"
        PluginManager.set_plugins_dir(builtin)
        PluginManager.load_all_plugins()
        self.sv = PluginManager.get_plugin("builtin.system_variables")
        self.sv._update()

    def test_time_format(self):
        from macro_deck_python.services.variable_manager import VariableManager
        t = VariableManager.get_value("system_time")
        self.assertIsNotNone(t)
        self.assertRegex(t, r"^\d{2}:\d{2}:\d{2}$")

    def test_date_format(self):
        from macro_deck_python.services.variable_manager import VariableManager
        d = VariableManager.get_value("system_date")
        self.assertIsNotNone(d)
        self.assertRegex(d, r"^\d{4}-\d{2}-\d{2}$")

    def test_datetime_format(self):
        from macro_deck_python.services.variable_manager import VariableManager
        dt = VariableManager.get_value("system_datetime")
        self.assertIsNotNone(dt)
        self.assertRegex(dt, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_cpu_published_if_psutil(self):
        try:
            import psutil
            from macro_deck_python.services.variable_manager import VariableManager
            cpu = VariableManager.get_value("system_cpu_percent")
            self.assertIsNotNone(cpu)
            self.assertGreaterEqual(float(cpu), 0.0)
            self.assertLessEqual(float(cpu), 100.0)
        except ImportError:
            self.skipTest("psutil not installed")

    def test_ram_published_if_psutil(self):
        try:
            import psutil
            from macro_deck_python.services.variable_manager import VariableManager
            ram = VariableManager.get_value("system_ram_percent")
            self.assertIsNotNone(ram)
            self.assertGreaterEqual(float(ram), 0.0)
            self.assertLessEqual(float(ram), 100.0)
        except ImportError:
            self.skipTest("psutil not installed")


# ════════════════════════════════════════════════════════════════════
# LOGGER
# ════════════════════════════════════════════════════════════════════

class TestLogger(unittest.TestCase):
    def test_all_levels_no_crash(self):
        from macro_deck_python.utils.logger import MacroDeckLogger
        MacroDeckLogger.trace(None, "trace msg")
        MacroDeckLogger.info(None, "info msg")
        MacroDeckLogger.warning(None, "warning msg")
        MacroDeckLogger.error(None, "error msg")

    def test_with_plugin(self):
        from macro_deck_python.utils.logger import MacroDeckLogger
        from macro_deck_python.plugins.base import IMacroDeckPlugin
        class FP(IMacroDeckPlugin):
            name = version = author = description = ""
            def enable(self): pass
        p = FP(); p.package_id = "log.test.plugin"
        MacroDeckLogger.info(p, "plugin log message")
        MacroDeckLogger.error(p, "plugin error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
