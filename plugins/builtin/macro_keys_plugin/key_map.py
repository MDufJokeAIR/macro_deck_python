"""
key_map.py  —  Exhaustive key name catalogue for MacroKeys plugin.

Every entry maps a human-readable label (shown in the UI) to:
  - a pyautogui key name   (used when pyautogui is available)
  - a pynput Key/KeyCode   (used when pynput is available)
  - an X11 keysym string   (used on Linux via Xtst fallback)
  - a Windows VK code      (used on Windows via ctypes fallback)

Groups
------
  LETTERS         a–z
  DIGITS          0–9 (main row)
  NUMPAD          numpad 0–9, operators, enter, decimal
  FUNCTION        F1–F24
  NAVIGATION      arrows, home, end, page up/down, insert, delete
  MODIFIERS       shift, ctrl, alt, meta/win, menu
  SPECIAL         space, tab, enter, escape, backspace, caps lock, print screen,
                  scroll lock, pause/break, num lock
  MEDIA           play/pause, stop, next, prev, mute, volume up/down
  BROWSER         browser back, forward, refresh, search, favorites, home
  OEM / PUNCTUATION  all standard punctuation + OEM_1 … OEM_102
  MOUSE_BUTTONS   left, right, middle (via pynput only)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class KeyDef:
    label: str                          # shown in UI
    group: str                          # category
    pyautogui: Optional[str] = None     # pyautogui key string
    pynput_name: Optional[str] = None   # pynput Key.name or vk int as str
    x11_keysym: Optional[str] = None    # XStringToKeysym name
    win_vk: Optional[int] = None        # Windows Virtual Key code
    description: str = ""


# ── helpers ─────────────────────────────────────────────────────────

def _k(label, group, pg=None, pn=None, x11=None, vk=None, desc="") -> KeyDef:
    return KeyDef(label=label, group=group, pyautogui=pg or label.lower(),
                  pynput_name=pn, x11_keysym=x11 or pg or label.lower(),
                  win_vk=vk, description=desc)


# ════════════════════════════════════════════════════════════════════
# KEY CATALOGUE
# ════════════════════════════════════════════════════════════════════

ALL_KEYS: list[KeyDef] = []

def _add(*keys): ALL_KEYS.extend(keys)


# ── Letters ──────────────────────────────────────────────────────────
_add(*[KeyDef(c, "Letters", pyautogui=c, pynput_name=c,
               x11_keysym=c, win_vk=ord(c.upper()))
       for c in "abcdefghijklmnopqrstuvwxyz"])

# ── Digits (main row) ─────────────────────────────────────────────
_add(*[KeyDef(str(d), "Digits", pyautogui=str(d), pynput_name=str(d),
               x11_keysym=str(d), win_vk=0x30 + d)
       for d in range(10)])

# ── Function keys F1–F24 ──────────────────────────────────────────
for n in range(1, 25):
    _add(KeyDef(f"F{n}", "Function",
                pyautogui=f"f{n}", pynput_name=f"f{n}",
                x11_keysym=f"F{n}", win_vk=0x6F + n))  # VK_F1=0x70

# ── Numpad ────────────────────────────────────────────────────────
_NUMPAD = [
    ("Numpad 0", "num0", "KP_0", 0x60),
    ("Numpad 1", "num1", "KP_1", 0x61),
    ("Numpad 2", "num2", "KP_2", 0x62),
    ("Numpad 3", "num3", "KP_3", 0x63),
    ("Numpad 4", "num4", "KP_4", 0x64),
    ("Numpad 5", "num5", "KP_5", 0x65),
    ("Numpad 6", "num6", "KP_6", 0x66),
    ("Numpad 7", "num7", "KP_7", 0x67),
    ("Numpad 8", "num8", "KP_8", 0x68),
    ("Numpad 9", "num9", "KP_9", 0x69),
    ("Numpad *", "multiply",   "KP_Multiply",  0x6A),
    ("Numpad +", "add",        "KP_Add",        0x6B),
    ("Numpad -", "subtract",   "KP_Subtract",   0x6D),
    ("Numpad .", "decimal",    "KP_Decimal",    0x6E),
    ("Numpad /", "divide",     "KP_Divide",     0x6F),
    ("Numpad Enter","enter",   "KP_Enter",      0x0D),
]
for label, pg, x11, vk in _NUMPAD:
    _add(KeyDef(label, "Numpad", pyautogui=pg, x11_keysym=x11, win_vk=vk))

# ── Navigation ────────────────────────────────────────────────────
_NAV = [
    ("Up",          "up",          "pynput:up",    "Up",          0x26),
    ("Down",        "down",        "pynput:down",  "Down",        0x28),
    ("Left",        "left",        "pynput:left",  "Left",        0x25),
    ("Right",       "right",       "pynput:right", "Right",       0x27),
    ("Home",        "home",        "pynput:home",  "Home",        0x24),
    ("End",         "end",         "pynput:end",   "End",         0x23),
    ("Page Up",     "pageup",      "pynput:page_up", "Prior",     0x21),
    ("Page Down",   "pagedown",    "pynput:page_down","Next",     0x22),
    ("Insert",      "insert",      "pynput:insert","Insert",      0x2D),
    ("Delete",      "delete",      "pynput:delete","Delete",      0x2E),
]
for label, pg, pn, x11, vk in _NAV:
    pn_clean = pn.replace("pynput:", "")
    _add(KeyDef(label, "Navigation", pyautogui=pg,
                pynput_name=pn_clean, x11_keysym=x11, win_vk=vk))

# ── Modifiers ─────────────────────────────────────────────────────
_MOD = [
    ("Left Shift",   "shiftleft",  "shift",    "Shift_L",       0xA0),
    ("Right Shift",  "shiftright", "shift_r",  "Shift_R",       0xA1),
    ("Left Ctrl",    "ctrlleft",   "ctrl",     "Control_L",     0xA2),
    ("Right Ctrl",   "ctrlright",  "ctrl_r",   "Control_R",     0xA3),
    ("Left Alt",     "altleft",    "alt",      "Alt_L",         0xA4),
    ("Right Alt",    "altright",   "alt_r",    "Alt_R",         0xA5),
    ("Left Win/⌘",   "winleft",    "cmd",      "Super_L",       0x5B),
    ("Right Win/⌘",  "winright",   "cmd_r",    "Super_R",       0x5C),
    ("Menu",         "apps",       "menu",     "Menu",          0x5D),
    ("Caps Lock",    "capslock",   "caps_lock","Caps_Lock",      0x14),
    ("Num Lock",     "numlock",    "num_lock", "Num_Lock",       0x90),
    ("Scroll Lock",  "scrolllock", "scroll_lock","Scroll_Lock", 0x91),
]
for label, pg, pn, x11, vk in _MOD:
    _add(KeyDef(label, "Modifiers", pyautogui=pg, pynput_name=pn,
                x11_keysym=x11, win_vk=vk))

# ── Special / Editing ─────────────────────────────────────────────
_SPECIAL = [
    ("Space",        "space",      "space",      "space",       0x20),
    ("Tab",          "tab",        "tab",        "Tab",         0x09),
    ("Enter",        "enter",      "enter",      "Return",      0x0D),
    ("Escape",       "escape",     "esc",        "Escape",      0x1B),
    ("Backspace",    "backspace",  "backspace",  "BackSpace",   0x08),
    ("Print Screen", "printscreen","print_screen","Print",      0x2C),
    ("Pause/Break",  "pause",      "pause",      "Pause",       0x13),
]
for label, pg, pn, x11, vk in _SPECIAL:
    _add(KeyDef(label, "Special", pyautogui=pg, pynput_name=pn,
                x11_keysym=x11, win_vk=vk))

# ── Media ─────────────────────────────────────────────────────────
_MEDIA = [
    ("Play/Pause",   "playpause",  "media_play_pause", "XF86AudioPlay",  0xB3),
    ("Stop",         "stop",       "media_stop",       "XF86AudioStop",  0xB2),
    ("Next Track",   "nexttrack",  "media_next",       "XF86AudioNext",  0xB0),
    ("Prev Track",   "prevtrack",  "media_previous",   "XF86AudioPrev",  0xB1),
    ("Mute",         "volumemute", "media_volume_mute","XF86AudioMute",  0xAD),
    ("Volume Up",    "volumeup",   "media_volume_up",  "XF86AudioRaiseVolume", 0xAF),
    ("Volume Down",  "volumedown", "media_volume_down","XF86AudioLowerVolume", 0xAE),
]
for label, pg, pn, x11, vk in _MEDIA:
    _add(KeyDef(label, "Media", pyautogui=pg, pynput_name=pn,
                x11_keysym=x11, win_vk=vk))

# ── Browser keys ──────────────────────────────────────────────────
_BROWSER = [
    ("Browser Back",      "browserback",     "XF86Back",       0xA6),
    ("Browser Forward",   "browserforward",  "XF86Forward",    0xA7),
    ("Browser Refresh",   "browserrefresh",  "XF86Refresh",    0xA8),
    ("Browser Stop",      "browserstop",     "XF86Stop",       0xA9),
    ("Browser Search",    "browsersearch",   "XF86Search",     0xAA),
    ("Browser Favorites", "browserfavorites","XF86Favorites",  0xAB),
    ("Browser Home",      "browserhome",     "XF86HomePage",   0xAC),
]
for label, pg, x11, vk in _BROWSER:
    _add(KeyDef(label, "Browser", pyautogui=pg, x11_keysym=x11, win_vk=vk))

# ── App/Launch ────────────────────────────────────────────────────
_APP = [
    ("Launch Mail",         "launchmail",    "XF86Mail",          0xB4),
    ("Launch Media Player", "launchmedia",   "XF86AudioMedia",    0xB5),
    ("Launch App 1",        "launchapp1",    "XF86Launch1",       0xB6),
    ("Launch App 2",        "launchapp2",    "XF86Launch2",       0xB7),
]
for label, pg, x11, vk in _APP:
    _add(KeyDef(label, "App Launch", pyautogui=pg, x11_keysym=x11, win_vk=vk))

# ── OEM / Punctuation ─────────────────────────────────────────────
_OEM = [
    (";",  "semicolon",  "semicolon",  "semicolon", 0xBA, "OEM_1"),
    ("=",  "=",          "equal",      "equal",     0xBB, "OEM_Plus"),
    (",",  ",",          "comma",      "comma",     0xBC, "OEM_Comma"),
    ("-",  "-",          "minus",      "minus",     0xBD, "OEM_Minus"),
    (".",  ".",          "period",     "period",    0xBE, "OEM_Period"),
    ("/",  "/",          "slash",      "slash",     0xBF, "OEM_2"),
    ("`",  "`",          "grave",      "grave",     0xC0, "OEM_3"),
    ("[",  "[",          "bracketleft","bracketleft",0xDB,"OEM_4"),
    ("\\", "\\",         "backslash",  "backslash", 0xDC, "OEM_5"),
    ("]",  "]",          "bracketright","bracketright",0xDD,"OEM_6"),
    ("'",  "'",          "apostrophe", "apostrophe",0xDE, "OEM_7"),
    ("OEM_8",  "oem8",   "oem8",       "oem8",      0xDF, "OEM_8"),
    ("OEM_102","oem102", "oem102",     "oem102",    0xE2, "OEM_102 (ISO)"),
]
for label, pg, pn, x11, vk, desc in _OEM:
    _add(KeyDef(label, "OEM / Punctuation", pyautogui=pg, pynput_name=pn,
                x11_keysym=x11, win_vk=vk, description=desc))

# ── Lookup helpers ────────────────────────────────────────────────

# label → KeyDef
BY_LABEL: dict[str, KeyDef] = {k.label: k for k in ALL_KEYS}

# group → [KeyDef]
BY_GROUP: dict[str, list[KeyDef]] = {}
for _kd in ALL_KEYS:
    BY_GROUP.setdefault(_kd.group, []).append(_kd)

GROUPS = list(BY_GROUP.keys())
