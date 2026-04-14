# Macro Deck — Python Rewrite

A full Python port of [Macro Deck](https://github.com/Macro-Deck-App/Macro-Deck).  
Turns any phone, tablet, or Raspberry Pi browser into a programmable macro pad.

---

## Quick Start

### Windows (PowerShell)

```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install websockets aiohttp cryptography psutil

# Run
python -m macro_deck_python

# Create a new plugin
python -m macro_deck_python new-plugin "My Plugin" --id me.myplugin
```

> **Note:** If you get an execution policy error, run this once before activating:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Linux / macOS (Bash)

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install websockets aiohttp cryptography psutil

# Run
python3 -m macro_deck_python

# Create a new plugin
python3 -m macro_deck_python new-plugin "My Plugin" --id me.myplugin
```

**Open on Raspberry Pi / phone / tablet:**
```
http://<server-ip>:8192        ← button pad  (auto-connects)
http://<server-ip>:8192/admin  ← admin panel
```

WebSocket server listens on `ws://<server-ip>:8191`.

---

## Architecture

```
macro_deck_python/
├── __main__.py                  # Entry-point (start server / new-plugin CLI)
├── core/config_manager.py       # App settings  ~/.macro_deck/config.json
│
├── models/
│   ├── variable.py              # Variable + VariableType
│   ├── action_button.py         # ActionButton (button_type, slider_config, actions, conditions)
│   └── profile.py               # Profile → Folder → {buttons, sliders, sub_folders}
│
├── plugins/
│   ├── base.py                  # IMacroDeckPlugin, PluginAction, PluginConfiguration,
│   │                            #   PluginCredentials (Fernet-encrypted)
│   ├── plugin_manager.py        # Dynamic loader, requirements.txt auto-install, unload
│   └── builtin/
│       ├── keyboard_plugin/     # Hotkey / TypeText / KeyPress  (pyautogui)
│       ├── keyboard_macro/      # 1-5 key macros: short/long/double/hold/sequence
│       │                        #   key_map.py (146 keys: F1-F24, OEM, media, numpad…)
│       │                        #   injector.py (6 backends: SendInput/Quartz/xdotool/
│       │                        #                Xlib/evdev/pyautogui)
│       ├── commands_plugin/     # RunCommand, OpenURL, Delay, ToggleVariable, SetVariable
│       ├── system_variables/    # CPU%, RAM%, time, date (psutil)
│       ├── obs_plugin/          # OBS WebSocket: stream/record/scene/source/volume
│       └── analog_slider/       # Vertical slider replacing N button cells in a column
│           ├── main.py          # SliderConfig, SliderState, SliderRegistry, actions
│           ├── analog_output.py # VariableOutput, KeyboardThresholdOutput
│           └── registry.py      # Stable singleton (survives hot-reload)
│
├── sdk/
│   ├── __init__.py              # Public API: PluginBase, ActionBase, @action, helpers
│   ├── plugin_base.py           # PluginBase (decorator + class style)
│   ├── decorators.py            # @action, @on_load, @on_delete
│   └── api.py                   # set_variable, get_config, set_credentials, log_*
│
├── services/
│   ├── variable_manager.py      # Thread-safe CRUD, persistence, change callbacks
│   ├── profile_manager.py       # Profile CRUD, per-client routing
│   ├── action_executor.py       # Background thread pipeline (conditions → actions)
│   ├── hot_reload.py            # Poll plugins dir, reload changed plugins (~2 s)
│   ├── icon_manager.py          # Content-addressable PNG store, LRU cache, base64
│   ├── extension_store.py       # Download/install/uninstall from extension store
│   └── update_service.py        # GitHub release update checker
│
├── websocket/
│   ├── protocol.py              # JSON encode/decode, message reference
│   └── server.py                # asyncio server, plugin_message_hooks, CORS origins=None
│
├── gui/
│   ├── pad_client.py            # Full single-file browser button-pad HTML/JS
│   ├── web_config.py            # aiohttp REST API + CORS middleware + admin SPA
│   └── tray.py                  # System tray (pystray + Pillow)
│
├── utils/
│   ├── template.py              # {variable} and {var:.2f} label rendering
│   ├── condition.py             # Condition evaluator  (== != > < >= <=)
│   ├── folder_utils.py          # BFS folder search
│   └── logger.py                # MacroDeckLogger (Trace/Info/Warning/Error)
│
├── cli/scaffold.py              # `new-plugin` scaffolding command
└── tests/                       # 351 unit + integration tests (100% pass)
```

---

## Launchers

Pre-configured launch scripts for quick server startup:

### Windows (`launchers/run.bat`)
Double-click to start the server with the virtual environment.
```batch
@echo off
cd /d "%~dp0"
.\venv\Scripts\python.exe -m macro_deck_python %*
```

### Linux (`launchers/MacroDeck.desktop`)
Desktop entry for quick launch from the application menu on Raspberry Pi / server.
Edit the URL and port to match your server IP:
```
[Desktop Entry]
Type=Application
Name=MacroDeck
Exec=/usr/bin/chromium --password-store=basic --start-maximized -app=http://192.168.1.100:8191
Icon=web-browser
Terminal=false
```

---

## Recent Updates

### Auto-fit Font Size (Label Scaling)

Button labels now support intelligent, responsive font sizing:

- **Auto-fit mode** (default for new buttons): Font size scales proportionally with the button cell size, making text readable on any screen (phone, tablet, desktop). Words are laid one per line, and overflow is prevented via automatic capping.
- **Explicit size mode**: Set a fixed pixel size (px) for direct control.

Toggle between modes in the editor's **Style panel** → **Font size** → **Auto-fit to button** checkbox.

**How it works:**
- Auto-fit computes: `fontSize = max(7, cellSize × 0.22)` (proportional to screen)
- A safety cap prevents the longest word from overflowing the button edge
- Each word appears on its own line for clean, readable layout

**Model changes:**
- `ActionButton.label_font_size` is now `Optional[int]`:
  - `null` → auto-fit (computed by the pad client)
  - `int` → explicit size in px (used as-is)
  
Existing buttons with explicit sizes continue to work unchanged.

---

## CLI Options

```
python -m macro_deck_python [command] [options]

Commands:
  (none / start)      Start the server
  new-plugin          Scaffold a new Python extension

Server options:
  --port              WebSocket port           (default 8191)
  --config-port       Web UI port              (default 8192)
  --host              Bind address             (default 0.0.0.0)
  --no-tray           Disable system tray
  --no-gui            Disable web UI
  --no-updates        Disable update checker
  --no-hot-reload     Disable hot-reload watcher
  --plugins-dir       Custom plugins directory
  --log-level         DEBUG|INFO|WARNING|ERROR

new-plugin options:
  "Plugin Name"       Human-readable name (required)
  --id                package_id  e.g. me.myplugin (required)
  --author            Your name
  --desc              Short description
  --style             decorator (default) | class
  --out               Output parent directory
```

---

## WebSocket Protocol

All messages: `{ "method": "...", ...fields }`

### Client → Server

| Method | Fields | Description |
|---|---|---|
| `CONNECT` | `device_type`, `api_version` | Identify client |
| `BUTTON_PRESS` | `position` or `button_id` | Press a button |
| `GET_BUTTONS` | `folder_id?` | Fetch layout |
| `GET_PROFILES` | — | List profiles |
| `SET_PROFILE` | `profile_id` | Switch profile |
| `GET_VARIABLES` | — | List variables |
| `SET_VARIABLE` | `name`, `value`, `type` | Set variable |
| `SLIDER_CHANGE` | `slider_id`, `value` | Slider moved |
| `PING` | — | Keepalive |

### Server → Client

| Method | Fields | Description |
|---|---|---|
| `CONNECTED` | `client_id` | Welcome |
| `BUTTONS` | `buttons[]`, `button_type`, `slider_config` | Full layout |
| `BUTTON_STATE` | `button_id`, `state` | Toggle update |
| `PROFILES` | `profiles[]`, `active_id` | Profile list |
| `VARIABLES` | `variables[]` | All variables |
| `VARIABLE_CHANGED` | `variable` | Live update |
| `SLIDER_STATE` | `slider_id`, `value` | Slider broadcast |
| `PONG` | — | Keepalive reply |
| `ERROR` | `message` | Error |

---

## Writing a Python Extension

### Decorator style (recommended)

```python
# ~/.macro_deck/plugins/me.myplugin/main.py
from macro_deck_python.sdk import PluginBase, action, VariableType, set_variable

class Main(PluginBase):
    package_id  = "me.myplugin"
    name        = "My Plugin"
    version     = "1.0.0"
    author      = "Me"
    description = "Does something cool"

    @action(name="Mute", description="Toggle audio mute")
    def mute(self, client_id, button):
        import subprocess
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

    @action(name="Counter", can_configure=True)
    def counter(self, client_id, button):
        import json
        cfg = json.loads(self.configuration) if self.configuration else {}
        n = int(cfg.get("start", 0))
        set_variable("my_counter", n + 1, VariableType.INTEGER, self)
```

### Class style

```python
from macro_deck_python.sdk import PluginBase, ActionBase

class MyAction(ActionBase):
    action_id = "my_action";  name = "My Action";  description = ""
    def trigger(self, client_id, button):
        val = self.get_config("text", "hello")   # reads JSON config
        print(val)

class Main(PluginBase):
    package_id = "me.myplugin"; name = "My Plugin"; ...
    def enable(self):
        super().enable()
        self.actions.append(MyAction())
```

### SDK helpers

```python
from macro_deck_python.sdk import (
    set_variable, get_variable,     # variable access
    get_config, set_config,         # plugin config (persisted)
    get_credentials, set_credentials, delete_credentials,  # Fernet-encrypted
    log_trace, log_info, log_warning, log_error,
    VariableType,
)
```

### Scaffold

#### Windows (PowerShell)
```powershell
python -m macro_deck_python new-plugin "My Plugin" `
  --id me.myplugin --author "Me" --style decorator
```

#### Linux / macOS (Bash)
```bash
python3 -m macro_deck_python new-plugin "My Plugin" \
  --id me.myplugin --author "Me" --style decorator
```

Creates `~/.macro_deck/plugins/me.myplugin/` with:
`main.py`, `manifest.json`, `requirements.txt`, `config.json`, `README.md`

Add pip dependencies to `requirements.txt` — they auto-install on load.  
Edit `main.py` and save — Macro Deck hot-reloads within ~2 seconds.

---

## Analog Slider

Replace N consecutive button cells in a column with a vertical slider.

```python
# Via CreateSliderAction config:
{
  "row": 0,
  "col": 2,
  "slider_config": {
    "size": 4,          # rows occupied
    "min_value": 0,
    "max_value": 100,
    "step": 1,
    "label": "Volume",
    "outputs": [
      { "type": "variable",  "variable_name": "master_vol", "variable_type": "Integer" },
      { "type": "threshold",
        "thresholds": [
          { "min": 0,  "max": 10,  "keys": ["volume_mute"],  "mode": "crossing" },
          { "min": 90, "max": 100, "keys": ["f12"],           "mode": "crossing" }
        ]
      }
    ]
  }
}
```

**Output modes:**

| Type | Effect |
|---|---|
| `variable` | Writes value/normalised to a VariableManager variable |
| `threshold` | Fires key combos on zone entry (`crossing`) or hold while inside (`zone`) |

---

## Raspberry Pi / Browser Connection

The button-pad client is served at:
```
http://<server-ip>:8192       ← open this in the Pi browser
```

It auto-discovers the WebSocket port via `/api/info` and connects.  
No configuration needed — just open the URL.

If the connection fails:
```bash
# Allow the ports in the firewall
sudo ufw allow 8191/tcp
sudo ufw allow 8192/tcp

# Verify the server is listening on all interfaces
ss -tlnp | grep -E "8191|8192"
# Should show  0.0.0.0:8191  and  0.0.0.0:8192

# Test from the Pi
curl http://<server-ip>:8192/api/info
```

---

## Tests

### Windows (PowerShell)
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### Linux / macOS (Bash)
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

351 tests, 0 failures.

---

## License

Apache 2.0 — same as the original Macro Deck project.