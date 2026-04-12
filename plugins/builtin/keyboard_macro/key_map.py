"""
key_map.py — exhaustive key name → platform key code table.

Supports:
  Windows  : SendInput with virtual key codes (VK_*)
  Linux    : xdotool / evdev keysym names
  macOS    : Quartz CGEvent key codes

KEY_MAP  : canonical_name → {"win": vk, "linux": keysym, "mac": cg_code, "label": str}
KEY_GROUPS: ordered dict of group_name → [canonical_name, ...]  (for the UI)
ALIASES  : alternative spellings → canonical_name
"""
from __future__ import annotations
from typing import Dict, List, Optional

# ─── Individual key definitions ─────────────────────────────────────
#  win   = Windows Virtual Key code (int)
#  linux = xdotool/Xlib keysym name (str)
#  mac   = macOS CGKeyCode (int)   (-1 = unmapped)
#  label = human-readable display label

KEY_MAP: Dict[str, Dict] = {

    # ── Letters ─────────────────────────────────────────────────────
    "a": {"win": 0x41, "linux": "a",          "mac":  0,  "label": "A"},
    "b": {"win": 0x42, "linux": "b",          "mac": 11,  "label": "B"},
    "c": {"win": 0x43, "linux": "c",          "mac":  8,  "label": "C"},
    "d": {"win": 0x44, "linux": "d",          "mac":  2,  "label": "D"},
    "e": {"win": 0x45, "linux": "e",          "mac": 14,  "label": "E"},
    "f": {"win": 0x46, "linux": "f",          "mac":  3,  "label": "F"},
    "g": {"win": 0x47, "linux": "g",          "mac":  5,  "label": "G"},
    "h": {"win": 0x48, "linux": "h",          "mac":  4,  "label": "H"},
    "i": {"win": 0x49, "linux": "i",          "mac": 34,  "label": "I"},
    "j": {"win": 0x4A, "linux": "j",          "mac": 38,  "label": "J"},
    "k": {"win": 0x4B, "linux": "k",          "mac": 40,  "label": "K"},
    "l": {"win": 0x4C, "linux": "l",          "mac": 37,  "label": "L"},
    "m": {"win": 0x4D, "linux": "m",          "mac": 46,  "label": "M"},
    "n": {"win": 0x4E, "linux": "n",          "mac": 45,  "label": "N"},
    "o": {"win": 0x4F, "linux": "o",          "mac": 31,  "label": "O"},
    "p": {"win": 0x50, "linux": "p",          "mac": 35,  "label": "P"},
    "q": {"win": 0x51, "linux": "q",          "mac": 12,  "label": "Q"},
    "r": {"win": 0x52, "linux": "r",          "mac": 15,  "label": "R"},
    "s": {"win": 0x53, "linux": "s",          "mac":  1,  "label": "S"},
    "t": {"win": 0x54, "linux": "t",          "mac": 17,  "label": "T"},
    "u": {"win": 0x55, "linux": "u",          "mac": 32,  "label": "U"},
    "v": {"win": 0x56, "linux": "v",          "mac":  9,  "label": "V"},
    "w": {"win": 0x57, "linux": "w",          "mac": 13,  "label": "W"},
    "x": {"win": 0x58, "linux": "x",          "mac":  7,  "label": "X"},
    "y": {"win": 0x59, "linux": "y",          "mac": 16,  "label": "Y"},
    "z": {"win": 0x5A, "linux": "z",          "mac":  6,  "label": "Z"},

    # ── Digits ───────────────────────────────────────────────────────
    "0": {"win": 0x30, "linux": "0",          "mac": 29,  "label": "0"},
    "1": {"win": 0x31, "linux": "1",          "mac": 18,  "label": "1"},
    "2": {"win": 0x32, "linux": "2",          "mac": 19,  "label": "2"},
    "3": {"win": 0x33, "linux": "3",          "mac": 20,  "label": "3"},
    "4": {"win": 0x34, "linux": "4",          "mac": 21,  "label": "4"},
    "5": {"win": 0x35, "linux": "5",          "mac": 23,  "label": "5"},
    "6": {"win": 0x36, "linux": "6",          "mac": 22,  "label": "6"},
    "7": {"win": 0x37, "linux": "7",          "mac": 26,  "label": "7"},
    "8": {"win": 0x38, "linux": "8",          "mac": 28,  "label": "8"},
    "9": {"win": 0x39, "linux": "9",          "mac": 25,  "label": "9"},

    # ── Function keys F1–F24 ─────────────────────────────────────────
    "f1":  {"win": 0x70, "linux": "F1",  "mac": 122, "label": "F1"},
    "f2":  {"win": 0x71, "linux": "F2",  "mac": 120, "label": "F2"},
    "f3":  {"win": 0x72, "linux": "F3",  "mac":  99, "label": "F3"},
    "f4":  {"win": 0x73, "linux": "F4",  "mac": 118, "label": "F4"},
    "f5":  {"win": 0x74, "linux": "F5",  "mac":  96, "label": "F5"},
    "f6":  {"win": 0x75, "linux": "F6",  "mac":  97, "label": "F6"},
    "f7":  {"win": 0x76, "linux": "F7",  "mac":  98, "label": "F7"},
    "f8":  {"win": 0x77, "linux": "F8",  "mac": 100, "label": "F8"},
    "f9":  {"win": 0x78, "linux": "F9",  "mac": 101, "label": "F9"},
    "f10": {"win": 0x79, "linux": "F10", "mac": 109, "label": "F10"},
    "f11": {"win": 0x7A, "linux": "F11", "mac": 103, "label": "F11"},
    "f12": {"win": 0x7B, "linux": "F12", "mac": 111, "label": "F12"},
    "f13": {"win": 0x7C, "linux": "F13", "mac": 105, "label": "F13"},
    "f14": {"win": 0x7D, "linux": "F14", "mac": 107, "label": "F14"},
    "f15": {"win": 0x7E, "linux": "F15", "mac": 113, "label": "F15"},
    "f16": {"win": 0x7F, "linux": "F16", "mac": 106, "label": "F16"},
    "f17": {"win": 0x80, "linux": "F17", "mac":  64, "label": "F17"},
    "f18": {"win": 0x81, "linux": "F18", "mac":  79, "label": "F18"},
    "f19": {"win": 0x82, "linux": "F19", "mac":  80, "label": "F19"},
    "f20": {"win": 0x83, "linux": "F20", "mac":  90, "label": "F20"},
    "f21": {"win": 0x84, "linux": "F21", "mac":  -1, "label": "F21"},
    "f22": {"win": 0x85, "linux": "F22", "mac":  -1, "label": "F22"},
    "f23": {"win": 0x86, "linux": "F23", "mac":  -1, "label": "F23"},
    "f24": {"win": 0x87, "linux": "F24", "mac":  -1, "label": "F24"},

    # ── Modifiers ────────────────────────────────────────────────────
    "ctrl":        {"win": 0x11, "linux": "ctrl",        "mac": 59,  "label": "Ctrl"},
    "ctrl_left":   {"win": 0xA2, "linux": "ctrl_l",      "mac": 59,  "label": "Ctrl (L)"},
    "ctrl_right":  {"win": 0xA3, "linux": "ctrl_r",      "mac": 62,  "label": "Ctrl (R)"},
    "shift":       {"win": 0x10, "linux": "shift",       "mac": 56,  "label": "Shift"},
    "shift_left":  {"win": 0xA0, "linux": "shift_l",     "mac": 56,  "label": "Shift (L)"},
    "shift_right": {"win": 0xA1, "linux": "shift_r",     "mac": 60,  "label": "Shift (R)"},
    "alt":         {"win": 0x12, "linux": "alt",         "mac": 58,  "label": "Alt"},
    "alt_left":    {"win": 0xA4, "linux": "alt_l",       "mac": 58,  "label": "Alt (L)"},
    "alt_right":   {"win": 0xA5, "linux": "alt_r",       "mac": 61,  "label": "Alt Gr (R)"},
    "super":       {"win": 0x5B, "linux": "super",       "mac": 55,  "label": "Win / ⌘"},
    "super_right": {"win": 0x5C, "linux": "super_r",     "mac": 54,  "label": "Win (R) / ⌘"},
    "meta":        {"win": 0x5B, "linux": "meta",        "mac": 55,  "label": "Meta"},
    "hyper":       {"win": -1,   "linux": "hyper",       "mac": -1,  "label": "Hyper"},
    "menu":        {"win": 0x5D, "linux": "menu",        "mac": 110, "label": "Menu"},
    "caps_lock":   {"win": 0x14, "linux": "caps_lock",   "mac": 57,  "label": "Caps Lock"},
    "num_lock":    {"win": 0x90, "linux": "num_lock",    "mac": 71,  "label": "Num Lock"},
    "scroll_lock": {"win": 0x91, "linux": "scroll_lock", "mac": -1,  "label": "Scroll Lock"},

    # ── Navigation ───────────────────────────────────────────────────
    "up":          {"win": 0x26, "linux": "Up",        "mac": 126, "label": "↑"},
    "down":        {"win": 0x28, "linux": "Down",      "mac": 125, "label": "↓"},
    "left":        {"win": 0x25, "linux": "Left",      "mac": 123, "label": "←"},
    "right":       {"win": 0x27, "linux": "Right",     "mac": 124, "label": "→"},
    "home":        {"win": 0x24, "linux": "Home",      "mac": 115, "label": "Home"},
    "end":         {"win": 0x23, "linux": "End",       "mac": 119, "label": "End"},
    "page_up":     {"win": 0x21, "linux": "Page_Up",   "mac": 116, "label": "Page Up"},
    "page_down":   {"win": 0x22, "linux": "Page_Down", "mac": 121, "label": "Page Down"},
    "insert":      {"win": 0x2D, "linux": "Insert",    "mac": 114, "label": "Insert"},
    "delete":      {"win": 0x2E, "linux": "Delete",    "mac": 117, "label": "Delete"},

    # ── Editing ──────────────────────────────────────────────────────
    "enter":       {"win": 0x0D, "linux": "Return",    "mac": 36,  "label": "Enter"},
    "return":      {"win": 0x0D, "linux": "Return",    "mac": 36,  "label": "Return"},
    "escape":      {"win": 0x1B, "linux": "Escape",    "mac": 53,  "label": "Esc"},
    "backspace":   {"win": 0x08, "linux": "BackSpace",  "mac": 51,  "label": "Backspace"},
    "tab":         {"win": 0x09, "linux": "Tab",        "mac": 48,  "label": "Tab"},
    "space":       {"win": 0x20, "linux": "space",      "mac": 49,  "label": "Space"},
    "print_screen":{"win": 0x2C, "linux": "Print",      "mac": -1,  "label": "Print Screen"},
    "pause":       {"win": 0x13, "linux": "Pause",      "mac": -1,  "label": "Pause"},

    # ── Numpad ───────────────────────────────────────────────────────
    "num0": {"win": 0x60, "linux": "KP_0",       "mac": 82,  "label": "Num 0"},
    "num1": {"win": 0x61, "linux": "KP_1",       "mac": 83,  "label": "Num 1"},
    "num2": {"win": 0x62, "linux": "KP_2",       "mac": 84,  "label": "Num 2"},
    "num3": {"win": 0x63, "linux": "KP_3",       "mac": 85,  "label": "Num 3"},
    "num4": {"win": 0x64, "linux": "KP_4",       "mac": 86,  "label": "Num 4"},
    "num5": {"win": 0x65, "linux": "KP_5",       "mac": 87,  "label": "Num 5"},
    "num6": {"win": 0x66, "linux": "KP_6",       "mac": 88,  "label": "Num 6"},
    "num7": {"win": 0x67, "linux": "KP_7",       "mac": 89,  "label": "Num 7"},
    "num8": {"win": 0x68, "linux": "KP_8",       "mac": 91,  "label": "Num 8"},
    "num9": {"win": 0x69, "linux": "KP_9",       "mac": 92,  "label": "Num 9"},
    "num_add":      {"win": 0x6B, "linux": "KP_Add",      "mac": 69,  "label": "Num +"},
    "num_sub":      {"win": 0x6D, "linux": "KP_Subtract", "mac": 78,  "label": "Num −"},
    "num_mul":      {"win": 0x6A, "linux": "KP_Multiply", "mac": 67,  "label": "Num *"},
    "num_div":      {"win": 0x6F, "linux": "KP_Divide",   "mac": 75,  "label": "Num /"},
    "num_decimal":  {"win": 0x6E, "linux": "KP_Decimal",  "mac": 65,  "label": "Num ."},
    "num_enter":    {"win": 0x0D, "linux": "KP_Enter",    "mac": 76,  "label": "Num Enter"},

    # ── OEM / Punctuation ────────────────────────────────────────────
    "oem_1":        {"win": 0xBA, "linux": "semicolon",   "mac": 41,  "label": "; :  (OEM_1)"},
    "oem_2":        {"win": 0xBF, "linux": "slash",       "mac": 44,  "label": "/ ?  (OEM_2)"},
    "oem_3":        {"win": 0xC0, "linux": "grave",       "mac": 50,  "label": "` ~  (OEM_3)"},
    "oem_4":        {"win": 0xDB, "linux": "bracketleft", "mac": 33,  "label": "[ {  (OEM_4)"},
    "oem_5":        {"win": 0xDC, "linux": "backslash",   "mac": 42,  "label": r"\ |  (OEM_5)"},
    "oem_6":        {"win": 0xDD, "linux": "bracketright","mac": 30,  "label": "] }  (OEM_6)"},
    "oem_7":        {"win": 0xDE, "linux": "apostrophe",  "mac": 39,  "label": "' \"  (OEM_7)"},
    # oem_8 (VK 0xDF) is the key immediately left of Right-Shift on ISO keyboards.
    # On French AZERTY it produces ! (unshifted) and § (shifted).
    # Linux keysym "exclam" lets xdotool/Xlib resolve the correct physical key
    # on any X11 layout; "endonym" (the old value) is not a real keysym and
    # caused every oem_8 press to be silently dropped on Linux.
    "oem_8":        {"win": 0xDF, "linux": "exclam",      "mac": -1,  "label": "! §  (OEM_8)"},
    "oem_plus":     {"win": 0xBB, "linux": "equal",       "mac": 24,  "label": "= +  (OEM_Plus)"},
    "oem_minus":    {"win": 0xBD, "linux": "minus",       "mac": 27,  "label": "- _  (OEM_Minus)"},
    "oem_comma":    {"win": 0xBC, "linux": "comma",       "mac": 43,  "label": ", <  (OEM_Comma)"},
    "oem_period":   {"win": 0xBE, "linux": "period",      "mac": 47,  "label": ". >  (OEM_Period)"},
    "oem_102":      {"win": 0xE2, "linux": "less",        "mac": -1,  "label": "< >  (OEM_102)"},

    # ── Media keys ───────────────────────────────────────────────────
    "media_play_pause": {"win": 0xB3, "linux": "XF86AudioPlay",       "mac": -1, "label": "⏯ Play/Pause"},
    "media_next":       {"win": 0xB0, "linux": "XF86AudioNext",       "mac": -1, "label": "⏭ Next Track"},
    "media_prev":       {"win": 0xB1, "linux": "XF86AudioPrev",       "mac": -1, "label": "⏮ Prev Track"},
    "media_stop":       {"win": 0xB2, "linux": "XF86AudioStop",       "mac": -1, "label": "⏹ Stop"},
    "volume_up":        {"win": 0xAF, "linux": "XF86AudioRaiseVolume", "mac": -1, "label": "🔊 Vol Up"},
    "volume_down":      {"win": 0xAE, "linux": "XF86AudioLowerVolume", "mac": -1, "label": "🔉 Vol Down"},
    "volume_mute":      {"win": 0xAD, "linux": "XF86AudioMute",        "mac": -1, "label": "🔇 Mute"},
    "media_select":     {"win": 0xB5, "linux": "XF86AudioMedia",       "mac": -1, "label": "Media Select"},
    "browser_back":     {"win": 0xA6, "linux": "XF86Back",             "mac": -1, "label": "Browser Back"},
    "browser_forward":  {"win": 0xA7, "linux": "XF86Forward",          "mac": -1, "label": "Browser Forward"},
    "browser_refresh":  {"win": 0xA8, "linux": "XF86Reload",           "mac": -1, "label": "Browser Refresh"},
    "browser_home":     {"win": 0xAC, "linux": "XF86HomePage",         "mac": -1, "label": "Browser Home"},
    "browser_search":   {"win": 0xAA, "linux": "XF86Search",           "mac": -1, "label": "Browser Search"},
    "launch_mail":      {"win": 0xB4, "linux": "XF86Mail",             "mac": -1, "label": "Launch Mail"},
    "launch_calculator":{"win": 0xB7, "linux": "XF86Calculator",       "mac": -1, "label": "Calculator"},

    # ── Mouse buttons ────────────────────────────────────────────────
    "mouse_left":   {"win": 0x01, "linux": "pointer_button1", "mac": -1, "label": "Mouse Left"},
    "mouse_right":  {"win": 0x02, "linux": "pointer_button3", "mac": -1, "label": "Mouse Right"},
    "mouse_middle": {"win": 0x04, "linux": "pointer_button2", "mac": -1, "label": "Mouse Middle"},
    "mouse_x1":     {"win": 0x05, "linux": "pointer_button4", "mac": -1, "label": "Mouse X1"},
    "mouse_x2":     {"win": 0x06, "linux": "pointer_button5", "mac": -1, "label": "Mouse X2"},
}

# ─── Aliases (alternate spellings → canonical name) ──────────────────
ALIASES: Dict[str, str] = {
    "control":     "ctrl",
    "lctrl":       "ctrl_left",
    "rctrl":       "ctrl_right",
    "lshift":      "shift_left",
    "rshift":      "shift_right",
    "lalt":        "alt_left",
    "ralt":        "alt_right",
    "win":         "super",
    "windows":     "super",
    "cmd":         "super",
    "command":     "super",
    "option":      "alt",
    "esc":         "escape",
    "del":         "delete",
    "ins":         "insert",
    "pgup":        "page_up",
    "pgdn":        "page_down",
    "prtsc":       "print_screen",
    "numpad0":     "num0",
    "numpad1":     "num1",
    "numpad2":     "num2",
    "numpad3":     "num3",
    "numpad4":     "num4",
    "numpad5":     "num5",
    "numpad6":     "num6",
    "numpad7":     "num7",
    "numpad8":     "num8",
    "numpad9":     "num9",
    "numpad_add":  "num_add",
    "numpad_sub":  "num_sub",
    "numpad_mul":  "num_mul",
    "numpad_div":  "num_div",
    "numpad_enter":"num_enter",
    "numpad_dot":  "num_decimal",
    "semicolon":   "oem_1",
    "slash":       "oem_2",
    "backtick":    "oem_3",
    "grave":       "oem_3",
    "backslash":   "oem_5",
    "play":        "media_play_pause",
    "next_track":  "media_next",
    "prev_track":  "media_prev",
    "stop":        "media_stop",
    "vol_up":      "volume_up",
    "vol_down":    "volume_down",
    "mute":        "volume_mute",
    "bs":          "backspace",
    "bksp":        "backspace",
    "ret":         "return",
    "spc":         "space",
}

# ─── UI groups (for the web configurator dropdown) ───────────────────
KEY_GROUPS: Dict[str, List[str]] = {
    "Letters":        [c for c in "abcdefghijklmnopqrstuvwxyz"],
    "Digits":         [str(i) for i in range(10)],
    "Function Keys":  [f"f{i}" for i in range(1, 25)],
    "Modifiers":      ["ctrl","ctrl_left","ctrl_right","shift","shift_left",
                       "shift_right","alt","alt_left","alt_right","super",
                       "super_right","menu","caps_lock","num_lock","scroll_lock"],
    "Navigation":     ["up","down","left","right","home","end",
                       "page_up","page_down","insert","delete"],
    "Editing":        ["enter","escape","backspace","tab","space",
                       "print_screen","pause"],
    "Numpad":         ["num0","num1","num2","num3","num4","num5","num6",
                       "num7","num8","num9","num_add","num_sub","num_mul",
                       "num_div","num_decimal","num_enter"],
    "OEM / Punctuation": ["oem_1","oem_2","oem_3","oem_4","oem_5","oem_6",
                           "oem_7","oem_8","oem_plus","oem_minus","oem_comma",
                           "oem_period","oem_102"],
    "Media":          ["media_play_pause","media_next","media_prev","media_stop",
                       "volume_up","volume_down","volume_mute","media_select",
                       "browser_back","browser_forward","browser_refresh",
                       "browser_home","browser_search","launch_mail",
                       "launch_calculator"],
    "Mouse Buttons":  ["mouse_left","mouse_right","mouse_middle","mouse_x1","mouse_x2"],
}


def resolve(name: str) -> Optional[Dict]:
    """
    Resolve a key name (case-insensitive, alias-aware) to its entry in KEY_MAP.
    Returns None if unknown.
    """
    n = name.lower().strip()
    n = ALIASES.get(n, n)
    return KEY_MAP.get(n)


def all_key_names() -> List[str]:
    """Return all canonical key names, sorted."""
    return sorted(KEY_MAP.keys())


def label(name: str) -> str:
    """Return the display label for a key name."""
    entry = resolve(name)
    return entry["label"] if entry else name
