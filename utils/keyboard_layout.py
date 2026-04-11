"""
keyboard_layout.py — Detect and manage keyboard layout configuration.

Provides functions to:
  1. Detect the current Windows keyboard layout
  2. Get the correct character mappings for the active layout
  3. Map characters to key combinations needed to produce them
"""
import ctypes
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger("utils.keyboard_layout")


# Character mappings for different layouts
# Maps characters to (key, shift_required) tuples
# key: physical key name (e.g., "key_comma", "key_slash")
# shift_required: whether shift modifier is needed
CHARACTER_MAPPINGS = {
    "QWERTY": {
        # Letters and numbers (no shift)
        "a": ("a", False),
        "b": ("b", False),
        "c": ("c", False),
        "d": ("d", False),
        "e": ("e", False),
        "f": ("f", False),
        "g": ("g", False),
        "h": ("h", False),
        "i": ("i", False),
        "j": ("j", False),
        "k": ("k", False),
        "l": ("l", False),
        "m": ("m", False),
        "n": ("n", False),
        "o": ("o", False),
        "p": ("p", False),
        "q": ("q", False),
        "r": ("r", False),
        "s": ("s", False),
        "t": ("t", False),
        "u": ("u", False),
        "v": ("v", False),
        "w": ("w", False),
        "x": ("x", False),
        "y": ("y", False),
        "z": ("z", False),
        "0": ("0", False),
        "1": ("1", False),
        "2": ("2", False),
        "3": ("3", False),
        "4": ("4", False),
        "5": ("5", False),
        "6": ("6", False),
        "7": ("7", False),
        "8": ("8", False),
        "9": ("9", False),
        # Symbols (unshifted)
        ",": ("oem_comma", False),
        ".": ("oem_period", False),
        "/": ("oem_2", False),
        ";": ("oem_1", False),
        "'": ("oem_7", False),
        "[": ("oem_4", False),
        "]": ("oem_6", False),
        "`": ("oem_3", False),
        "-": ("oem_minus", False),
        "=": ("oem_plus", False),
        "\\": ("oem_5", False),
        # Symbols (shifted)
        "!": ("1", True),
        "@": ("2", True),
        "#": ("3", True),
        "$": ("4", True),
        "%": ("5", True),
        "^": ("6", True),
        "&": ("7", True),
        "*": ("8", True),
        "(": ("9", True),
        ")": ("0", True),
        "<": ("oem_comma", True),
        ">": ("oem_period", True),
        "?": ("oem_2", True),
        ":": ("oem_1", True),
        '"': ("oem_7", True),
        "{": ("oem_4", True),
        "}": ("oem_6", True),
        "~": ("oem_3", True),
        "_": ("oem_minus", True),
        "+": ("oem_plus", True),
        "|": ("oem_5", True),
    },
    "AZERTY": {
        # AZERTY layout - French keyboard
        # Letters in their physical positions on AZERTY keyboards
        "a": ("q", False),
        "b": ("b", False),
        "c": ("c", False),
        "d": ("d", False),
        "e": ("e", False),
        "f": ("f", False),
        "g": ("g", False),
        "h": ("h", False),
        "i": ("i", False),
        "j": ("j", False),
        "k": ("k", False),
        "l": ("l", False),
        "m": ("m", False),  # m key - same position on AZERTY
        "n": ("n", False),
        "o": ("o", False),
        "p": ("p", False),
        "q": ("a", False),  # q moves to a position
        "r": ("r", False),
        "s": ("s", False),
        "t": ("t", False),
        "u": ("u", False),
        "v": ("v", False),
        "w": ("z", False),  # w moves to z position
        "x": ("x", False),
        "y": ("y", False),
        "z": ("w", False),  # z moves to w position
        # Shifted number keys produce the actual numbers on AZERTY
        "1": ("1", True),
        "2": ("2", True),
        "3": ("3", True),
        "4": ("4", True),
        "5": ("5", True),
        "6": ("6", True),
        "7": ("7", True),
        "8": ("8", True),
        "9": ("9", True),
        "0": ("0", True),
        "°": ("oem_4", True),               # Shift+) produces °
        "+": ("oem_plus", True),            # Shift+= produces +
        # On French AZERTY, symbols are unshifted and numbers are shifted!
        "²": ("oem_7", False), 
        "&": ("1", False),                  # Unshifted 1 produces &
        "é": ("2", False),                  # Unshifted 2 produces é
        '"': ("3", False),                  # Unshifted 3 produces "
        "'": ("4", False),                  # Unshifted 4 produces '
        "(": ("5", False),                  # Unshifted 5 produces (
        "-": ("6", False),                  # Unshifted 6 produces -
        "è": ("7", False),                  # Unshifted 7 produces è
        "_": ("8", False),                  # Unshifted 8 produces _
        "ç": ("9", False),                  # Unshifted 9 produces ç
        "à": ("0", False),                  # Unshifted 0 produces à
        ")": ("oem_4", False),              # Unshifted KEY RIGHT OF À produces )
        "=": ("oem_plus", False),           # Unshifted KEY RIGHT OF ) produces = 
        # AltGr combinations (3-tuple format: key, shift, altgr)
        "~": ("2", False, True),            # AltGr+2 
        "#": ("3", False, True),            # AltGr+3
        "{": ("4", False, True),            # AltGr+4 
        "[": ("5", False, True),            # AltGr+5 
        "|": ("6", False, True),            # AltGr+6 
        "`": ("7", False, True),            # AltGr+7 
        "\\": ("8", False, True),           # AltGr+8 
        "@": ("0", False, True),            # AltGr+0 
        "]": ("oem_4", False, True),        # AltGr+°
        "}": ("oem_plus", False, True),     # AltGr+= 
        # Other symbol keys on the keyboard
        # Keys to the right of P
        "^": ("oem_6", False),              # 1st KEY RIGHT OF P : circumflex
        "¨": ("oem_6", True),               # Shift + 1st KEY RIGHT OF P : diaeresis
        "$": ("oem_1", False),              # 2nd key right of P : dollar sign
        "£": ("oem_1", True),               # Shift + 2nd key right of P : Pound
        "¤": ("oem_1", False, True),        # AltGr + 2nd key right of P : Generic currency sign
        # Keys to the right of L
        "ù": ("oem_3", False),              # 1st KEY RIGHT OF M : ù
        "%": ("oem_3", True),               # Shift + 1st KEY RIGHT OF M : percent sign
        "*": ("oem_5", False),              # 2nd key right of M : asterisk
        "µ": ("oem_5", True),               # Shift + 2nd key right of M : µ
        # Keys to the right of N 
        ",": ("oem_comma", False),          # 1st right of N: comma key 
        "?": ("oem_comma", True),           # Shift + 1st right of N: question mark 
        ";": ("oem_period", False),         # 2nd right of N: semicolon 
        ".": ("oem_period", True),          # Shift + 2nd right of N: period 
        ":": ("oem_2", False),              # 3rd right of N: colon  
        "/": ("oem_2", True),               # Shift + 3rd right of N: forward slash
        # i do not know #"!": ("?", False),                  # 4th right of N: exclamation 
        # i do not know #"§": ("?", True),                   # Shift + 4th right of N: section sign
        # Key on the left of W
        "<": ("oem_102", False),            # 1st left of W: IntlBackslash key
        ">": ("oem_102", True),             # Shift + 1st left of W: IntlBackslash
        # More symbol keys ?
    },
    "QWERTZ": {
        # QWERTZ layout - German/Central European keyboard
        # Similar to QWERTY but with z and y swapped
        "a": ("a", False),
        "b": ("b", False),
        "c": ("c", False),
        "d": ("d", False),
        "e": ("e", False),
        "f": ("f", False),
        "g": ("g", False),
        "h": ("h", False),
        "i": ("i", False),
        "j": ("j", False),
        "k": ("k", False),
        "l": ("l", False),
        "m": ("m", False),
        "n": ("n", False),
        "o": ("o", False),
        "p": ("p", False),
        "q": ("q", False),
        "r": ("r", False),
        "s": ("s", False),
        "t": ("t", False),
        "u": ("u", False),
        "v": ("v", False),
        "w": ("w", False),
        "x": ("x", False),
        "y": ("z", False),  # y and z are swapped
        "z": ("y", False),
        "0": ("0", False),
        "1": ("1", False),
        "2": ("2", False),
        "3": ("3", False),
        "4": ("4", False),
        "5": ("5", False),
        "6": ("6", False),
        "7": ("7", False),
        "8": ("8", False),
        "9": ("9", False),
        ",": ("oem_comma", False),
        ".": ("oem_period", False),
        "/": ("oem_2", False),
    },
}



def detect_keyboard_layout() -> str:
    """
    Detect the current Windows keyboard layout.
    Returns: "QWERTY", "AZERTY", "QWERTZ", or "UNKNOWN"
    """
    try:
        # Get the active keyboard layout from Windows
        user32 = ctypes.windll.user32
        
        # Get the active window keyboard layout
        hwnd = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        layout_id = user32.GetKeyboardLayout(thread_id)
        
        # Extract the language code (low word)
        lang_code = layout_id & 0xFFFF
        
        # Map language codes to layout names
        # Common keyboard layout IDs:
        # 0x0409 = English (US) - QWERTY
        # 0x040C = French - AZERTY
        # 0x080C = French (Belgian) - AZERTY
        # 0x140C = French (Canadian) - QWERTY
        # 0x0407 = German - QWERTZ
        
        if lang_code == 0x0409:  # English US
            return "QWERTY"
        elif lang_code in [0x040C, 0x080C, 0x0C0C]:  # French layouts
            return "AZERTY"
        elif lang_code in [0x0407, 0x0807, 0x0C07]:  # German/Austrian/Swiss German
            return "QWERTZ"
        elif lang_code == 0x0410:  # Italian
            return "QWERTY"
        elif lang_code in [0x0809, 0x0C09, 0x1009, 0x1409]:  # English (UK, AU, CA, etc)
            return "QWERTY"
        else:
            logger.info(f"Unknown keyboard layout code: 0x{lang_code:04X}")
            return "UNKNOWN"
    except Exception as e:
        logger.error(f"Failed to detect keyboard layout: {e}")
        return "UNKNOWN"


def get_layout() -> str:
    """Get the currently detected keyboard layout."""
    return detect_keyboard_layout()


def get_key_for_char(ch: str, layout: Optional[str] = None) -> Optional[Tuple]:
    """
    Get the key and modifiers needed to produce a character on the current layout.
    
    Args:
        ch: Character to type
        layout: Keyboard layout (auto-detect if None)
    
    Returns:
        Tuple of (key_name, shift_required) or (key_name, shift_required, altgr_required)
        Example: ("key_slash", True) = press Shift+key_slash
        Example: ("key_2", False, True) = press AltGr+key_2
    """
    if layout is None:
        layout = get_layout()
    
    if layout not in CHARACTER_MAPPINGS:
        layout = "QWERTY"
    
    mappings = CHARACTER_MAPPINGS[layout]
    return mappings.get(ch)


def get_all_layouts() -> Dict[str, Dict[str, Tuple[str, bool]]]:
    """Get all available character mappings."""
    return CHARACTER_MAPPINGS


def get_current_layout_info() -> Dict:
    """Get detailed info about the current keyboard layout."""
    layout = get_layout()
    return {
        "layout": layout,
        "mappings": CHARACTER_MAPPINGS.get(layout, CHARACTER_MAPPINGS["QWERTY"]),
        "available_layouts": list(CHARACTER_MAPPINGS.keys()),
    }
