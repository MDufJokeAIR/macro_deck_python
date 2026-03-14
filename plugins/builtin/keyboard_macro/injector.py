"""
injector.py — cross-platform low-level key injection.

Hierarchy of backends (tried in order):
  1. Windows  : ctypes SendInput (native, no dep)
  2. macOS    : Quartz CGEvent   (native, no dep on macOS)
  3. Linux    : xdotool          (CLI, widely available)
  4. Linux    : python-xlib      (pure Python)
  5. Linux    : evdev / uinput   (kernel level, needs permissions)
  6. Fallback : pyautogui        (cross-platform, needs display)

All backends expose:
    press(key_name)           — press and immediately release
    down(key_name)            — key down only
    up(key_name)              — key up only
    combo(key_names)          — hold keys 1..N-1, tap key N, release in reverse
    mouse_click(button, n)    — click mouse button n times
"""
from __future__ import annotations

import logging
import platform
import subprocess
import time
from typing import List, Optional

from macro_deck_python.plugins.builtin.keyboard_macro.key_map import resolve, KEY_MAP

logger = logging.getLogger("plugin.keyboard_macro.injector")

_OS = platform.system()   # "Windows" | "Linux" | "Darwin"


# ═══════════════════════════════════════════════════════════════════════
# Windows backend (SendInput)
# ═══════════════════════════════════════════════════════════════════════

class _WindowsBackend:
    """Uses ctypes + SendInput. Zero external dependencies on Windows."""

    def __init__(self):
        import ctypes
        import ctypes.wintypes
        self._ctypes = ctypes

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001

        # Extended VK codes that need EXTENDEDKEY flag
        self._EXTENDED = {
            0xA3, 0xA5,               # RCtrl, RAlt
            0x26, 0x28, 0x25, 0x27,   # arrows
            0x24, 0x23, 0x21, 0x22,   # Home End PgUp PgDn
            0x2D, 0x2E,               # Insert Delete
            0x5B, 0x5C, 0x5D,         # Win keys, Menu
            0x6F,                     # Numpad Divide
            0x0D,                     # Numpad Enter  (handled separately)
        }

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk",         ctypes.wintypes.WORD),
                ("wScan",       ctypes.wintypes.WORD),
                ("dwFlags",     ctypes.wintypes.DWORD),
                ("time",        ctypes.wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class _INPUT_union(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.wintypes.DWORD), ("_input", _INPUT_union)]

        self._INPUT = INPUT
        self._KEYBDINPUT = KEYBDINPUT
        self._INPUT_KEYBOARD = INPUT_KEYBOARD
        self._KEYEVENTF_KEYUP = KEYEVENTF_KEYUP
        self._KEYEVENTF_EXTENDEDKEY = KEYEVENTF_EXTENDEDKEY
        self._send = ctypes.windll.user32.SendInput

    def _make_input(self, vk: int, key_up: bool) -> object:
        flags = 0
        if vk in self._EXTENDED:
            flags |= self._KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= self._KEYEVENTF_KEYUP
        ki = self._KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0,
                               dwExtraInfo=None)
        inp = self._INPUT(type=self._INPUT_KEYBOARD)
        inp._input.ki = ki
        return inp

    def _send_inputs(self, inputs: list) -> None:
        arr_type = self._INPUT * len(inputs)
        arr = arr_type(*inputs)
        self._send(len(inputs), arr, self._ctypes.sizeof(self._INPUT))

    def _vk(self, key_name: str) -> Optional[int]:
        entry = resolve(key_name)
        if entry is None:
            logger.warning("Unknown key: %s", key_name)
            return None
        vk = entry.get("win", -1)
        return vk if vk != -1 else None

    def down(self, key_name: str) -> None:
        vk = self._vk(key_name)
        if vk: self._send_inputs([self._make_input(vk, False)])

    def up(self, key_name: str) -> None:
        vk = self._vk(key_name)
        if vk: self._send_inputs([self._make_input(vk, True)])

    def press(self, key_name: str) -> None:
        vk = self._vk(key_name)
        if vk:
            self._send_inputs([self._make_input(vk, False),
                                self._make_input(vk, True)])

    def combo(self, keys: List[str]) -> None:
        if not keys: return
        downs, ups = [], []
        for k in keys:
            vk = self._vk(k)
            if vk:
                downs.append(self._make_input(vk, False))
                ups.insert(0, self._make_input(vk, True))
        self._send_inputs(downs + ups)

    def mouse_click(self, button: str = "mouse_left", n: int = 1) -> None:
        import ctypes
        MOUSEEVENTF = {"mouse_left": (0x0002, 0x0004),
                       "mouse_right": (0x0008, 0x0010),
                       "mouse_middle": (0x0020, 0x0040)}
        flags = MOUSEEVENTF.get(button, (0x0002, 0x0004))
        for _ in range(n):
            ctypes.windll.user32.mouse_event(flags[0], 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(flags[1], 0, 0, 0, 0)


# ═══════════════════════════════════════════════════════════════════════
# macOS backend (Quartz CGEvent)
# ═══════════════════════════════════════════════════════════════════════

class _MacBackend:
    def __init__(self):
        import Quartz  # type: ignore
        self._Q = Quartz

    def _cgcode(self, key_name: str) -> Optional[int]:
        entry = resolve(key_name)
        if entry is None:
            logger.warning("Unknown key: %s", key_name)
            return None
        code = entry.get("mac", -1)
        return code if code != -1 else None

    def _event(self, code: int, down: bool):
        Q = self._Q
        src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
        ev = Q.CGEventCreateKeyboardEvent(src, code, down)
        Q.CGEventPost(Q.kCGHIDEventTap, ev)

    def down(self, key_name: str) -> None:
        c = self._cgcode(key_name)
        if c is not None: self._event(c, True)

    def up(self, key_name: str) -> None:
        c = self._cgcode(key_name)
        if c is not None: self._event(c, False)

    def press(self, key_name: str) -> None:
        c = self._cgcode(key_name)
        if c is not None:
            self._event(c, True)
            self._event(c, False)

    def combo(self, keys: List[str]) -> None:
        for k in keys[:-1]: self.down(k)
        self.press(keys[-1])
        for k in reversed(keys[:-1]): self.up(k)

    def mouse_click(self, button: str = "mouse_left", n: int = 1) -> None:
        Q = self._Q
        src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
        btn_map = {"mouse_left": Q.kCGMouseButtonLeft,
                   "mouse_right": Q.kCGMouseButtonRight,
                   "mouse_middle": Q.kCGMouseButtonCenter}
        btn = btn_map.get(button, Q.kCGMouseButtonLeft)
        pos = Q.CGEventGetLocation(Q.CGEventCreate(src))
        for _ in range(n):
            Q.CGEventPost(Q.kCGHIDEventTap,
                Q.CGEventCreateMouseEvent(src, Q.kCGEventLeftMouseDown, pos, btn))
            Q.CGEventPost(Q.kCGHIDEventTap,
                Q.CGEventCreateMouseEvent(src, Q.kCGEventLeftMouseUp, pos, btn))


# ═══════════════════════════════════════════════════════════════════════
# Linux: xdotool backend (CLI)
# ═══════════════════════════════════════════════════════════════════════

class _XdotoolBackend:
    """Calls xdotool. Works with X11 and XWayland."""

    def _keysym(self, key_name: str) -> Optional[str]:
        entry = resolve(key_name)
        if entry is None:
            logger.warning("Unknown key: %s", key_name)
            return None
        ks = entry.get("linux")
        return ks if ks else None

    def _run(self, args: List[str]) -> None:
        try:
            subprocess.run(["xdotool"] + args,
                           capture_output=True, timeout=2)
        except FileNotFoundError:
            raise RuntimeError("xdotool not found — install it: apt install xdotool")
        except subprocess.TimeoutExpired:
            logger.error("xdotool timed out")

    def down(self, key_name: str) -> None:
        ks = self._keysym(key_name)
        if ks: self._run(["keydown", ks])

    def up(self, key_name: str) -> None:
        ks = self._keysym(key_name)
        if ks: self._run(["keyup", ks])

    def press(self, key_name: str) -> None:
        ks = self._keysym(key_name)
        if ks: self._run(["key", ks])

    def combo(self, keys: List[str]) -> None:
        syms = [self._keysym(k) for k in keys]
        syms = [s for s in syms if s]
        if syms: self._run(["key", "+".join(syms)])

    def mouse_click(self, button: str = "mouse_left", n: int = 1) -> None:
        btn_map = {"mouse_left": "1", "mouse_middle": "2", "mouse_right": "3",
                   "mouse_x1": "8", "mouse_x2": "9"}
        b = btn_map.get(button, "1")
        for _ in range(n):
            self._run(["click", b])


# ═══════════════════════════════════════════════════════════════════════
# Linux: python-xlib backend
# ═══════════════════════════════════════════════════════════════════════

class _XlibBackend:
    def __init__(self):
        from Xlib import display as xdisplay, X, XK  # type: ignore
        from Xlib.ext import xtest  # type: ignore
        self._display = xdisplay.Display()
        self._X = X
        self._XK = XK

    def _keycode(self, key_name: str) -> Optional[int]:
        entry = resolve(key_name)
        if not entry: return None
        ks_name = entry.get("linux")
        if not ks_name: return None
        keysym = self._XK.string_to_keysym(ks_name)
        if keysym == 0: return None
        return self._display.keysym_to_keycode(keysym)

    def _fake_key(self, code: int, pressed: bool) -> None:
        from Xlib.ext import xtest
        xtest.fake_input(self._display, self._X.KeyPress if pressed else self._X.KeyRelease, code)
        self._display.sync()

    def down(self, key_name: str) -> None:
        c = self._keycode(key_name)
        if c: self._fake_key(c, True)

    def up(self, key_name: str) -> None:
        c = self._keycode(key_name)
        if c: self._fake_key(c, False)

    def press(self, key_name: str) -> None:
        c = self._keycode(key_name)
        if c:
            self._fake_key(c, True)
            self._fake_key(c, False)

    def combo(self, keys: List[str]) -> None:
        codes = [self._keycode(k) for k in keys]
        codes = [c for c in codes if c]
        for c in codes: self._fake_key(c, True)
        for c in reversed(codes): self._fake_key(c, False)

    def mouse_click(self, button: str = "mouse_left", n: int = 1) -> None:
        from Xlib.ext import xtest
        btn_map = {"mouse_left": 1, "mouse_middle": 2, "mouse_right": 3,
                   "mouse_x1": 8, "mouse_x2": 9}
        b = btn_map.get(button, 1)
        for _ in range(n):
            xtest.fake_input(self._display, self._X.ButtonPress, b)
            xtest.fake_input(self._display, self._X.ButtonRelease, b)
            self._display.sync()


# ═══════════════════════════════════════════════════════════════════════
# Linux: evdev/uinput backend (kernel level)
# ═══════════════════════════════════════════════════════════════════════

class _EvdevBackend:
    """Uses /dev/uinput — requires the user to be in the 'input' group or root."""

    # Map linux keysym → evdev KEY_* code
    _EVDEV_MAP = {
        "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34,
        "h": 35, "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49,
        "o": 24, "p": 25, "q": 16, "r": 19, "s": 31, "t": 20, "u": 22,
        "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
        "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8,
        "8": 9, "9": 10,
        "F1": 59, "F2": 60, "F3": 61, "F4": 62, "F5": 63, "F6": 64,
        "F7": 65, "F8": 66, "F9": 67, "F10": 68, "F11": 87, "F12": 88,
        "Return": 28, "Escape": 1, "BackSpace": 14, "Tab": 15, "space": 57,
        "ctrl_l": 29, "ctrl_r": 97, "shift_l": 42, "shift_r": 54,
        "alt_l": 56, "alt_r": 100, "super": 125,
        "Up": 103, "Down": 108, "Left": 105, "Right": 106,
        "Home": 102, "End": 107, "Page_Up": 104, "Page_Down": 109,
        "Insert": 110, "Delete": 111,
    }

    def __init__(self):
        import evdev  # type: ignore
        ui = evdev.UInput()
        self._ui = ui
        self._evdev = evdev

    def _evcode(self, key_name: str) -> Optional[int]:
        entry = resolve(key_name)
        if not entry: return None
        ks = entry.get("linux")
        return self._EVDEV_MAP.get(ks)

    def _emit(self, code: int, val: int) -> None:
        import evdev
        self._ui.write(evdev.ecodes.EV_KEY, code, val)
        self._ui.syn()

    def down(self, key_name: str) -> None:
        c = self._evcode(key_name)
        if c is not None: self._emit(c, 1)

    def up(self, key_name: str) -> None:
        c = self._evcode(key_name)
        if c is not None: self._emit(c, 0)

    def press(self, key_name: str) -> None:
        c = self._evcode(key_name)
        if c is not None: self._emit(c, 1); self._emit(c, 0)

    def combo(self, keys: List[str]) -> None:
        codes = [self._evcode(k) for k in keys]
        codes = [c for c in codes if c is not None]
        for c in codes: self._emit(c, 1)
        for c in reversed(codes): self._emit(c, 0)

    def mouse_click(self, button: str = "mouse_left", n: int = 1) -> None:
        import evdev
        btn_map = {"mouse_left": evdev.ecodes.BTN_LEFT,
                   "mouse_right": evdev.ecodes.BTN_RIGHT,
                   "mouse_middle": evdev.ecodes.BTN_MIDDLE}
        b = btn_map.get(button, evdev.ecodes.BTN_LEFT)
        for _ in range(n):
            self._ui.write(evdev.ecodes.EV_KEY, b, 1); self._ui.syn()
            self._ui.write(evdev.ecodes.EV_KEY, b, 0); self._ui.syn()


# ═══════════════════════════════════════════════════════════════════════
# Fallback: pyautogui
# ═══════════════════════════════════════════════════════════════════════

class _PyautoguiBackend:
    def __init__(self):
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False
        self._pg = pyautogui

    def _pg_key(self, key_name: str) -> str:
        """Map our canonical names to pyautogui key strings."""
        PG = {
            "super": "winleft", "ctrl": "ctrl", "alt": "alt", "shift": "shift",
            "ctrl_left": "ctrlleft", "ctrl_right": "ctrlright",
            "shift_left": "shiftleft", "shift_right": "shiftright",
            "alt_left": "altleft", "alt_right": "altright",
            "enter": "enter", "escape": "esc", "backspace": "backspace",
            "tab": "tab", "space": "space",
            "up": "up", "down": "down", "left": "left", "right": "right",
            "home": "home", "end": "end", "page_up": "pageup", "page_down": "pagedown",
            "insert": "insert", "delete": "delete", "print_screen": "printscreen",
            "caps_lock": "capslock", "num_lock": "numlock", "scroll_lock": "scrolllock",
            "oem_plus": "=", "oem_minus": "-", "oem_comma": ",", "oem_period": ".",
            "oem_1": ";", "oem_2": "/", "oem_3": "`", "oem_4": "[",
            "oem_5": "\\", "oem_6": "]", "oem_7": "'",
        }
        for i in range(1, 25):
            PG[f"f{i}"] = f"f{i}"
        for i in range(10):
            PG[f"num{i}"] = f"num{i}"
        return PG.get(key_name, key_name)

    def down(self, key_name: str) -> None:
        try: self._pg.keyDown(self._pg_key(key_name))
        except Exception as e: logger.warning("pyautogui down %s: %s", key_name, e)

    def up(self, key_name: str) -> None:
        try: self._pg.keyUp(self._pg_key(key_name))
        except Exception as e: logger.warning("pyautogui up %s: %s", key_name, e)

    def press(self, key_name: str) -> None:
        try: self._pg.press(self._pg_key(key_name))
        except Exception as e: logger.warning("pyautogui press %s: %s", key_name, e)

    def combo(self, keys: List[str]) -> None:
        try: self._pg.hotkey(*[self._pg_key(k) for k in keys])
        except Exception as e: logger.warning("pyautogui combo %s: %s", keys, e)

    def mouse_click(self, button: str = "mouse_left", n: int = 1) -> None:
        btn_map = {"mouse_left": "left", "mouse_right": "right", "mouse_middle": "middle"}
        b = btn_map.get(button, "left")
        try: self._pg.click(button=b, clicks=n)
        except Exception as e: logger.warning("pyautogui click: %s", e)


# ═══════════════════════════════════════════════════════════════════════
# Backend factory — auto-detect best available
# ═══════════════════════════════════════════════════════════════════════

_backend = None

def _init_backend():
    global _backend
    if _backend is not None:
        return _backend

    if _OS == "Windows":
        try:
            _backend = _WindowsBackend()
            logger.info("Keyboard backend: Windows SendInput")
            return _backend
        except Exception as e:
            logger.warning("Windows backend failed: %s", e)

    if _OS == "Darwin":
        try:
            _backend = _MacBackend()
            logger.info("Keyboard backend: macOS Quartz")
            return _backend
        except Exception as e:
            logger.warning("macOS backend failed: %s", e)

    if _OS == "Linux":
        # Try xdotool (most compatible)
        try:
            result = subprocess.run(["xdotool", "version"],
                                    capture_output=True, timeout=2)
            if result.returncode == 0:
                _backend = _XdotoolBackend()
                logger.info("Keyboard backend: xdotool")
                return _backend
        except Exception:
            pass

        # Try python-xlib
        try:
            _backend = _XlibBackend()
            logger.info("Keyboard backend: python-xlib")
            return _backend
        except Exception as e:
            logger.debug("Xlib backend unavailable: %s", e)

        # Try evdev/uinput
        try:
            _backend = _EvdevBackend()
            logger.info("Keyboard backend: evdev/uinput")
            return _backend
        except Exception as e:
            logger.debug("evdev backend unavailable: %s", e)

    # Universal fallback
    try:
        _backend = _PyautoguiBackend()
        logger.info("Keyboard backend: pyautogui (fallback)")
        return _backend
    except Exception as e:
        logger.error("All keyboard backends failed. Last error: %s", e)
        raise RuntimeError("No keyboard injection backend available. "
                           "Install xdotool (Linux), or pip install pyautogui.")


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def press(key_name: str) -> None:
    """Press and immediately release one key."""
    _init_backend().press(key_name)

def down(key_name: str) -> None:
    """Hold a key down."""
    _init_backend().down(key_name)

def up(key_name: str) -> None:
    """Release a held key."""
    _init_backend().up(key_name)

def combo(keys: List[str]) -> None:
    """
    Send a key combination.
    Keys 0..N-2 are held, key N-1 is tapped, then all released in reverse.
    e.g. combo(["ctrl", "shift", "t"]) → Ctrl+Shift+T
    """
    if not keys:
        return
    if len(keys) == 1:
        press(keys[0])
    else:
        _init_backend().combo(keys)

def mouse_click(button: str = "mouse_left", n: int = 1) -> None:
    """Click a mouse button n times."""
    _init_backend().mouse_click(button, n)

def reset_backend() -> None:
    """Force re-detection of the best backend (e.g. after installing xdotool)."""
    global _backend
    _backend = None
