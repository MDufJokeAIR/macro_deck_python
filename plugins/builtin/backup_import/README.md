# Backup Import Plugin

> **Import Original MacroDeck App Backups into MacroDeck-Python**

This plugin enables you to import profiles, buttons, actions, and variables from the original MacroDeck App (Windows .NET version) into the MacroDeck-Python application.

## Features

✅ **Profiles**: Converts all profiles from the backup  
✅ **Buttons**: Migrates button positions, labels, icons, and colors  
✅ **Actions**: Translates plugin actions to the new action system  
✅ **Variables**: Imports all variables with their types  
✅ **Nested Folders**: Preserves folder hierarchy  
✅ **Batch Import**: Import entire backups in one command  

## Usage

### Basic Import

```bash
python -m macro_deck_python import-backup "path/to/backup/directory"
```

### Example

```bash
python -m macro_deck_python import-backup "C:\Users\matte\Downloads\backup_26-03-19_18-37-35"
```

### What Gets Imported

| Item | Status | Notes |
|------|--------|-------|
| Profiles | ✅ Full support | All profiles imported with structure |
| Buttons | ✅ Full support | Positions, labels, icons, colors preserved |
| Actions | ✅ Partial | Common actions converted; unknown types skipped |
| Variables | ✅ Full support | All variables imported with correct types |
| Folders | ✅ Full support | Nested folder hierarchy maintained |
| Custom Plugins | ⚠️ Requires mapping | Plugin action types need to be mapped |

## Supported Action Conversions

The plugin automatically converts the following action types:

| Original Action | Converted To | Details |
|-----------------|--------------|---------|
| `HotkeyAction` | `builtin.keyboard_macro.macro_short_press` | ✅ Converts VK codes (vk_k, vk_6, etc.) to key names; handles modifiers (meta→super) |
| `WriteTextAction` | `builtin.keyboard.type_text` | ✅ |
| `KeyPressAction` | `builtin.keyboard.key_press` | ✅ |
| `DelayAction` | `builtin.commands.delay` | ✅ |
| `SetProfileAction` | `builtin.commands.set_variable` | ✅ |
| `ToggleStateAction` | `builtin.commands.toggle_variable` | ✅ |
| `MediaPlayPauseAction` | `builtin.commands.run_command` | ✅ |
| `MediaNextTrackAction` | `builtin.commands.run_command` | ✅ |
| ***Other actions*** | Skipped | ⚠️ Unknown actions are preserved but not executed |

### HotkeyAction Conversion Examples

The Windows Utils `HotkeyAction` is converted to the keyboard_macro plugin format:

```
Old Format                    →  New Format
{"keys": "vk_k"}             →  {"keys": ["k"]}
{"keys": "meta+vk_6"}        →  {"keys": ["super", "6"]}
{"keys": "ctrl+shift+vk_c"}  →  {"keys": ["ctrl", "shift", "c"]}
{"keys": "alt+vk_f4"}        →  {"keys": ["alt", "f4"]}
```

VK Code Mapping Supported:
- **Letters**: vk_a through vk_z
- **Digits**: vk_0 through vk_9  
- **Function Keys**: vk_f1 through vk_f24
- **Navigation**: vk_up, vk_down, vk_left, vk_right, vk_home, vk_end, vk_prior, vk_next
- **Editing**: vk_return, vk_escape, vk_back, vk_tab, vk_space, vk_delete, vk_insert
- **Numpad**: vk_numpad0-9, vk_add, vk_subtract, vk_multiply, vk_divide, vk_decimal
- **Modifiers**: meta (→ super), ctrl, shift, alt

## Backup Structure

The plugin expects an unzipped backup directory with this structure:

```
backup_directory/
├── profiles.db        # SQLite database with profiles (JSON serialized)
├── variables.db       # SQLite database with variables
├── config.json        # Config file (imported for reference)
├── devices.json       # Device list (imported for reference)
├── credentials/       # Credentials folder (not imported)
├── configs/           # Plugin configs
├── iconpacks/         # Icon packs
└── plugins/           # Plugins (not imported)
```

## Import Details

### How Profiles Are Converted

1. **Source Format** (Original MacroDeck):
   - Profile stored as JSON string in `profiles.db` table `ProfileJson`
   - Buttons have: Position (X, Y), Icon, Color, Label, Actions array

2. **Target Format** (MacroDeck-Python):
   - Profile stored as dataclass + JSON in `~/.macro_deck/profiles.json`
   - Buttons have: Grid position, Program (list of blocks), Appearance

3. **Conversion Process**:
   - Parse JSON from SQLite database
   - Map button X/Y coordinates to grid row/col
   - Convert Actions to Program blocks
   - Apply styling from old button properties
   - Insert into ProfileManager

### How Variables Are Converted

Variables are imported with type mapping:

```
String / string  → VariableType.STRING
Integer / int    → VariableType.INTEGER
Float / float    → VariableType.FLOAT
Bool / bool      → VariableType.BOOL
```

### How Actions Are Converted

Each action is converted to a Block with:
- `plugin_id`: Mapped from the original action type
- `action_id`: Derived from the original action name
- `configuration`: JSON-formatted plugin-specific configuration

## Import Output

The import command shows a summary:

```
Starting import from c:\Users\matte\Downloads\backup_26-03-19_18-37-35...

✓ Import Complete!
  Profiles imported: 4
  Variables imported: 32
  Actions converted: 106

⚠ Warnings (2):
  - Failed to convert profile: ...
  - Failed to import variable xyz: ...
```

- **Profiles imported**: Number of successfully converted profiles
- **Variables imported**: Number of successfully imported variables
- **Actions converted**: Total number of button actions processed
- **Warnings**: Issues encountered during import (non-fatal)

## After Import

1. **Restart the server** to load the imported profiles:
   ```bash
   python -m macro_deck_python
   ```

2. **Access the PAD** at `http://localhost:8193` to verify

3. **Check variables** by looking at the Variables UI in the web config

4. **Verify actions** work by testing buttons on your clients

## Troubleshooting

### Import Fails with "Directory does not exist"
- Verify the backup path is correct
- Use absolute paths (e.g., `C:\Users\...`)
- Ensure the backup was unzipped

### No profiles imported
- Verify `profiles.db` exists in the backup directory
- Check that the database is not corrupted
- Look at warning messages for parsing errors

### Actions not working after import
- Some plugin actions may need configuration updates
- Check the action logs for unsupported action types
- Manually reconfigure complex actions in the web UI

### Variables not showing up
- Verify `variables.db` exists in the backup directory
- Check that variable names don't conflict with existing ones
- Look at warning messages for import errors

## API Reference

### BackupConverter Class

```python
from macro_deck_python.plugins.builtin.backup_import.main import BackupConverter

# Import a backup
results = BackupConverter.import_backup("path/to/backup")
# Returns: {
#   "profiles_imported": int,
#   "variables_imported": int,
#   "actions_converted": int,
#   "warnings": [str],
#   "errors": [str],
# }
```

## Configuration

The plugin is built-in and requires no configuration. It automatically:

- Detects the original MacroDeck backup format
- Maps action types to new plugin system
- Preserves profile hierarchy and button layout
- Imports all variables with correct types

## Limitations

- ❌ **Custom plugins**: Actions from custom plugins are skipped (need manual mapping)
- ❌ **Plugin dependencies**: Third-party plugins must be installed manually
- ❌ **Complex configurations**: Some advanced action configurations may need adjustment
- ⚠️ **Icon packs**: Icons are preserved by name; ensure icon packs are installed in the new app

## Future Enhancements

- [ ] Support for custom plugin action mapping
- [ ] Automatic icon pack detection
- [ ] Incremental imports (skip existing profiles)
- [ ] Profile merge options (combine with existing profiles)
- [ ] Export to original format

## License

Part of MacroDeck-Python. See main LICENSE file.
