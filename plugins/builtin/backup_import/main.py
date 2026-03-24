"""
Main backup import plugin.
Provides CLI commands to import original MacroDeck backups into the Python version.
"""
import json
import sqlite3
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
import re

from macro_deck_python.models.profile import Profile, Folder
from macro_deck_python.models.action_button import ActionButton, Block
from macro_deck_python.models.variable import Variable, VariableType
from macro_deck_python.services.profile_manager import ProfileManager
from macro_deck_python.services.variable_manager import VariableManager


class BackupConverter:
    """Converts original MacroDeck backup format to Python app format."""
    
    _action_count = 0

    # VK code mapping - convert Windows virtual key names to keyboard_macro key names
    VK_CODE_MAP = {
        # Letters
        "vk_a": "a", "vk_b": "b", "vk_c": "c", "vk_d": "d", "vk_e": "e",
        "vk_f": "f", "vk_g": "g", "vk_h": "h", "vk_i": "i", "vk_j": "j",
        "vk_k": "k", "vk_l": "l", "vk_m": "m", "vk_n": "n", "vk_o": "o",
        "vk_p": "p", "vk_q": "q", "vk_r": "r", "vk_s": "s", "vk_t": "t",
        "vk_u": "u", "vk_v": "v", "vk_w": "w", "vk_x": "x", "vk_y": "y",
        "vk_z": "z",
        # Direct letter names (no vk_ prefix)
        "a": "a", "b": "b", "c": "c", "d": "d", "e": "e",
        "f": "f", "g": "g", "h": "h", "i": "i", "j": "j",
        "k": "k", "l": "l", "m": "m", "n": "n", "o": "o",
        "p": "p", "q": "q", "r": "r", "s": "s", "t": "t",
        "u": "u", "v": "v", "w": "w", "x": "x", "y": "y",
        "z": "z",
        
        # Digits
        "vk_0": "0", "vk_1": "1", "vk_2": "2", "vk_3": "3", "vk_4": "4",
        "vk_5": "5", "vk_6": "6", "vk_7": "7", "vk_8": "8", "vk_9": "9",
        "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
        "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
        
        # Function keys F1-F24
        "vk_f1": "f1", "vk_f2": "f2", "vk_f3": "f3", "vk_f4": "f4",
        "vk_f5": "f5", "vk_f6": "f6", "vk_f7": "f7", "vk_f8": "f8",
        "vk_f9": "f9", "vk_f10": "f10", "vk_f11": "f11", "vk_f12": "f12",
        "vk_f13": "f13", "vk_f14": "f14", "vk_f15": "f15", "vk_f16": "f16",
        "vk_f17": "f17", "vk_f18": "f18", "vk_f19": "f19", "vk_f20": "f20",
        "vk_f21": "f21", "vk_f22": "f22", "vk_f23": "f23", "vk_f24": "f24",
        # Direct F-key names
        "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
        "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
        "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
        "f13": "f13", "f14": "f14", "f15": "f15", "f16": "f16",
        "f17": "f17", "f18": "f18", "f19": "f19", "f20": "f20",
        "f21": "f21", "f22": "f22", "f23": "f23", "f24": "f24",
        
        # Modifiers (for reference, though usually parsed separately)
        "vk_control": "ctrl", "vk_lcontrol": "ctrl_left", "vk_rcontrol": "ctrl_right",
        "vk_shift": "shift", "vk_lshift": "shift_left", "vk_rshift": "shift_right",
        "vk_menu": "alt", "vk_lmenu": "alt_left", "vk_rmenu": "alt_right",
        "vk_lwin": "super", "vk_rwin": "super_right",
        
        # Navigation
        "vk_up": "up", "vk_down": "down", "vk_left": "left", "vk_right": "right",
        "vk_home": "home", "vk_end": "end", "vk_prior": "page_up", "vk_next": "page_down",
        "vk_pageup": "page_up", "vk_pagedown": "page_down",
        "up": "up", "down": "down", "left": "left", "right": "right",
        "home": "home", "end": "end", "pageup": "page_up", "pagedown": "page_down",
        "page_up": "page_up", "page_down": "page_down",
        
        # Editing
        "vk_return": "enter", "vk_enter": "enter", "vk_escape": "escape", "vk_esc": "escape",
        "vk_back": "backspace", "vk_backspace": "backspace", "vk_tab": "tab", 
        "vk_space": "space", "vk_delete": "delete", "vk_insert": "insert",
        "enter": "enter", "return": "enter", "escape": "escape", "esc": "escape",
        "backspace": "backspace", "back": "backspace", "tab": "tab", 
        "space": "space", "delete": "delete", "insert": "insert",
        
        # Numpad
        "vk_numpad0": "num0", "vk_numpad1": "num1", "vk_numpad2": "num2",
        "vk_numpad3": "num3", "vk_numpad4": "num4", "vk_numpad5": "num5",
        "vk_numpad6": "num6", "vk_numpad7": "num7", "vk_numpad8": "num8",
        "vk_numpad9": "num9", "vk_add": "num_add", "vk_subtract": "num_sub",
        "vk_multiply": "num_mul", "vk_divide": "num_div", "vk_decimal": "num_decimal",
        "numpad0": "num0", "numpad1": "num1", "numpad2": "num2",
        "numpad3": "num3", "numpad4": "num4", "numpad5": "num5",
        "numpad6": "num6", "numpad7": "num7", "numpad8": "num8",
        "numpad9": "num9", "add": "num_add", "subtract": "num_sub",
        "multiply": "num_mul", "divide": "num_div", "decimal": "num_decimal",
        
        # Special / System
        "vk_print": "print_screen", "vk_printscreen": "print_screen",
        "vk_pause": "pause", "vk_break": "pause",
        "vk_apps": "menu", "vk_context": "menu",
        "vk_capslock": "caps_lock", "vk_numlock": "num_lock", 
        "vk_scrolllock": "scroll_lock", "vk_scroll": "scroll_lock",
        "print": "print_screen", "printscreen": "print_screen", "prtsc": "print_screen",
        "pause": "pause", "break": "pause",
        "apps": "menu", "context": "menu", "menu": "menu",
        "capslock": "caps_lock", "caps": "caps_lock",
        "numlock": "num_lock", "scrolllock": "scroll_lock", "scroll": "scroll_lock",
        
        # OEM keys (common ones)
        "vk_oem_1": "oem_1", "oem_1": "oem_1",     # ; :
        "vk_oem_plus": "oem_plus", "oem_plus": "oem_plus",     # = +
        "vk_oem_comma": "oem_comma", "oem_comma": "oem_comma",   # , <
        "vk_oem_minus": "oem_minus", "oem_minus": "oem_minus",   # - _
        "vk_oem_period": "oem_period", "oem_period": "oem_period", # . >
        "vk_oem_2": "oem_2", "oem_2": "oem_2",     # / ?
        "vk_oem_3": "oem_3", "oem_3": "oem_3",     # ` ~
        "vk_oem_4": "oem_4", "oem_4": "oem_4",     # [ {
        "vk_oem_5": "oem_5", "oem_5": "oem_5",     # \ |
        "vk_oem_6": "oem_6", "oem_6": "oem_6",     # ] }
        "vk_oem_7": "oem_7", "oem_7": "oem_7",     # ' "
        "vk_oem_8": "oem_8", "oem_8": "oem_8",     # OEM specific
        "vk_oem_102": "oem_102", "oem_102": "oem_102", # < > on non-US keyboards
    }

    # Mapping of old action types to new plugin IDs
    ACTION_TYPE_MAPPING = {
        # Windows keyboard actions (old WindowsUtils plugin)
        "SuchByte.WindowsUtils.Actions.HotkeyAction": ("builtin.keyboard_macro", "macro_short_press"),
        "SuchByte.WindowsUtils.Actions.WriteTextAction": ("builtin.keyboard", "type_text"),
        "SuchByte.WindowsUtils.Actions.KeyPressAction": ("builtin.keyboard", "key_press"),
        
        # Delay action (old ActionButton plugin)
        "SuchByte.MacroDeck.ActionButton.Plugin.DelayAction": ("builtin.commands", "delay"),
        
        # Variable control (old ActionButton plugin - toggle state)
        "SuchByte.MacroDeck.ActionButton.ActionButtonToggleStateAction, Macro Deck 2": ("builtin.commands", "toggle_variable"),
        "SuchByte.MacroDeck.ActionButton.ActionButtonToggleStateAction": ("builtin.commands", "toggle_variable"),
        
        # Button state control (old ActionButton plugin - set state on/off)
        "SuchByte.MacroDeck.ActionButton.ActionButtonSetStateOnAction, Macro Deck 2": ("builtin.commands", "set_variable"),
        "SuchByte.MacroDeck.ActionButton.ActionButtonSetStateOnAction": ("builtin.commands", "set_variable"),
        "SuchByte.MacroDeck.ActionButton.ActionButtonSetStateOffAction, Macro Deck 2": ("builtin.commands", "set_variable"),
        "SuchByte.MacroDeck.ActionButton.ActionButtonSetStateOffAction": ("builtin.commands", "set_variable"),
        
        # Variable value modification (old Variables plugin - set/increment/decrement)
        "SuchByte.MacroDeck.Variables.Plugin.ChangeVariableValueAction": ("builtin.commands", "set_variable"),
        
        # Profile switching - map to the new switch_profile action
        "SuchByte.MacroDeck.InternalPlugins.DevicePlugin.Actions.SetProfileAction, Macro Deck 2": ("builtin.commands", "switch_profile"),
        
        # Media controls (old MediaControls plugin)
        "MediaControls_Plugin.MediaPlayPauseAction": ("builtin.commands", "run_command"),
        "MediaControls_Plugin.MediaNextTrackAction": ("builtin.commands", "run_command"),
        "MediaControls_Plugin.MediaPreviousTrackAction": ("builtin.commands", "run_command"),
        "MediaControls_Plugin.MediaStopAction": ("builtin.commands", "run_command"),
        "MediaControls_Plugin.MediaVolumeUpAction": ("builtin.commands", "run_command"),
        "MediaControls_Plugin.MediaVolumeDownAction": ("builtin.commands", "run_command"),
    }

    @staticmethod
    def _rgb_to_hex(rgb_str: str) -> str:
        """Convert 'R, G, B' format to '#RRGGBB' hex format."""
        try:
            if isinstance(rgb_str, str):
                # Handle "R, G, B" format
                parts = [int(x.strip()) for x in rgb_str.split(',')]
                if len(parts) == 3:
                    return f"#{parts[0]:02x}{parts[1]:02x}{parts[2]:02x}"
        except (ValueError, AttributeError):
            pass
        
        # Already hex or invalid, return as-is
        if rgb_str and rgb_str.startswith('#'):
            return rgb_str
        
        # Default to black if unparseable
        return "#000000"

    @staticmethod
    def _normalize_color(color_str: str) -> str:
        """Normalize color to hex format."""
        if not color_str:
            return "#FFFFFF"
        
        # Map of named colors from .NET
        named_colors = {
            "black": "#000000",
            "white": "#FFFFFF",
            "red": "#FF0000",
            "green": "#00FF00",
            "blue": "#0000FF",
            "yellow": "#FFFF00",
            "cyan": "#00FFFF",
            "magenta": "#FF00FF",
            "gray": "#808080",
            "grey": "#808080",
            "lightgray": "#D3D3D3",
            "lightgrey": "#D3D3D3",
            "darkgray": "#A9A9A9",
            "darkgrey": "#A9A9A9",
            "orange": "#FFA500",
            "purple": "#800080",
            "brown": "#A52A2A",
            "pink": "#FFC0CB",
            "lime": "#00FF00",
            "navy": "#000080",
            "teal": "#008080",
            "gold": "#FFD700",
            "silver": "#C0C0C0",
            "maroon": "#800000",
            "olive": "#808000",
            "coral": "#FF7F50",
            "khaki": "#F0E68C",
            "salmon": "#FA8072",
            "turquoise": "#40E0D0",
            "violet": "#EE82EE",
            "transparent": "#FFFFFF",
        }
        
        # Check for named color
        color_lower = color_str.lower().strip()
        if color_lower in named_colors:
            return named_colors[color_lower]
        
        # Try RGB format conversion
        if "," in color_str:
            return BackupConverter._rgb_to_hex(color_str)
        
        # Already hex?
        if color_str.startswith("#"):
            return color_str
        
        # Default to black for unparseable colors
        return "#000000"

    @staticmethod
    def _convert_windows_utils_hotkey(vk_string: str) -> List[str]:
        """
        Convert Windows Utils hotkey format to keyboard_macro key list.
        
        Examples:
            "vk_k" → ["k"]
            "meta+vk_6" → ["super", "6"]
            "ctrl+shift+vk_c" → ["ctrl", "shift", "c"]
            "alt+vk_f4" → ["alt", "f4"]
            "vk_rshift+vk_lmenu+vk_c" → ["shift_right", "alt_left", "c"]
        """
        if not vk_string:
            return []
        
        # Normalize to lowercase
        vk_string = vk_string.strip().lower()
        
        # Split by + to get individual parts (modifiers and key)
        parts = vk_string.split("+")
        keys = []
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            part_lower = part.lower()
            
            # Handle modifiers (non-VK format, for backward compat)
            if part_lower == "meta":
                keys.append("super")
            elif part_lower in ["ctrl", "shift", "alt"]:
                keys.append(part_lower)
            elif part_lower in ["lctrl", "left_ctrl", "ctrl_left", "ctrl_l"]:
                keys.append("ctrl_left")
            elif part_lower in ["rctrl", "right_ctrl", "ctrl_right", "ctrl_r"]:
                keys.append("ctrl_right")
            elif part_lower in ["lshift", "left_shift", "shift_left", "shift_l"]:
                keys.append("shift_left")
            elif part_lower in ["rshift", "right_shift", "shift_right", "shift_r"]:
                keys.append("shift_right")
            elif part_lower in ["lalt", "left_alt", "alt_left", "alt_l"]:
                keys.append("alt_left")
            elif part_lower in ["ralt", "right_alt", "alt_right", "alt_r"]:
                keys.append("alt_right")
            else:
                # Try to look up in VK_CODE_MAP (handles both vk_xxx and direct names)
                if part_lower in BackupConverter.VK_CODE_MAP:
                    keys.append(BackupConverter.VK_CODE_MAP[part_lower])
                elif part.startswith("vk_"):
                    # If VK format but not found, strip vk_ prefix and use the rest
                    key_name = part[3:].lower()
                    keys.append(key_name)
                else:
                    # Direct key name - use as-is (already lowercased)
                    keys.append(part_lower)
        
        return keys

    @staticmethod
    def import_backup(backup_path: str) -> Dict[str, Any]:
        """
        Import a backup from a directory.
        
        Args:
            backup_path: Path to unzipped backup directory
            
        Returns:
            Dict with import statistics and results
        """
        BackupConverter._action_count = 0  # Reset counter
        
        results = {
            "profiles_imported": 0,
            "imported_profiles": [],  # List of {id, name} dicts
            "variables_imported": 0,
            "imported_variables": [],  # List of variable names
            "actions_converted": 0,
            "warnings": [],
            "errors": [],
        }

        # Validate backup path
        backup_path = Path(backup_path)
        if not backup_path.is_dir():
            results["errors"].append(f"Backup path does not exist: {backup_path}")
            return results

        # Import profiles
        profiles_db = backup_path / "profiles.db"
        if profiles_db.exists():
            try:
                profile_results = BackupConverter._import_profiles(profiles_db)
                results["profiles_imported"] = profile_results["count"]
                results["imported_profiles"] = profile_results.get("profiles", [])
                results["warnings"].extend(profile_results["warnings"])
            except Exception as e:
                results["errors"].append(f"Failed to import profiles: {e}")

        # Get action count
        results["actions_converted"] = BackupConverter._action_count

        # Import variables
        variables_db = backup_path / "variables.db"
        if variables_db.exists():
            try:
                var_results = BackupConverter._import_variables(variables_db)
                results["variables_imported"] = var_results["count"]
                results["imported_variables"] = var_results.get("variables", [])
                results["warnings"].extend(var_results["warnings"])
            except Exception as e:
                results["errors"].append(f"Failed to import variables: {e}")

        return results

    @staticmethod
    def _import_profiles(db_path: Path) -> Dict[str, Any]:
        """Import profiles from the old SQLite database."""
        results = {"count": 0, "profiles": [], "warnings": []}

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT JsonString FROM ProfileJson")
            rows = cursor.fetchall()

            for row in rows:
                try:
                    old_profile = json.loads(row[0])
                    new_profile = BackupConverter._convert_profile(old_profile)
                    
                    # Add to ProfileManager
                    ProfileManager._profiles[new_profile.profile_id] = new_profile
                    results["count"] += 1
                    # Track the imported profile
                    results["profiles"].append({
                        "id": new_profile.profile_id,
                        "name": new_profile.name
                    })
                    
                    # Create variables for all button state bindings
                    try:
                        BackupConverter._create_button_variables(new_profile)
                    except Exception as e:
                        # Log but don't fail the profile import if variable creation fails
                        results["warnings"].append(f"Warning: Could not create button variables: {e}")
                    
                except Exception as e:
                    results["warnings"].append(f"Failed to convert profile: {e}")
            
            # Save after importing all profiles and variables
            ProfileManager.save()
            VariableManager.save()

        finally:
            conn.close()

        return results

    @staticmethod
    def _create_button_variables(profile: Profile) -> None:
        """Create variables for all button state bindings in a profile."""
        def _iterate_buttons(folder: Folder) -> None:
            """Recursively iterate through all buttons in folder and subfolders."""
            # Check all buttons in this folder
            for key, btn in folder.buttons.items():
                if not btn or not isinstance(btn, ActionButton):
                    continue
                    
                # If button doesn't have state_binding yet, generate one from position
                if not hasattr(btn, 'state_binding') or not btn.state_binding:
                    try:
                        row, col = map(int, key.split('_'))
                        btn.state_binding = f"Profile{profile.name}_x{col}y{row}"
                    except (ValueError, AttributeError, TypeError):
                        continue
                
                # Create the button's state variable as a Boolean
                if btn.state_binding:
                    VariableManager.set_value(
                        name=btn.state_binding,
                        value="false",
                        vtype=VariableType.BOOL,
                        plugin_id=None,
                        save=False
                    )
            
            # Recursively process subfolders
            for subfolder in folder.sub_folders:
                _iterate_buttons(subfolder)
        
        # Start from the root folder and create all button variables
        if profile and hasattr(profile, 'folder'):
            _iterate_buttons(profile.folder)

    @staticmethod
    def _convert_profile(old_profile: dict) -> Profile:
        """Convert old profile format to new format."""
        profile_id = old_profile.get("ProfileId", "")
        name = old_profile.get("DisplayName", "Imported Profile")

        # Create root folder, passing profile name for variable naming
        root_folder = BackupConverter._convert_folder(old_profile.get("Folders", [{}])[0], name)

        profile = Profile(profile_id=profile_id, name=name, folder=root_folder)
        return profile

    @staticmethod
    def _convert_folder(old_folder: dict, profile_name: str = "") -> Folder:
        """Convert old folder format to new format.
        
        Args:
            old_folder: The old folder dictionary
            profile_name: The parent profile name for generating button variable names
        """
        folder_id = old_folder.get("FolderId", "")
        name = old_folder.get("DisplayName", "Main")
        
        folder = Folder(folder_id=folder_id, name=name)

        # Convert buttons
        old_buttons = old_folder.get("ActionButtons", [])
        for old_btn in old_buttons:
            try:
                # Position buttons in grid
                # Note: X/Y notation where x=column, y=row
                col = old_btn.get("Position_X", 0)  # X from old app → col
                row = old_btn.get("Position_Y", 0)  # Y from old app → row
                new_btn = BackupConverter._convert_button(old_btn, row, col, profile_name)
                if new_btn:
                    folder.set_button(row, col, new_btn)
            except Exception as e:
                continue  # Skip problematic buttons

        # Convert child folders
        for child_folder_data in old_folder.get("Childs", []):
            child_folder = BackupConverter._convert_folder(child_folder_data, profile_name)
            folder.sub_folders.append(child_folder)

        return folder

    @staticmethod
    def _convert_button(old_button: dict, row: int = 0, col: int = 0, profile_name: str = "") -> Optional[ActionButton]:
        """Convert old button format to new format.
        
        Args:
            old_button: The old button dictionary
            row: Button row position
            col: Button column position
            profile_name: Parent profile name for generating variable names
        """
        button_id = old_button.get("Guid", "")
        
        button = ActionButton(button_id=button_id)

        # Generate auto-variable name for this button first
        # Pattern: Profile{profile_name}_x{col}y{row} (e.g., ProfileSC_x3y2)
        button_var = f"Profile{profile_name}_x{col}y{row}"
        
        # Bind button to its state variable by default
        button.state_binding = button_var

        # Get OFF and ON state data
        label_off_data = old_button.get("LabelOff", {})
        label_on_data = old_button.get("LabelOn", {})
        
        # Set button's default label from OFF state
        if label_off_data and label_off_data.get("LabelText"):
            button.label = label_off_data.get("LabelText")
            button.label_color = BackupConverter._normalize_color(
                label_off_data.get("LabelColor", "White")
            )
        bg_color_off = old_button.get("BackColorOff", "")
        bg_color_on = old_button.get("BackColorOn", "")
        icon_off = old_button.get("IconOff", "")
        icon_on = old_button.get("IconOn", "")
        
        # Set button's default appearance
        if bg_color_off:
            button.background_color = BackupConverter._normalize_color(bg_color_off)
        if icon_off:
            button.icon = icon_off
        
        # Check if button has both ON and OFF states (different values)
        has_dual_states = (
            bg_color_off and bg_color_on and bg_color_off != bg_color_on
        ) or (
            icon_off and icon_on and icon_off != icon_on
        )

        if has_dual_states:
            # Create IF block to handle state-dependent styling using the button's variable
            if_block = Block(
                type="if",
                variable_name=button_var,
                operator="==",
                compare_value="True",  # Use Python's str(True) format, not JSON "true"
            )
            
            # ON state (true condition) - when button is in ON state
            if bg_color_on or icon_on or label_on_data.get("LabelText"):
                on_style = Block(type="style")
                if label_on_data and label_on_data.get("LabelText"):
                    on_style.label = label_on_data.get("LabelText")
                    on_style.label_color = BackupConverter._normalize_color(
                        label_on_data.get("LabelColor", "White")
                    )
                if bg_color_on:
                    on_style.background_color = BackupConverter._normalize_color(bg_color_on)
                if icon_on:
                    on_style.icon = icon_on
                if any([on_style.label, on_style.label_color, on_style.background_color, on_style.icon]):
                    if_block.then_blocks.append(on_style)
            
            # OFF state (false condition) - when button is in OFF state
            if bg_color_off or icon_off or label_off_data.get("LabelText"):
                off_style = Block(type="style")
                if label_off_data and label_off_data.get("LabelText"):
                    off_style.label = label_off_data.get("LabelText")
                    off_style.label_color = BackupConverter._normalize_color(
                        label_off_data.get("LabelColor", "White")
                    )
                if bg_color_off:
                    off_style.background_color = BackupConverter._normalize_color(bg_color_off)
                if icon_off:
                    off_style.icon = icon_off
                if any([off_style.label, off_style.label_color, off_style.background_color, off_style.icon]):
                    if_block.else_blocks.append(off_style)
            
            button.program.append(if_block)
        else:
            # Single state - just use OFF state colors
            # Convert label
            if label_off_data and label_off_data.get("LabelText"):
                label_color = label_off_data.get("LabelColor", "White")
                label_color = BackupConverter._normalize_color(label_color)
                button.program.append(Block(
                    type="style",
                    label=label_off_data.get("LabelText"),
                    label_color=label_color,
                ))

            # Convert background color
            if bg_color_off:
                bg_color = BackupConverter._normalize_color(bg_color_off)
                button.program.append(Block(
                    type="style",
                    background_color=bg_color,
                ))

            # Convert icon
            if icon_off:
                button.program.append(Block(
                    type="style",
                    icon=icon_off,
                ))

        # Convert actions, passing the button variable for state actions
        old_actions = old_button.get("Actions", [])
        has_condition_action = False
        has_explicit_toggle = False
        set_variable_actions = {}  # Track external variable setters
        
        for old_action in old_actions:
            try:
                action_type = old_action.get("$type", "")
                
                # Track if we have ConditionActions (complex buttons)
                if "ConditionAction" in action_type:
                    has_condition_action = True
                
                # Track if there's an explicit toggle already
                if "ToggleStateAction" in action_type:
                    has_explicit_toggle = True
                
                # Track set_variable actions to create reactive IF conditions later
                if "ChangeVariableValueAction" in action_type:
                    config = old_action.get("Configuration", "{}")
                    try:
                        if isinstance(config, str):
                            config_dict = json.loads(config)
                        else:
                            config_dict = config if isinstance(config, dict) else {}
                        
                        # The old format uses "variable" and "value" keys
                        var_name = config_dict.get("variable", "")
                        var_value = config_dict.get("value", "")
                        
                        if var_name and var_value:
                            set_variable_actions[var_name] = var_value
                    except:
                        pass
                
                action_block = BackupConverter._convert_action(
                    old_action, 
                    button_var,
                    bg_color_on=bg_color_on,
                    bg_color_off=bg_color_off,
                    label_on_data=label_on_data,
                    label_off_data=label_off_data,
                    icon_on=icon_on,
                    icon_off=icon_off,
                )
                if action_block:
                    button.program.append(action_block)
                    BackupConverter._action_count += 1
            except Exception as e:
                continue  # Skip problematic actions
        
        # For complex buttons with conditions but no explicit toggle,
        # add a toggle to complete the state cycle
        if has_condition_action and not has_explicit_toggle and button_var:
            button.program.append(Block(
                type="action",
                plugin_id="builtin.commands",
                action_id="toggle_variable",
                configuration=json.dumps({"variable_name": button_var}),
                configuration_summary=f"Toggle {button_var}",
            ))
        
        # Add reactive IF conditions for buttons that set external variables
        # This makes buttons light up when their controlled variable matches their value
        # (e.g., Scanning button lights up when mode == "Scan" or mode == "Guns")
        # Use ON state colors if available, otherwise use default off color
        if set_variable_actions:
            for ext_var_name, ext_var_value in set_variable_actions.items():
                # Only create reactive conditions for variables that aren't the button's own state
                if ext_var_name != button_var:
                    # Create IF block: if variable equals the value this button sets
                    if_block = Block(
                        type="if",
                        variable_name=ext_var_name,
                        operator="==",
                        compare_value=str(ext_var_value),
                    )
                    
                    # Apply highlighting style in THEN block
                    # Use ON color if available, otherwise use a slightly different shade
                    on_style = Block(type="style")
                    if label_on_data and label_on_data.get("LabelText"):
                        on_style.label = label_on_data.get("LabelText")
                    if label_on_data and label_on_data.get("LabelColor"):
                        on_style.label_color = BackupConverter._normalize_color(label_on_data.get("LabelColor", "White"))
                    
                    # Use ON color if different from OFF, otherwise use a lighter shade
                    if bg_color_on and bg_color_on != bg_color_off:
                        on_style.background_color = BackupConverter._normalize_color(bg_color_on)
                    elif bg_color_off:
                        # If on/off colors are the same, lighten it to show it's active
                        # Convert to RGB, increase brightness, convert back
                        try:
                            r = int(bg_color_off[1:3], 16)
                            g = int(bg_color_off[3:5], 16)
                            b = int(bg_color_off[5:7], 16)
                            # Increase brightness by 30%
                            r = min(255, int(r * 1.3))
                            g = min(255, int(g * 1.3))
                            b = min(255, int(b * 1.3))
                            on_style.background_color = f"#{r:02x}{g:02x}{b:02x}"
                        except:
                            on_style.background_color = button.background_color
                    
                    if icon_on and icon_on != icon_off:
                        on_style.icon = icon_on
                    
                    if_block.then_blocks.append(on_style)
                    button.program.append(if_block)

        return button if button.program else None

    @staticmethod
    def _convert_action(
        old_action: dict, 
        button_var: str = "",
        bg_color_on: str = "",
        bg_color_off: str = "",
        label_on_data: dict = None,
        label_off_data: dict = None,
        icon_on: str = "",
        icon_off: str = "",
    ) -> Optional[Block]:
        """Convert old action format to new block format.
        
        Args:
            old_action: The old action dictionary to convert
            button_var: Optional button variable name for state actions (e.g., "_button_2_3")
            bg_color_on: Button's ON state background color
            bg_color_off: Button's OFF state background color
            label_on_data: Button's ON state label data
            label_off_data: Button's OFF state label data
            icon_on: Button's ON state icon
            icon_off: Button's OFF state icon
        """
        if label_on_data is None:
            label_on_data = {}
        if label_off_data is None:
            label_off_data = {}
        
        action_type = old_action.get("$type", "")
        name = old_action.get("Name", "")
        config = old_action.get("Configuration", "{}")

        # Handle ConditionAction (IF blocks)
        if "ConditionAction" in action_type:
            return BackupConverter._convert_condition_action(
                old_action, 
                button_var,
                bg_color_on=bg_color_on,
                bg_color_off=bg_color_off,
                label_on_data=label_on_data,
                label_off_data=label_off_data,
                icon_on=icon_on,
                icon_off=icon_off,
            )

        # Handle ActionButtonSetBackgroundColorAction - convert to STYLE block
        if "ActionButtonSetBackgroundColorAction" in action_type:
            try:
                if isinstance(config, str):
                    config_dict = json.loads(config.replace("\\r\\n", "").replace("\\", "")) if config else {}
                else:
                    config_dict = config if isinstance(config, dict) else {}
                
                color_hex = config_dict.get("ColorHex", "#000000")
                color_hex = BackupConverter._normalize_color(color_hex)
                
                return Block(
                    type="style",
                    background_color=color_hex,
                )
            except:
                return None  # Skip if conversion fails

        # Map action type - try exact match first, then substring match for Windows Utils actions
        if action_type in BackupConverter.ACTION_TYPE_MAPPING:
            plugin_id, action_id = BackupConverter.ACTION_TYPE_MAPPING[action_type]
        elif "ChangeVariableValueAction" in action_type:
            # Variable value modification - map to set_variable
            plugin_id, action_id = "builtin.commands", "set_variable"
        elif "ActionButtonSetStateOnAction" in action_type:
            # Button state ON - map to set_variable
            plugin_id, action_id = "builtin.commands", "set_variable"
        elif "ActionButtonSetStateOffAction" in action_type:
            # Button state OFF - map to set_variable
            plugin_id, action_id = "builtin.commands", "set_variable"
        elif "HotkeyAction" in action_type:
            # Windows Utils hotkey - map to keyboard_macro
            plugin_id, action_id = "builtin.keyboard_macro", "macro_short_press"
        elif "WriteTextAction" in action_type or "TypeTextAction" in action_type:
            # Text input action - map to keyboard type_text
            plugin_id, action_id = "builtin.keyboard", "type_text"
        elif "KeyPressAction" in action_type:
            # Single key press - map to keyboard key_press
            plugin_id, action_id = "builtin.keyboard", "key_press"
        elif "DelayAction" in action_type:
            # Delay action
            plugin_id, action_id = "builtin.commands", "delay"
        else:
            # Fallback for unknown actions
            plugin_id, action_id = "unknown", action_type.split(".")[-1] if action_type else "unknown"

        # Parse configuration
        try:
            if isinstance(config, str):
                # Special handling for DelayAction - configuration is just a milliseconds number
                if "DelayAction" in action_type:
                    try:
                        config_dict = {"ms": int(config)}
                    except (ValueError, TypeError):
                        config_dict = {"ms": 500}
                else:
                    # Clean up escaped JSON
                    config = config.replace("\\r\\n", "").replace("\\", "")
                    config_dict = json.loads(config) if config else {}
            else:
                config_dict = config if isinstance(config, dict) else {}
        except:
            config_dict = {}

        # Convert configuration to new format based on action type
        new_config = BackupConverter._convert_action_config(
            action_type, config_dict, button_var
        )

        # Generate a human-readable summary for specific action types
        summary = old_action.get("ConfigurationSummary", name)
        if "HotkeyAction" in action_type and new_config.get("keys"):
            # Create a human-readable summary for keyboard shortcuts
            keys_list = new_config.get("keys", [])
            summary = " + ".join(keys_list) if isinstance(keys_list, list) else str(keys_list)

        block = Block(
            type="action",
            plugin_id=plugin_id,
            action_id=action_id,
            configuration=json.dumps(new_config),
            configuration_summary=summary,
        )

        return block

    @staticmethod
    def _convert_action_config(action_type: str, old_config: dict, button_var: str = "") -> dict:
        """Convert action-specific configuration to new plugin format.
        
        Args:
            action_type: The action type string
            old_config: The old configuration dictionary
            button_var: Optional button variable name for state actions (e.g., "_button_2_3")
        """
        if "HotkeyAction" in action_type:
            # Convert Windows Utils hotkey format to keyboard_macro format
            # Old format: {"keys": "vk_k"} or {"keys": "meta+vk_6"} or {"key": "...", "ctrl": "...", etc}
            # New format: {"keys": [...], "tap_ms": 50} for macro_short_press action
            
            # Check if new format (keys string)
            if "keys" in old_config:
                keys_str = old_config.get("keys", "").strip()
                if keys_str:
                    keys_list = BackupConverter._convert_windows_utils_hotkey(keys_str)
                    # Always export regardless of whether keys were parsed
                    return {"keys": keys_list, "tap_ms": 50}
            
            # Check if old format (separate fields: key, ctrl, shift, alt, lwin)
            # Also support left/right specific modifiers: lctrl, rctrl, lshift, rshift, lalt, ralt
            key = old_config.get("key", "").strip().lower()
            keys_list = []
            
            # Track if we found any left/right specific modifiers
            has_specific_modifiers = False
            
            # Check for left/right specific modifiers first
            if old_config.get("lctrl") == "True" or old_config.get("lctrl") is True or \
               old_config.get("left_ctrl") == "True" or old_config.get("left_ctrl") is True:
                keys_list.append("ctrl_left")
                has_specific_modifiers = True
            if old_config.get("rctrl") == "True" or old_config.get("rctrl") is True or \
               old_config.get("right_ctrl") == "True" or old_config.get("right_ctrl") is True:
                keys_list.append("ctrl_right")
                has_specific_modifiers = True
            
            if old_config.get("lshift") == "True" or old_config.get("lshift") is True or \
               old_config.get("left_shift") == "True" or old_config.get("left_shift") is True:
                keys_list.append("shift_left")
                has_specific_modifiers = True
            if old_config.get("rshift") == "True" or old_config.get("rshift") is True or \
               old_config.get("right_shift") == "True" or old_config.get("right_shift") is True:
                keys_list.append("shift_right")
                has_specific_modifiers = True
            
            if old_config.get("lalt") == "True" or old_config.get("lalt") is True or \
               old_config.get("left_alt") == "True" or old_config.get("left_alt") is True:
                keys_list.append("alt_left")
                has_specific_modifiers = True
            if old_config.get("ralt") == "True" or old_config.get("ralt") is True or \
               old_config.get("right_alt") == "True" or old_config.get("right_alt") is True:
                keys_list.append("alt_right")
                has_specific_modifiers = True
            
            # Only check generic modifiers if no specific left/right variants were found
            if not has_specific_modifiers:
                if old_config.get("ctrl") == "True" or old_config.get("ctrl") is True:
                    keys_list.append("ctrl")
                if old_config.get("shift") == "True" or old_config.get("shift") is True:
                    keys_list.append("shift")
                if old_config.get("alt") == "True" or old_config.get("alt") is True:
                    keys_list.append("alt")
            
            if old_config.get("lwin") == "True" or old_config.get("lwin") is True or \
               old_config.get("meta") == "True" or old_config.get("meta") is True:
                keys_list.append("super")
            
            if key:
                # Convert key - try VK_CODE_MAP first (handles both vk_xxx and direct names)
                key_lower = key.lower()
                mapped_key = BackupConverter.VK_CODE_MAP.get(key_lower)
                if mapped_key:
                    key = mapped_key
                elif key.startswith("vk_"):
                    # If not found but is VK format, strip vk_ prefix
                    key = key[3:].lower()
                keys_list.append(key)
            
            # Always return keys configuration, even if empty (don't filter out)
            return {"keys": keys_list, "tap_ms": 50}
            
        elif "WriteTextAction" in action_type or "TypeTextAction" in action_type:
            # Convert old text action to new type_text format
            text = old_config.get("text", "")
            interval = float(old_config.get("interval", 0.03))
            return {"text": text, "interval": interval}
            
        elif "KeyPressAction" in action_type:
            # Single key press
            key = old_config.get("key", "").strip().lower()
            return {"key": key}
            
        elif "DelayAction" in action_type:
            # Convert delay in milliseconds
            try:
                delay_ms = int(old_config.get("ms", old_config.get("Configuration", 500)))
            except (ValueError, TypeError):
                delay_ms = 500
            return {"milliseconds": delay_ms}
            
        elif "SetProfileAction" in action_type:
            # Profile switching - convert to switch_profile action
            # The ProfileId from the backup is preserved during import
            profile_id = old_config.get("ProfileId", "")
            return {"profile_id": profile_id}
            
        elif "MediaPlayPauseAction" in action_type:
            # Map to run_command with media action
            return {"command": "nircmd.exe mediaplay"}
        elif "MediaNextTrackAction" in action_type:
            return {"command": "nircmd.exe medianext"}
        elif "MediaPreviousTrackAction" in action_type:
            return {"command": "nircmd.exe mediaprev"}
        elif "MediaStopAction" in action_type:
            return {"command": "nircmd.exe mediastop"}
        elif "MediaVolumeUpAction" in action_type:
            return {"command": "nircmd.exe changesysvolume 5000"}
        elif "MediaVolumeDownAction" in action_type:
            return {"command": "nircmd.exe changesysvolume -5000"}
            
        elif "ChangeVariableValueAction" in action_type:
            # Convert variable modification action
            # Configuration format: {"method":"set", "variable":"var_name", "value":"new_value"}
            method = old_config.get("method", "set").lower()
            variable_name = old_config.get("variable", "")
            value = str(old_config.get("value", ""))
            
            # Detect type from value if possible
            var_type = "String"
            if value.lower() in ["true", "false"]:
                var_type = "Bool"
            elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                var_type = "Integer"
            elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
                var_type = "Float"
            
            return {
                "variable_name": variable_name,
                "value": value,
                "type": var_type
            }
            
        elif "ActionButtonSetStateOnAction" in action_type:
            # Set button state to ON using set_variable action
            # Use the button's own variable to control its appearance
            var_name = button_var if button_var else "button_state"
            return {
                "variable_name": var_name,
                "value": "true",
                "type": "Bool"
            }
            
        elif "ActionButtonSetStateOffAction" in action_type:
            # Set button state to OFF using set_variable action
            # Use the button's own variable to control its appearance
            var_name = button_var if button_var else "button_state"
            return {
                "variable_name": var_name,
                "value": "false",
                "type": "Bool"
            }
            
        elif "ActionButtonToggleStateAction" in action_type:
            # Toggle button state using toggle_variable action
            # Use the button's own variable to control its appearance
            var_name = button_var if button_var else "button_state"
            return {
                "variable_name": var_name
            }
            
        else:
            return old_config

    @staticmethod
    @staticmethod
    def _convert_condition_action(
        old_condition: dict, 
        button_var: str = "",
        bg_color_on: str = "",
        bg_color_off: str = "",
        label_on_data: dict = None,
        label_off_data: dict = None,
        icon_on: str = "",
        icon_off: str = "",
    ) -> Optional[Block]:
        """Convert old ConditionAction to new IF block format.
        
        Args:
            old_condition: The old condition action dictionary
            button_var: Optional button variable name for state actions
            bg_color_on: Button's ON state background color for automatic styling
            bg_color_off: Button's OFF state background color for automatic styling
            label_on_data: Button's ON state label data for automatic styling
            label_off_data: Button's OFF state label data for automatic styling
            icon_on: Button's ON state icon for automatic styling
            icon_off: Button's OFF state icon for automatic styling
        """
        if label_on_data is None:
            label_on_data = {}
        if label_off_data is None:
            label_off_data = {}
        
        # Extract condition details from root level
        variable_name = old_condition.get("ConditionValue1Source", "").strip()
        condition_type = old_condition.get("ConditionType", 0)
        condition_value = old_condition.get("ConditionValue2", "")
        
        # Track if this is a button state condition (empty variable name)
        is_button_state_condition = not variable_name or variable_name == "_state" or variable_name == "state"
        
        # If the condition variable is checking the button state (e.g., "_state" or empty),
        # replace it with the button's actual variable name
        if is_button_state_condition:
            variable_name = button_var
            # Convert "On"/"Off" to "True"/"False" for boolean variable comparison
            if isinstance(condition_value, str):
                condition_value = condition_value.strip()
                if condition_value.lower() == "on":
                    condition_value = "True"
                elif condition_value.lower() == "off":
                    condition_value = "False"
        else:
            # Normalize condition_value for non-state conditions too
            if isinstance(condition_value, str):
                condition_value = condition_value.strip()
                # Normalize lowercase true/false to Python format
                if condition_value.lower() == "true":
                    condition_value = "True"
                elif condition_value.lower() == "false":
                    condition_value = "False"
        
        # Map ConditionType to operator (0 = equals, others need research)
        # Based on observed data: 0 = "==", 1 = unknown (likely !=)
        operator = "==" if condition_type == 0 else "!="
        
        # Extract true/false branches
        actions_list = old_condition.get("Actions", [])
        actions_else = old_condition.get("ActionsElse", [])
        
        # Convert nested actions to blocks, passing button_var
        then_blocks = []
        for action in actions_list:
            action_block = BackupConverter._convert_action(
                action, 
                button_var,
                bg_color_on=bg_color_on,
                bg_color_off=bg_color_off,
                label_on_data=label_on_data,
                label_off_data=label_off_data,
                icon_on=icon_on,
                icon_off=icon_off,
            )
            if action_block:
                then_blocks.append(action_block)
        
        else_blocks = []
        for action in actions_else:
            action_block = BackupConverter._convert_action(
                action, 
                button_var,
                bg_color_on=bg_color_on,
                bg_color_off=bg_color_off,
                label_on_data=label_on_data,
                label_off_data=label_off_data,
                icon_on=icon_on,
                icon_off=icon_off,
            )
            if action_block:
                else_blocks.append(action_block)
        
        # Add automatic styling if no STYLE blocks exist in then/else
        # This makes conditional buttons react visually by showing colors when condition is met
        has_then_style = any(b.type == "style" for b in then_blocks)
        has_else_style = any(b.type == "style" for b in else_blocks)
        
        if not has_then_style and (bg_color_on or label_on_data):
            # Add ON state styling to THEN block
            then_style = Block(type="style")
            if label_on_data and label_on_data.get("LabelText"):
                then_style.label = label_on_data.get("LabelText")
            if label_on_data and label_on_data.get("LabelColor"):
                then_style.label_color = BackupConverter._normalize_color(label_on_data.get("LabelColor", "White"))
            if bg_color_on:
                then_style.background_color = BackupConverter._normalize_color(bg_color_on)
            if icon_on:
                then_style.icon = icon_on
            then_blocks.insert(0, then_style)
        
        if not has_else_style and (bg_color_off or label_off_data):
            # Add OFF state styling to ELSE block
            else_style = Block(type="style")
            if label_off_data and label_off_data.get("LabelText"):
                else_style.label = label_off_data.get("LabelText")
            if label_off_data and label_off_data.get("LabelColor"):
                else_style.label_color = BackupConverter._normalize_color(label_off_data.get("LabelColor", "White"))
            if bg_color_off:
                else_style.background_color = BackupConverter._normalize_color(bg_color_off)
            if icon_off:
                else_style.icon = icon_off
            else_blocks.insert(0, else_style)
        
        # Create IF block with conditions list instead of top-level fields
        if_block = Block(
            type="if",
            variable_name=variable_name,  # Set at top-level for UI display/compat
            operator=operator,
            compare_value=condition_value,
            conditions=[{
                "variable_name": variable_name,
                "operator": operator,
                "compare_value": condition_value,
                "logic": "AND",
            }],
            then_blocks=then_blocks,
            else_blocks=else_blocks,
        )
        
        return if_block

    @staticmethod
    def _import_variables(db_path: Path) -> Dict[str, Any]:
        """Import variables from the old SQLite database."""
        results = {"count": 0, "variables": [], "warnings": []}

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT Name, Value, Type FROM Variable")
            rows = cursor.fetchall()

            for name, value, var_type in rows:
                try:
                    # Map old type to new type
                    if var_type in ["String", "string"]:
                        var_type_enum = VariableType.STRING
                    elif var_type in ["Integer", "int"]:
                        var_type_enum = VariableType.INTEGER
                    elif var_type in ["Float", "float"]:
                        var_type_enum = VariableType.FLOAT
                    elif var_type in ["Bool", "bool"]:
                        var_type_enum = VariableType.BOOL
                    else:
                        var_type_enum = VariableType.STRING

                    # Create and save variable
                    VariableManager.set_value(
                        name=name,
                        value=value,
                        vtype=var_type_enum,
                        plugin_id=None,
                        save=True
                    )
                    results["count"] += 1
                    results["variables"].append(name)

                except Exception as e:
                    results["warnings"].append(f"Failed to import variable {name}: {e}")

        finally:
            conn.close()

        return results


# Plugin main class
from macro_deck_python.sdk import PluginBase


class Main(PluginBase):
    """Backup import plugin - provides CLI command and REST API endpoint for importing MacroDeck backups."""
    package_id = "builtin.backup_import"
    name = "Backup Import"
    version = "1.0.0"
    author = "MacroDeck"
    description = "Import original MacroDeck backups into MacroDeck-Python"
    can_configure = False

    def enable(self) -> None:
        super().enable()
        # No actions exposed - this plugin provides CLI commands and REST API
        self.log_info(f"Backup import plugin enabled - use 'import-backup' CLI command or /api/backup/import endpoint")


def import_backup_command(backup_path: str) -> None:
    """CLI command to import a backup."""
    print(f"Starting import from {backup_path}...")
    
    results = BackupConverter.import_backup(backup_path)
    
    print(f"\n✓ Import Complete!")
    print(f"  Profiles imported: {results['profiles_imported']}")
    print(f"  Variables imported: {results['variables_imported']}")
    print(f"  Actions converted: {results['actions_converted']}")
    
    if results["warnings"]:
        print(f"\n⚠ Warnings ({len(results['warnings'])}):")
        for warning in results["warnings"][:5]:
            print(f"  - {warning}")
        if len(results["warnings"]) > 5:
            print(f"  ... and {len(results['warnings']) - 5} more")
    
    if results["errors"]:
        print(f"\n✗ Errors ({len(results['errors'])}):")
        for error in results["errors"]:
            print(f"  - {error}")
