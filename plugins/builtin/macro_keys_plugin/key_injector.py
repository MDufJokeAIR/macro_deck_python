"""
key_injector.py  —  Cross-platform key injection engine.

Priority order:
  1. pynput  (best: works on Windows, macOS, Linux/X11/Wayland)
  2. pyautogui  (good: Windows, macOS, Linux/X11)
  3. Linux Xtst via ctypes  (fallback: Linux/X11 only, no extra deps)
  4. Windows ctypes SendInput  (fallback: Windows only)
  5. Raise ImportError with install hint.

Each backend implements the same interface:
  press(key_def)   — press and release once
  down(key_def)    — press and hold
  up(key_def)      — release
"""
from __future__ import annotations

import logging
import platform
import time
from typing import Optional

from macro_deck_python.plugins.builtin.macro_keys_plugin.key_map import KeyDef

logger = logging.getLogger("plugin.macro_keys.injector")

_OS = platform.system()   # "Windows" | "Darwin" | "Linux"


# ════════════════════════════════════════════════════════════════════
# Backend detection (lazy, cached)
# ════════════════════════════════════════════════════════════════════

_BACKEND: Optional[str] = None   # "pynput" | "pyautogui" | "xtst" | "win32"

def _detect_backend() -> str:
    global _BACKEND
    if _BACKEND:
        return _BACKEND
    try:
        import pynput.keyboard  # noqa
        _BACKEND = "pynput"
        logger.info("Key injector backend: pynput")
        return _BACKEND
    except ImportError:
        pass
    try:
        import pyautogui  # noqa
        _BACKEND = "pyautogui"
        logger.info("Key injector backend: pyautogui")
        return _BACKEND
    except ImportError:
        pass
    if _OS == "Linux":
        try:
            import ctypes, ctypes.util
            lib = ctypes.util.find_library("Xtst")
            if lib:
                ctypes.CDLL(lib)
                _BACKEND = "xtst"
                logger.info("Key injector backend: Xtst (ctypes)")
                return _BACKEND
        except Exception:
            pass
    if _OS == "Windows":
        try:
            import ctypes
            _BACKEND = "win32"
            logger.info("Key injector backend: Win32 SendInput")
            return _BACKEND
        except Exception:
            pass
    raise ImportError(
        "No key injection backend found.\n"
        "Install one of:\n"
        "  pip install pynput          (recommended, all platforms)\n"
        "  pip install pyautogui       (Windows/macOS/Linux-X11)\n"
        "On Linux without X11: install pynput and use a compatible compositor."
    )


# ════════════════════════════════════════════════════════════════════
# pynput backend
# ════════════════════════════════════════════════════════════════════

def _pynput_key(kd: KeyDef):
    """Resolve a KeyDef to a pynput Key or KeyCode."""
    from pynput.keyboard import Key, KeyCode
    pn = kd.pynput_name
    if pn:
        if hasattr(Key, pn):
            return getattr(Key, pn)
        try:
            return KeyCode.from_char(pn)
        except Exception:
            pass
    # Fall back to char from pyautogui name (single char)
    if kd.pyautogui and len(kd.pyautogui) == 1:
        return KeyCode.from_char(kd.pyautogui)
    return KeyCode.from_char(kd.label[0].lower()) if kd.label else None


_pynput_controller = None

def _get_pynput_ctrl():
    global _pynput_controller
    if _pynput_controller is None:
        from pynput.keyboard import Controller
        _pynput_controller = Controller()
    return _pynput_controller


def _pynput_press(kd: KeyDef):
    k = _pynput_key(kd)
    if k:
        _get_pynput_ctrl().press(k)
        _get_pynput_ctrl().release(k)


def _pynput_down(kd: KeyDef):
    k = _pynput_key(kd)
    if k:
        _get_pynput_ctrl().press(k)


def _pynput_up(kd: KeyDef):
    k = _pynput_key(kd)
    if k:
        _get_pynput_ctrl().release(k)


# ════════════════════════════════════════════════════════════════════
# pyautogui backend
# ════════════════════════════════════════════════════════════════════

def _pyautogui_press(kd: KeyDef):
    import pyautogui
    pyautogui.press(kd.pyautogui)


def _pyautogui_down(kd: KeyDef):
    import pyautogui
    pyautogui.keyDown(kd.pyautogui)


def _pyautogui_up(kd: KeyDef):
    import pyautogui
    pyautogui.keyUp(kd.pyautogui)


# ════════════════════════════════════════════════════════════════════
# Linux Xtst (ctypes) backend
# ════════════════════════════════════════════════════════════════════

_xtst_display = None
_Xtst = None
_X11  = None

def _init_xtst():
    global _xtst_display, _Xtst, _X11
    if _Xtst is not None:
        return
    import ctypes, ctypes.util
    _X11  = ctypes.CDLL(ctypes.util.find_library("X11"))
    _Xtst = ctypes.CDLL(ctypes.util.find_library("Xtst"))
    _X11.XOpenDisplay.restype = ctypes.c_void_p
    _xtst_display = _X11.XOpenDisplay(None)
    if not _xtst_display:
        raise RuntimeError("Cannot open X11 display")


def _xtst_keysym(kd: KeyDef) -> int:
    import ctypes
    _init_xtst()
    sym = kd.x11_keysym or kd.pyautogui or kd.label
    _X11.XStringToKeysym.restype = ctypes.c_ulong
    keysym = _X11.XStringToKeysym(sym.encode())
    if keysym == 0:
        # Try capitalised form (e.g. "Return", "space")
        keysym = _X11.XStringToKeysym(sym.capitalize().encode())
    return keysym


def _xtst_send(kd: KeyDef, is_press: bool):
    import ctypes
    _init_xtst()
    keysym = _xtst_keysym(kd)
    keycode = _X11.XKeysymToKeycode(_xtst_display, ctypes.c_ulong(keysym))
    _Xtst.XTestFakeKeyEvent(_xtst_display, keycode, ctypes.c_int(1 if is_press else 0),
                            ctypes.c_ulong(0))
    _X11.XFlush(_xtst_display)


def _xtst_press(kd: KeyDef):
    _xtst_send(kd, True)
    time.sleep(0.01)
    _xtst_send(kd, False)


def _xtst_down(kd: KeyDef): _xtst_send(kd, True)
def _xtst_up(kd: KeyDef):   _xtst_send(kd, False)


# ════════════════════════════════════════════════════════════════════
# Windows SendInput backend
# ════════════════════════════════════════════════════════════════════

def _win32_vk(kd: KeyDef) -> int:
    if kd.win_vk:
        return kd.win_vk
    # Single printable char
    if kd.pyautogui and len(kd.pyautogui) == 1:
        import ctypes
        return ctypes.windll.user32.VkKeyScanW(ord(kd.pyautogui)) & 0xFF
    return 0


def _win32_send(kd: KeyDef, is_keydown: bool):
    import ctypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk",         ctypes.c_ushort),
            ("wScan",       ctypes.c_ushort),
            ("dwFlags",     ctypes.c_ulong),
            ("time",        ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("_input",)
        _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]

    vk    = _win32_vk(kd)
    flags = 0 if is_keydown else 2   # KEYEVENTF_KEYUP = 2
    inp   = INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=flags))
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _win32_press(kd: KeyDef):
    _win32_send(kd, True)
    time.sleep(0.01)
    _win32_send(kd, False)


def _win32_down(kd: KeyDef): _win32_send(kd, True)
def _win32_up(kd: KeyDef):   _win32_send(kd, False)


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

_DISPATCH = {
    "pynput":   (_pynput_press,   _pynput_down,   _pynput_up),
    "pyautogui":(_pyautogui_press,_pyautogui_down,_pyautogui_up),
    "xtst":     (_xtst_press,     _xtst_down,     _xtst_up),
    "win32":    (_win32_press,    _win32_down,    _win32_up),
}


def press_key(kd: KeyDef) -> None:
    """Press and release a single key."""
    b = _detect_backend()
    _DISPATCH[b][0](kd)


def key_down(kd: KeyDef) -> None:
    """Hold a key down."""
    b = _detect_backend()
    _DISPATCH[b][1](kd)


def key_up(kd: KeyDef) -> None:
    """Release a held key."""
    b = _detect_backend()
    _DISPATCH[b][2](kd)


def press_combination(keys: list[KeyDef], hold_ms: int = 30) -> None:
    """
    Press a combination of keys simultaneously (e.g. Ctrl+Shift+Escape).
    All keys are held down together, then released in reverse order.

    Parameters
    ----------
    keys    : ordered list of KeyDef (modifiers first, main key last)
    hold_ms : how long (milliseconds) to hold all keys before releasing
    """
    if not keys:
        return
    b = _detect_backend()
    _, down_fn, up_fn = _DISPATCH[b]
    try:
        for kd in keys:
            down_fn(kd)
            time.sleep(0.005)         # tiny gap between each key-down
        time.sleep(hold_ms / 1000.0)  # hold
    finally:
        for kd in reversed(keys):
            up_fn(kd)
            time.sleep(0.005)
