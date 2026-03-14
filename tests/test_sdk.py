"""
test_sdk.py — tests for the Python extension SDK

Tests:
  1.  PluginBase decorator style — @action auto-discovery
  2.  @action with on_load / on_delete lifecycle hooks
  3.  PluginBase class style — ActionBase subclasses
  4.  Mixed style — @action + explicit ActionBase
  5.  ActionBase.get_config() JSON helper
  6.  PluginBase config shortcuts (get_config / set_config)
  7.  PluginBase variable shortcuts (set_variable / get_variable)
  8.  PluginBase log shortcuts (no crash)
  9.  SDK free-function API (set_variable, get_variable, get_config …)
  10. Plugin validation (bad manifest, missing Main, wrong base class)
  11. Plugin unload (disable called, removed from registry)
  12. Scaffold CLI — decorator and class styles
  13. Scaffold CLI — duplicate package_id raises
  14. Scaffold CLI — all output files created correctly
  15. Hot-reload watcher — detects file change and reloads
  16. Decorator actions wired through executor end-to-end
  17. Multiple @action methods in one PluginBase
  18. action_id defaults to method name
  19. can_configure flag propagated correctly
  20. SDK imports (nothing crashes on import)
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import shutil
import sys
import tempfile
import time
import threading
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))


# ─── helpers ─────────────────────────────────────────────────────────

def _reset():
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


# ═══════════════════════════════════════════════════════════════════════
# 1-9  SDK PLUGIN BASE
# ═══════════════════════════════════════════════════════════════════════

class TestPluginBaseDecorator(unittest.TestCase):
    """Tests for decorator-style plugin authoring."""

    def setUp(self):
        _reset()

    def _make_plugin(self, log):
        from macro_deck_python.sdk import PluginBase, action, on_load, on_delete, VariableType

        class MyPlugin(PluginBase):
            package_id  = "test.decorator"
            name        = "Decorator Test"
            version     = "1.0.0"
            author      = "Test"
            description = "Test plugin"

            @action(name="Fire", description="Fires", can_configure=False)
            def fire(self, client_id, button):
                log.append(("fire", client_id))

            @action(name="Cfg", description="Configured", can_configure=True)
            def configured(self, client_id, button):
                cfg = json.loads(self.configuration) if self.configuration else {}
                log.append(("cfg", cfg.get("key", "?")))

            @on_load("configured")
            def configured_loaded(self):
                log.append(("load", "configured"))

            @on_delete("configured")
            def configured_deleted(self):
                log.append(("delete", "configured"))

        p = MyPlugin()
        p.enable()
        return p

    def test_actions_discovered(self):
        log = []
        p = self._make_plugin(log)
        self.assertEqual(len(p.actions), 2)

    def test_action_ids_default_to_method_names(self):
        log = []
        p = self._make_plugin(log)
        ids = {a.action_id for a in p.actions}
        self.assertIn("fire", ids)
        self.assertIn("configured", ids)

    def test_action_names_set_correctly(self):
        log = []
        p = self._make_plugin(log)
        names = {a.name for a in p.actions}
        self.assertIn("Fire", names)
        self.assertIn("Cfg", names)

    def test_can_configure_propagated(self):
        log = []
        p = self._make_plugin(log)
        fire_act     = next(a for a in p.actions if a.action_id == "fire")
        cfg_act      = next(a for a in p.actions if a.action_id == "configured")
        self.assertFalse(fire_act.can_configure)
        self.assertTrue(cfg_act.can_configure)

    def test_trigger_fires_method(self):
        log = []
        p = self._make_plugin(log)
        fire_act = next(a for a in p.actions if a.action_id == "fire")
        fire_act.plugin = p
        fire_act.trigger("client-1", None)
        self.assertIn(("fire", "client-1"), log)

    def test_trigger_passes_configuration(self):
        log = []
        p = self._make_plugin(log)
        cfg_act = next(a for a in p.actions if a.action_id == "configured")
        cfg_act.plugin = p
        cfg_act.configuration = json.dumps({"key": "hello"})
        cfg_act.trigger("c", None)
        self.assertIn(("cfg", "hello"), log)

    def test_on_load_hook_fires(self):
        log = []
        p = self._make_plugin(log)
        cfg_act = next(a for a in p.actions if a.action_id == "configured")
        cfg_act.plugin = p
        cfg_act.on_action_button_loaded()
        self.assertIn(("load", "configured"), log)

    def test_on_delete_hook_fires(self):
        log = []
        p = self._make_plugin(log)
        cfg_act = next(a for a in p.actions if a.action_id == "configured")
        cfg_act.plugin = p
        cfg_act.on_action_button_delete()
        self.assertIn(("delete", "configured"), log)

    def test_no_trigger_without_plugin(self):
        log = []
        p = self._make_plugin(log)
        fire_act = next(a for a in p.actions if a.action_id == "fire")
        fire_act.plugin = None
        fire_act.trigger("c", None)   # must not raise
        self.assertEqual(log, [])

    def test_explicit_action_id(self):
        from macro_deck_python.sdk import PluginBase, action
        log = []
        class P(PluginBase):
            package_id = "test.explicit_id"
            name = version = author = description = ""
            @action(name="X", action_id="my_explicit_id")
            def whatever_name(self, cid, btn):
                log.append("x")
        p = P(); p.enable()
        self.assertEqual(p.actions[0].action_id, "my_explicit_id")

    def test_multiple_actions_in_one_plugin(self):
        from macro_deck_python.sdk import PluginBase, action
        class P(PluginBase):
            package_id = "test.multi"
            name = version = author = description = ""
            @action(name="A") 
            def a(self, cid, btn): pass
            @action(name="B") 
            def b(self, cid, btn): pass
            @action(name="C") 
            def c(self, cid, btn): pass
            @action(name="D") 
            def d(self, cid, btn): pass
        p = P(); p.enable()
        self.assertEqual(len(p.actions), 4)


class TestPluginBaseClassStyle(unittest.TestCase):
    """Tests for traditional class-style (ActionBase subclass) authoring."""

    def setUp(self):
        _reset()

    def test_class_style_actions(self):
        from macro_deck_python.sdk import PluginBase, ActionBase
        log = []

        class HelloAction(ActionBase):
            action_id = "hello"; name = "Hello"; description = ""
            def trigger(self, cid, btn):
                log.append(cid)

        class Main(PluginBase):
            package_id = "test.class_style"
            name = version = author = description = ""
            def enable(self):
                super().enable()
                self.actions.append(HelloAction())

        p = Main(); p.enable()
        act = p.actions[0]
        act.plugin = p
        act.trigger("c-1", None)
        self.assertIn("c-1", log)

    def test_get_config_helper(self):
        from macro_deck_python.sdk import ActionBase
        class A(ActionBase):
            action_id = "a"; name = ""; description = ""
            def trigger(self, c, b): pass
        a = A()
        a.configuration = json.dumps({"x": 42, "y": "hello"})
        self.assertEqual(a.get_config("x"), 42)
        self.assertEqual(a.get_config("y"), "hello")
        self.assertIsNone(a.get_config("missing"))
        self.assertEqual(a.get_config("missing", "default"), "default")

    def test_get_config_empty_configuration(self):
        from macro_deck_python.sdk import ActionBase
        class A(ActionBase):
            action_id = "a"; name = ""; description = ""
            def trigger(self, c, b): pass
        a = A()
        a.configuration = ""
        self.assertIsNone(a.get_config("anything"))

    def test_get_config_invalid_json(self):
        from macro_deck_python.sdk import ActionBase
        class A(ActionBase):
            action_id = "a"; name = ""; description = ""
            def trigger(self, c, b): pass
        a = A()
        a.configuration = "{not json}"
        self.assertIsNone(a.get_config("x"))


class TestPluginBaseShortcuts(unittest.TestCase):
    """Tests for PluginBase convenience methods."""

    def setUp(self):
        _reset()
        from macro_deck_python.sdk import PluginBase
        class P(PluginBase):
            package_id = "test.shortcuts"
            name = version = author = description = ""
            def enable(self): super().enable()
        self.p = P(); self.p.enable()

    def test_config_shortcuts(self):
        self.p.set_config("my_key", "my_value")
        self.assertEqual(self.p.get_config("my_key"), "my_value")
        self.assertEqual(self.p.get_config("missing", "default"), "default")

    def test_variable_shortcuts(self):
        from macro_deck_python.models.variable import VariableType
        self.p.set_variable("test_var", 99, VariableType.INTEGER)
        self.assertEqual(self.p.get_variable("test_var"), 99)

    def test_variable_save_false(self):
        from macro_deck_python.models.variable import VariableType
        from macro_deck_python.services.variable_manager import VariableManager
        self.p.set_variable("ephemeral", "x", VariableType.STRING, save=False)
        v = VariableManager.get_variable("ephemeral")
        self.assertFalse(v.save)

    def test_log_shortcuts_no_crash(self):
        self.p.log_trace("trace")
        self.p.log_info("info")
        self.p.log_warning("warn")
        self.p.log_error("err")


class TestSDKFunctions(unittest.TestCase):
    """Tests for the free-function API in sdk.api."""

    def setUp(self):
        _reset()
        from macro_deck_python.sdk import PluginBase
        class P(PluginBase):
            package_id = "test.api_fns"
            name = version = author = description = ""
            def enable(self): super().enable()
        self.p = P(); self.p.enable()

    def test_set_get_variable(self):
        from macro_deck_python.sdk import set_variable, get_variable, VariableType
        set_variable("sdk_var", 42, VariableType.INTEGER, self.p)
        self.assertEqual(get_variable("sdk_var"), 42)

    def test_set_get_config(self):
        from macro_deck_python.sdk import get_config, set_config
        set_config(self.p, "cfg_key", "cfg_val")
        self.assertEqual(get_config(self.p, "cfg_key"), "cfg_val")

    def test_credentials_encrypt_decrypt(self):
        from macro_deck_python.sdk import get_credentials, set_credentials, delete_credentials
        import macro_deck_python.plugins.base as base_mod
        tmp = pathlib.Path(tempfile.mkdtemp())
        orig_dir = base_mod.PluginCredentials._CREDS_DIR
        orig_key = base_mod._KEY_FILE
        base_mod.PluginCredentials._CREDS_DIR = tmp / "creds"
        base_mod._KEY_FILE = tmp / ".key"
        base_mod.PluginCredentials._CREDS_DIR.mkdir()
        try:
            set_credentials(self.p, {"user": "alice", "token": "xyz"})
            creds = get_credentials(self.p)
            self.assertEqual(len(creds), 1)
            self.assertEqual(creds[0]["user"], "alice")
            delete_credentials(self.p)
            self.assertEqual(get_credentials(self.p), [])
        finally:
            base_mod.PluginCredentials._CREDS_DIR = orig_dir
            base_mod._KEY_FILE = orig_key
            shutil.rmtree(tmp, ignore_errors=True)

    def test_log_functions_no_crash(self):
        from macro_deck_python.sdk import log_trace, log_info, log_warning, log_error
        log_trace(self.p, "trace")
        log_info(self.p, "info")
        log_warning(self.p, "warn")
        log_error(self.p, "err")
        log_info(None, "no plugin")


# ═══════════════════════════════════════════════════════════════════════
# 10-11  PLUGIN VALIDATION & UNLOAD
# ═══════════════════════════════════════════════════════════════════════

class TestPluginValidation(unittest.TestCase):
    def setUp(self):
        _reset()
        self._tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_plugin(self, manifest: dict, main_code: str) -> pathlib.Path:
        pid = manifest.get("package_id", "test.invalid")
        d = self._tmp / pid
        d.mkdir()
        (d / "manifest.json").write_text(json.dumps(manifest))
        (d / "main.py").write_text(main_code)
        return d

    def _load(self, plugin_dir):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager._plugins.clear()
        PluginManager._actions.clear()
        PluginManager.set_plugins_dir(self._tmp)
        PluginManager._load_plugin(plugin_dir)

    def test_missing_package_id_raises(self):
        from macro_deck_python.plugins.plugin_manager import PluginValidationError
        d = self._tmp / "bad"
        d.mkdir()
        (d / "manifest.json").write_text(json.dumps({"name": "Bad", "version": "1.0.0"}))
        (d / "main.py").write_text("")
        with self.assertRaises(PluginValidationError):
            from macro_deck_python.plugins.plugin_manager import PluginManager
            PluginManager._load_plugin(d)

    def test_missing_name_raises(self):
        from macro_deck_python.plugins.plugin_manager import PluginValidationError
        d = self._write_plugin(
            {"package_id": "test.noname", "version": "1.0.0"},
            "class Main: pass"
        )
        from macro_deck_python.plugins.plugin_manager import PluginManager
        with self.assertRaises(PluginValidationError):
            PluginManager._load_plugin(d)

    def test_package_id_with_spaces_raises(self):
        from macro_deck_python.plugins.plugin_manager import PluginValidationError
        d = self._write_plugin(
            {"package_id": "bad id with spaces", "name": "Bad", "version": "1.0.0"},
            ""
        )
        from macro_deck_python.plugins.plugin_manager import PluginManager
        with self.assertRaises(PluginValidationError):
            PluginManager._load_plugin(d)

    def test_missing_main_class_raises(self):
        from macro_deck_python.plugins.plugin_manager import PluginValidationError
        d = self._write_plugin(
            {"package_id": "test.nomain", "name": "No Main", "version": "1.0.0"},
            "# no Main class here\nx = 1"
        )
        from macro_deck_python.plugins.plugin_manager import PluginManager
        with self.assertRaises(PluginValidationError):
            PluginManager._load_plugin(d)

    def test_main_wrong_base_class_raises(self):
        from macro_deck_python.plugins.plugin_manager import PluginValidationError
        d = self._write_plugin(
            {"package_id": "test.wrongbase", "name": "Wrong Base", "version": "1.0.0"},
            "class Main:  # not a subclass of IMacroDeckPlugin\n    pass"
        )
        from macro_deck_python.plugins.plugin_manager import PluginManager
        with self.assertRaises(PluginValidationError):
            PluginManager._load_plugin(d)

    def test_valid_plugin_loads_ok(self):
        d = self._write_plugin(
            {"package_id": "test.valid_v", "name": "Valid", "version": "1.0.0"},
            "from macro_deck_python.sdk import PluginBase\n"
            "class Main(PluginBase):\n"
            "    package_id = 'test.valid_v'\n"
            "    name = version = author = description = ''\n"
            "    def enable(self): super().enable()\n"
        )
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager.set_plugins_dir(self._tmp)
        PluginManager._load_plugin(d)
        self.assertIn("test.valid_v", PluginManager._plugins)


class TestPluginUnload(unittest.TestCase):
    def setUp(self):
        _reset()
        self._tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_unload_calls_disable(self):
        disabled = []
        from macro_deck_python.sdk import PluginBase
        from macro_deck_python.plugins.plugin_manager import PluginManager

        class P(PluginBase):
            package_id = "test.unload"
            name = version = author = description = ""
            def enable(self): super().enable()
            def disable(self): disabled.append(True)

        p = P(); p.enable()
        PluginManager._plugins["test.unload"] = p
        PluginManager._actions["test.unload"] = {}

        ok = PluginManager.unload_plugin("test.unload")
        self.assertTrue(ok)
        self.assertNotIn("test.unload", PluginManager._plugins)
        self.assertNotIn("test.unload", PluginManager._actions)
        self.assertEqual(disabled, [True])

    def test_unload_nonexistent_returns_false(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        self.assertFalse(PluginManager.unload_plugin("does.not.exist"))


# ═══════════════════════════════════════════════════════════════════════
# 12-14  SCAFFOLD CLI
# ═══════════════════════════════════════════════════════════════════════

class TestScaffold(unittest.TestCase):
    def setUp(self):
        self._tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _scaffold(self, name, pid, style="decorator"):
        from macro_deck_python.cli.scaffold import scaffold
        return scaffold(
            name=name, package_id=pid,
            author="Test Author", description="Test desc",
            style=style, output_dir=self._tmp,
        )

    def test_decorator_style_files_created(self):
        out = self._scaffold("My Plugin", "me.myplugin", style="decorator")
        self.assertTrue((out / "main.py").exists())
        self.assertTrue((out / "manifest.json").exists())
        self.assertTrue((out / "requirements.txt").exists())
        self.assertTrue((out / "README.md").exists())
        self.assertTrue((out / "config.json").exists())

    def test_class_style_files_created(self):
        out = self._scaffold("Class Plugin", "me.classplugin", style="class")
        self.assertTrue((out / "main.py").exists())
        self.assertTrue((out / "manifest.json").exists())

    def test_manifest_content(self):
        out = self._scaffold("Test Plugin", "me.testplug")
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["package_id"], "me.testplug")
        self.assertEqual(manifest["name"], "Test Plugin")
        self.assertEqual(manifest["author"], "Test Author")
        self.assertEqual(manifest["version"], "1.0.0")

    def test_main_py_contains_package_id(self):
        out = self._scaffold("Check Plugin", "me.checkplug")
        src = (out / "main.py").read_text()
        self.assertIn("me.checkplug", src)

    def test_main_py_imports_sdk(self):
        out = self._scaffold("SDK Import Test", "me.sdkimport")
        src = (out / "main.py").read_text()
        self.assertIn("macro_deck_python.sdk", src)

    def test_class_style_inherits_action_base(self):
        out = self._scaffold("Class Test", "me.classtest", style="class")
        src = (out / "main.py").read_text()
        self.assertIn("ActionBase", src)

    def test_duplicate_raises(self):
        from macro_deck_python.cli.scaffold import scaffold
        self._scaffold("First", "me.dup")
        with self.assertRaises(FileExistsError):
            scaffold("Second", "me.dup",
                     output_dir=self._tmp, style="decorator")

    def test_generated_plugin_is_loadable(self):
        """The scaffolded plugin must pass validation and load correctly."""
        out = self._scaffold("Load Test", "me.loadtest", style="decorator")
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager._plugins.clear()
        PluginManager._actions.clear()
        PluginManager.set_plugins_dir(self._tmp)
        PluginManager._load_plugin(out)
        self.assertIn("me.loadtest", PluginManager._plugins)
        # Decorator style generates hello_world, configurable, set_counter actions
        acts = list(PluginManager._actions["me.loadtest"].keys())
        self.assertGreaterEqual(len(acts), 1)

    def test_generated_class_plugin_is_loadable(self):
        """Class-style scaffolded plugin must also load correctly."""
        out = self._scaffold("Load Class", "me.loadclass", style="class")
        from macro_deck_python.plugins.plugin_manager import PluginManager
        PluginManager._plugins.clear()
        PluginManager._actions.clear()
        PluginManager.set_plugins_dir(self._tmp)
        PluginManager._load_plugin(out)
        self.assertIn("me.loadclass", PluginManager._plugins)


# ═══════════════════════════════════════════════════════════════════════
# 15  HOT-RELOAD WATCHER
# ═══════════════════════════════════════════════════════════════════════

class TestHotReload(unittest.TestCase):
    def setUp(self):
        _reset()
        self._tmp = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_plugin(self, pid: str, action_name: str) -> pathlib.Path:
        d = self._tmp / pid
        d.mkdir(exist_ok=True)
        (d / "manifest.json").write_text(json.dumps({
            "package_id": pid, "name": pid, "version": "1.0.0",
        }))
        (d / "main.py").write_text(
            f"from macro_deck_python.sdk import PluginBase, action\n"
            f"class Main(PluginBase):\n"
            f"    package_id = '{pid}'\n"
            f"    name = version = author = description = ''\n"
            f"    @action(name='{action_name}')\n"
            f"    def the_action(self, cid, btn): pass\n"
        )
        return d

    def test_initial_load_then_reload_on_change(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.services.hot_reload import HotReloadWatcher

        pid = "test.hotreload"
        plugin_dir = self._write_plugin(pid, "Version1")

        # Initial load
        PluginManager.set_plugins_dir(self._tmp)
        PluginManager._load_plugin(plugin_dir)
        self.assertIn(pid, PluginManager._plugins)
        v1_actions = list(PluginManager._actions[pid].keys())
        self.assertEqual(v1_actions, ["the_action"])

        reloaded = []
        watcher = HotReloadWatcher(
            plugins_dir=self._tmp,
            interval=0.2,
            on_reload=lambda pkg: reloaded.append(pkg),
        )

        # Prime the watcher's mtime snapshot so it knows the baseline
        watcher._scan()

        # Modify the plugin — change the action name (simulates dev editing)
        time.sleep(0.05)
        (plugin_dir / "main.py").write_text(
            f"from macro_deck_python.sdk import PluginBase, action\n"
            f"class Main(PluginBase):\n"
            f"    package_id = '{pid}'\n"
            f"    name = version = author = description = ''\n"
            f"    @action(name='Version2')\n"
            f"    def the_action(self, cid, btn): pass\n"
            f"    @action(name='NewAction')\n"
            f"    def new_action(self, cid, btn): pass\n"
        )

        # Trigger one scan cycle
        watcher._scan()

        # Verify reload happened
        self.assertIn(pid, reloaded)
        self.assertIn(pid, PluginManager._plugins)
        # Should now have 2 actions
        new_actions = PluginManager._actions.get(pid, {})
        self.assertEqual(len(new_actions), 2)
        self.assertIn("new_action", new_actions)

    def test_no_reload_without_change(self):
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.services.hot_reload import HotReloadWatcher

        pid = "test.nochange"
        plugin_dir = self._write_plugin(pid, "Stable")
        PluginManager.set_plugins_dir(self._tmp)
        PluginManager._load_plugin(plugin_dir)

        reloaded = []
        watcher = HotReloadWatcher(self._tmp, interval=0.2,
                                   on_reload=lambda p: reloaded.append(p))
        watcher._scan()   # prime
        watcher._scan()   # second scan — no change
        self.assertEqual(reloaded, [])

    def test_watcher_start_stop(self):
        from macro_deck_python.services.hot_reload import HotReloadWatcher
        w = HotReloadWatcher(self._tmp, interval=0.1)
        w.start()
        time.sleep(0.3)
        w.stop()
        self.assertFalse(w._thread.is_alive())


# ═══════════════════════════════════════════════════════════════════════
# 16  END-TO-END: DECORATOR ACTION THROUGH EXECUTOR
# ═══════════════════════════════════════════════════════════════════════

class TestDecoratorActionEndToEnd(unittest.TestCase):
    def setUp(self):
        _reset()

    def test_decorator_action_triggered_via_executor(self):
        from macro_deck_python.sdk import PluginBase, action, VariableType, set_variable
        from macro_deck_python.plugins.plugin_manager import PluginManager
        from macro_deck_python.models.action_button import ActionButton, ActionEntry
        from macro_deck_python.services.action_executor import execute_button
        from macro_deck_python.services.variable_manager import VariableManager

        fired = []

        class Main(PluginBase):
            package_id = "e2e.decorator"
            name = version = author = description = ""

            @action(name="Increment")
            def increment(self, client_id, button):
                current = VariableManager.get_value("e2e_count") or 0
                set_variable("e2e_count", int(current) + 1, VariableType.INTEGER, self)
                fired.append(client_id)

        plugin = Main(); plugin.enable()
        PluginManager._plugins["e2e.decorator"] = plugin
        act = plugin.actions[0]
        act.plugin = plugin
        PluginManager._actions["e2e.decorator"] = {"increment": act}

        btn = ActionButton()
        btn.actions.append(ActionEntry("e2e.decorator", "increment", "{}"))
        execute_button(btn, "e2e-client")
        time.sleep(0.2)

        self.assertIn("e2e-client", fired)
        self.assertEqual(VariableManager.get_value("e2e_count"), 1)


# ═══════════════════════════════════════════════════════════════════════
# 20  SDK IMPORT SMOKE TEST
# ═══════════════════════════════════════════════════════════════════════

class TestSDKImports(unittest.TestCase):
    def test_all_public_names_importable(self):
        from macro_deck_python import sdk
        for name in sdk.__all__:
            self.assertTrue(hasattr(sdk, name), f"sdk.{name} missing")

    def test_plugin_base_importable(self):
        from macro_deck_python.sdk import PluginBase
        self.assertTrue(issubclass(PluginBase, object))

    def test_action_base_importable(self):
        from macro_deck_python.sdk import ActionBase
        self.assertTrue(issubclass(ActionBase, object))

    def test_variable_type_importable(self):
        from macro_deck_python.sdk import VariableType
        self.assertEqual(VariableType.INTEGER.value, "Integer")

    def test_decorator_importable(self):
        from macro_deck_python.sdk import action, on_load, on_delete
        self.assertTrue(callable(action))
        self.assertTrue(callable(on_load))
        self.assertTrue(callable(on_delete))


if __name__ == "__main__":
    unittest.main(verbosity=2)
