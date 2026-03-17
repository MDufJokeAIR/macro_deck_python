"""
editor_client.py
================
Full visual grid editor for Macro Deck profiles.
Served at /editor.

Features
--------
- Visual CSS-grid matching the profile's columns×rows
- Click empty cell → create button
- Click existing button → opens inspector panel
- Drag-and-drop to reorder buttons
- Right-click → delete / duplicate
- Slider creation: hold Shift + drag across cells in same column
- Inspector panel (right side) with three tabs:
    STYLE   — label, label colour, background colour, icon upload
    ACTIONS — add/remove/configure actions; visual key picker for macros
    SLIDER  — inline slider placement and output configuration
- Key picker widget: up to 5 keys, tap_ms, hold_ms, double-click toggle
- All changes saved immediately to the REST API
"""

EDITOR_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Macro Deck — Editor</title>
<style>
/* ── Reset ─────────────────────────────────────────────────────── */
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d0d1a;--surface:#16213e;--surface2:#1a2a4a;--surface3:#0f3460;
  --accent:#7c83fd;--accent2:#5a62e0;--danger:#e05a5a;--success:#4ade80;
  --text:#e0e0e0;--muted:#9ca3af;--border:#1e2d4a;
  --radius:8px;--transition:.15s ease;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:system-ui,-apple-system,sans-serif;font-size:14px}

/* ── Layout ─────────────────────────────────────────────────────── */
#app{display:flex;height:100vh;flex-direction:column}
#topbar{display:flex;align-items:center;gap:10px;padding:8px 14px;
  background:var(--surface);border-bottom:1px solid var(--border);
  flex-shrink:0;min-height:48px}
#topbar h1{font-size:1rem;color:var(--accent);margin-right:6px;white-space:nowrap}
#workspace{display:flex;flex:1;overflow:hidden}
#grid-area{flex:1;overflow:hidden;display:flex;align-items:center;justify-content:center}
#inspector{width:340px;flex-shrink:0;background:var(--surface);
  border-left:1px solid var(--border);overflow-y:auto;display:flex;flex-direction:column}
#inspector.hidden{display:none}

/* ── Topbar controls ─────────────────────────────────────────────── */
select.ctrl,input.ctrl{background:var(--surface3);color:var(--text);
  border:1px solid var(--border);border-radius:var(--radius);
  padding:5px 10px;font-size:.85rem;outline:none}
select.ctrl:focus,input.ctrl:focus{border-color:var(--accent)}
.btn{padding:6px 14px;border:none;border-radius:var(--radius);cursor:pointer;
  font-size:.85rem;transition:background var(--transition)}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:var(--accent2)}
.btn-danger{background:var(--danger);color:#fff}
.btn-ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.btn-ghost:hover{background:var(--accent);color:#fff}
.btn-sm{padding:3px 10px;font-size:.8rem}
.sep{width:1px;height:24px;background:var(--border);margin:0 4px}

/* ── Grid ────────────────────────────────────────────────────────── */
#grid-wrap{position:relative}
#grid{display:grid;gap:5px}
.cell{
  background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;cursor:pointer;padding:6px;overflow:hidden;position:relative;
  transition:border-color var(--transition),background var(--transition);
  user-select:none}
.cell:hover{border-color:var(--accent);background:var(--surface3)}
.cell.empty{border-style:dashed;border-color:var(--border);background:transparent;
  color:var(--border)}
.cell.empty:hover{border-color:var(--accent);color:var(--accent)}
.cell.selected{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent)44}
.cell.drag-over{border-color:var(--success);background:var(--success)11}
.cell.drag-src{opacity:.4}
.cell.slider-head{background:#0f2040;border-color:var(--accent)88;border-style:solid}
.cell.slider-occ{background:#0a1a30;border-color:var(--accent)33;border-style:dashed;
  cursor:not-allowed}
.cell-icon{width:60%;height:60%;object-fit:contain;flex-shrink:0}
.cell-label{font-size:.65rem;text-align:center;line-height:1.2;max-width:100%;
  overflow:hidden;word-break:break-all;display:-webkit-box;
  -webkit-line-clamp:3;-webkit-box-orient:vertical}
.cell-type-badge{position:absolute;top:3px;right:3px;font-size:.55rem;
  background:var(--accent)33;color:var(--accent);border-radius:3px;padding:1px 4px}
.cell-add-icon{font-size:1.4rem;opacity:.3}
/* Slider mode highlight */
body.slider-mode .cell.empty:hover{border-color:#f59e0b;color:#f59e0b;
  background:#f59e0b11}
body.slider-mode .cell.slider-candidate{border-color:#f59e0b;background:#f59e0b22}
.slider-mode-bar{background:#f59e0b;color:#000;text-align:center;padding:4px 0;
  font-size:.8rem;border-radius:var(--radius);display:none}
body.slider-mode .slider-mode-bar{display:block}

/* ── Inspector ───────────────────────────────────────────────────── */
#insp-header{padding:12px 14px 0;display:flex;align-items:center;justify-content:space-between}
#insp-header h2{font-size:.95rem;color:var(--accent)}
#insp-close{background:none;border:none;color:var(--muted);font-size:1.1rem;
  cursor:pointer;padding:2px 6px}
#insp-close:hover{color:var(--danger)}
#insp-tabs{display:flex;border-bottom:1px solid var(--border);margin-top:8px;flex-shrink:0}
.tab-btn{flex:1;padding:8px 0;font-size:.8rem;background:none;border:none;
  color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;
  transition:all var(--transition)}
.tab-btn.active{color:var(--accent);border-bottom-color:var(--accent)}
.tab-btn:hover:not(.active){color:var(--text)}
.tab-panel{padding:12px 14px;display:none;flex-direction:column;gap:10px}
.tab-panel.active{display:flex}

/* ── Form elements ───────────────────────────────────────────────── */
.field{display:flex;flex-direction:column;gap:4px}
.field label{font-size:.75rem;color:var(--muted)}
.field input,.field select,.field textarea{
  background:var(--surface3);color:var(--text);border:1px solid var(--border);
  border-radius:6px;padding:6px 10px;font-size:.85rem;width:100%;outline:none}
.field input:focus,.field select:focus{border-color:var(--accent)}
.field textarea{resize:vertical;min-height:60px;font-family:monospace;font-size:.8rem}
.color-row{display:flex;align-items:center;gap:8px}
.color-row input[type=color]{width:36px;height:30px;border:none;border-radius:4px;
  padding:0;cursor:pointer;background:none}
.color-row input[type=text]{flex:1}
.icon-preview{width:48px;height:48px;border:1px solid var(--border);border-radius:6px;
  object-fit:contain;background:var(--surface3)}
.icon-row{display:flex;align-items:center;gap:8px}
.row{display:flex;gap:8px}
.row .field{flex:1}
h3{font-size:.8rem;color:var(--accent);text-transform:uppercase;
  letter-spacing:.06em;margin:4px 0 2px}

/* ── Actions list ────────────────────────────────────────────────── */
.action-item{background:var(--surface3);border-radius:6px;padding:8px 10px;
  display:flex;flex-direction:column;gap:6px;border:1px solid var(--border)}
.action-item-header{display:flex;align-items:center;justify-content:space-between;gap:6px}
.action-item-header span{font-size:.82rem;font-weight:500;flex:1}
.action-del{background:none;border:none;color:var(--danger);cursor:pointer;
  font-size:.9rem;padding:0 4px;opacity:.7}
.action-del:hover{opacity:1}
.action-cfg{margin-top:4px}
#add-action-row{display:flex;gap:6px;align-items:center}
#add-action-row select{flex:1;background:var(--surface3);color:var(--text);
  border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:.82rem}

/* ── Key picker ──────────────────────────────────────────────────── */
.key-picker{background:var(--bg);border-radius:var(--radius);padding:10px;
  border:1px solid var(--border);display:flex;flex-direction:column;gap:8px}
.key-slots{display:flex;gap:5px;flex-wrap:wrap}
.key-slot{display:flex;align-items:center;gap:3px}
.key-slot select{background:var(--surface3);color:var(--text);
  border:1px solid var(--border);border-radius:5px;padding:4px 6px;
  font-size:.75rem;max-width:120px}
.key-slot-add,.key-slot-del{background:none;border:none;cursor:pointer;
  font-size:.9rem;padding:0 3px}
.key-slot-add{color:var(--success)}
.key-slot-del{color:var(--danger)}
.key-options{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.key-options label{display:flex;align-items:center;gap:4px;font-size:.78rem;
  cursor:pointer;color:var(--muted)}
.key-options input[type=number]{width:64px;background:var(--surface3);
  color:var(--text);border:1px solid var(--border);border-radius:5px;
  padding:3px 6px;font-size:.78rem}
.key-options input[type=checkbox]{accent-color:var(--accent);cursor:pointer}
.mode-tabs{display:flex;gap:4px;margin-bottom:4px}
.mode-tab{padding:3px 10px;font-size:.75rem;border-radius:4px;border:1px solid var(--border);
  background:none;color:var(--muted);cursor:pointer}
.mode-tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}

/* ── Slider panel ────────────────────────────────────────────────── */
.slider-viz{background:var(--bg);border-radius:var(--radius);
  border:1px solid var(--accent)44;padding:10px;display:flex;flex-direction:column;
  gap:8px}
.slider-preview{display:flex;align-items:center;justify-content:center;gap:12px;
  padding:8px 0}
.slider-track{width:16px;border-radius:8px;background:var(--surface3);
  border:1px solid var(--border);flex-shrink:0;position:relative}
.slider-thumb{width:24px;height:12px;background:var(--accent);border-radius:3px;
  position:absolute;left:-4px;top:50%;transform:translateY(-50%)}
.output-item{background:var(--surface3);border-radius:6px;padding:8px;
  border:1px solid var(--border);display:flex;flex-direction:column;gap:6px}
.output-header{display:flex;align-items:center;justify-content:space-between}

/* ── Context menu ────────────────────────────────────────────────── */
#ctx-menu{position:fixed;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:4px 0;z-index:1000;display:none;
  box-shadow:0 4px 16px #00000066;min-width:140px}
.ctx-item{padding:8px 14px;cursor:pointer;font-size:.85rem;display:flex;
  align-items:center;gap:8px}
.ctx-item:hover{background:var(--surface3)}
.ctx-item.danger{color:var(--danger)}

/* ── Folder breadcrumb ───────────────────────────────────────────── */
#breadcrumb{display:flex;align-items:center;gap:4px;font-size:.8rem;color:var(--muted)}
#breadcrumb span{cursor:pointer;color:var(--accent);text-decoration:underline}
#breadcrumb span:hover{color:var(--text)}

/* ── Toast ───────────────────────────────────────────────────────── */
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);
  background:var(--accent);color:#fff;padding:8px 18px;border-radius:20px;
  font-size:.82rem;display:none;z-index:2000;pointer-events:none;white-space:nowrap}

/* ── Scrollbar ───────────────────────────────────────────────────── */
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>
<div id="app">

<!-- Top bar -->
<div id="topbar">
  <h1>🎛 Macro Deck</h1>
  <div class="sep"></div>
  <select class="ctrl" id="profile-sel" onchange="onProfileChange(this.value)"></select>
  <button class="btn btn-ghost btn-sm" onclick="renameProfile()">✏ Rename</button>
  <button class="btn btn-ghost btn-sm" onclick="createProfile()">+ Profile</button>
  <div class="sep"></div>
  <label style="font-size:.8rem;color:var(--muted)">Columns</label>
  <input class="ctrl" type="number" id="cols-inp" min="1" max="12" value="5"
    style="width:56px" onchange="resizeGrid()">
  <label style="font-size:.8rem;color:var(--muted)">Rows</label>
  <input class="ctrl" type="number" id="rows-inp" min="1" max="12" value="3"
    style="width:56px" onchange="resizeGrid()">
  <div class="sep"></div>
  <button class="btn btn-ghost btn-sm" id="slider-mode-btn" onclick="toggleSliderMode()">
    ⎸ Slider Mode
  </button>
  <div class="sep"></div>
  <a href="/pad" target="_blank" class="btn btn-ghost btn-sm">▶ Open Pad</a>
  <a href="/admin" target="_blank" class="btn btn-ghost btn-sm">⚙ Admin</a>
</div>

<!-- Workspace -->
<div id="workspace">

  <!-- Grid area -->
  <div id="grid-area">
    <div style="display:flex;align-items:center;gap:10px">
      <div id="breadcrumb"><span onclick="navRoot()">Root</span></div>
      <div class="slider-mode-bar" id="slider-bar">
        ⎸ Slider Mode — click the top cell of a column, then extend downward
      </div>
    </div>
    <div id="grid-wrap">
      <div id="grid"></div>
    </div>
    <!-- Sub-folder list -->
    <div id="subfolder-list" style="display:flex;flex-wrap:wrap;gap:6px"></div>
  </div>

  <!-- Inspector panel -->
  <div id="inspector" class="hidden">
    <div id="insp-header">
      <h2 id="insp-title">Button</h2>
      <button id="insp-close" onclick="closeInspector()" title="Close">✕</button>
    </div>
    <div id="insp-tabs">
      <button class="tab-btn active" onclick="showTab('style')">Style</button>
      <button class="tab-btn" onclick="showTab('actions')">Actions</button>
      <button class="tab-btn" id="tab-slider-btn"
              onclick="showTab('slider')" style="display:none">Slider</button>
    </div>

    <!-- Style tab -->
    <div class="tab-panel active" id="tab-style">
      <div class="field">
        <label>Label</label>
        <input type="text" id="f-label" placeholder="Button label or {variable}"
               oninput="debounceSave()">
      </div>
      <div class="row">
        <div class="field">
          <label>Label colour</label>
          <div class="color-row">
            <input type="color" id="f-lc-picker"
                   oninput="syncColor('f-lc-picker','f-lc-text')">
            <input type="text" class="ctrl" id="f-lc-text" value="#FFFFFF"
                   oninput="syncColor('f-lc-text','f-lc-picker')">
          </div>
        </div>
        <div class="field">
          <label>Background</label>
          <div class="color-row">
            <input type="color" id="f-bg-picker"
                   oninput="syncColor('f-bg-picker','f-bg-text')">
            <input type="text" class="ctrl" id="f-bg-text" value="#000000"
                   oninput="syncColor('f-bg-text','f-bg-picker')">
          </div>
        </div>
      </div>
      <div class="field">
        <label>Font size (px)</label>
        <input type="number" id="f-font" min="8" max="48" value="12"
               oninput="debounceSave()">
      </div>
      <div class="field">
        <label>Icon (PNG, upload or paste base64)</label>
        <div class="icon-row">
          <img id="icon-preview" class="icon-preview" src="" alt=""
               onerror="this.style.display='none'" style="display:none">
          <div style="display:flex;flex-direction:column;gap:4px;flex:1">
            <input type="file" id="icon-file" accept="image/png,image/jpeg,image/gif"
                   onchange="loadIcon(this)">
            <button class="btn btn-ghost btn-sm" onclick="clearIcon()">✕ Clear icon</button>
          </div>
        </div>
      </div>
      <div class="field">
        <label>State binding (variable → on/off)</label>
        <div style="display:flex;gap:4px;align-items:center">
          <select id="f-state-bind" onchange="debounceSave()" style="flex:1">
            <option value="">— none —</option>
          </select>
          <button class="btn btn-ghost btn-sm" title="Rename or retype this variable"
                  onclick="editBoundVariable()" style="flex-shrink:0">✏</button>
        </div>
        <div id="auto-var-hint" style="font-size:.7rem;color:var(--accent);margin-top:2px;display:none"></div>
      </div>
      <button class="btn btn-primary" onclick="saveButton()">Save button</button>
      <button class="btn btn-sm" style="background:var(--danger);color:#fff;margin-top:4px"
              onclick="deleteCurrentButton()">🗑 Delete button</button>
    </div>

    <!-- Actions tab -->
    <div class="tab-panel" id="tab-actions">
      <div id="actions-list" style="display:flex;flex-direction:column;gap:6px"></div>
      <h3>Add action</h3>
      <div id="add-action-row">
        <select id="action-picker">
          <option value="">Select action…</option>
        </select>
        <button class="btn btn-primary btn-sm" onclick="addAction()">+ Add</button>
      </div>
      <h3 style="margin-top:6px">Conditions</h3>
      <div id="conditions-list" style="display:flex;flex-direction:column;gap:6px"></div>
      <button class="btn btn-ghost btn-sm" onclick="addCondition()">+ Add condition</button>
      <button class="btn btn-primary" style="margin-top:4px"
              onclick="saveButton()">Save actions</button>
    </div>

    <!-- Slider tab -->
    <div class="tab-panel" id="tab-slider">
      <div class="slider-viz">
        <h3>Slider preview</h3>
        <div class="slider-preview">
          <div class="slider-track" id="sv-track" style="height:120px">
            <div class="slider-thumb"></div>
          </div>
          <div style="font-size:.75rem;color:var(--muted)">
            <div id="sv-max">100</div>
            <div style="margin:8px 0;color:var(--accent)" id="sv-cur">50</div>
            <div id="sv-min">0</div>
          </div>
        </div>
      </div>
      <div class="row">
        <div class="field">
          <label>Min value</label>
          <input type="number" id="sl-min" value="0" oninput="updateSliderPreview()">
        </div>
        <div class="field">
          <label>Max value</label>
          <input type="number" id="sl-max" value="100" oninput="updateSliderPreview()">
        </div>
        <div class="field">
          <label>Step</label>
          <input type="number" id="sl-step" value="1" min="0" step="any">
        </div>
      </div>
      <div class="field">
        <label>Label</label>
        <input type="text" id="sl-label" placeholder="Volume">
      </div>
      <div class="field">
        <label>Track colour</label>
        <div class="color-row">
          <input type="color" id="sl-color" value="#7c83fd"
                 oninput="syncColor('sl-color','sl-color-txt')">
          <input type="text" class="ctrl" id="sl-color-txt" value="#7c83fd"
                 oninput="syncColor('sl-color-txt','sl-color')">
        </div>
      </div>
      <div class="field">
        <label>Height (rows)</label>
        <input type="number" id="sl-size" min="1" max="10" value="3">
      </div>
      <h3>Outputs</h3>
      <div id="slider-outputs" style="display:flex;flex-direction:column;gap:6px"></div>
      <button class="btn btn-ghost btn-sm" onclick="addSliderOutput()">+ Add output</button>
      <button class="btn btn-primary" style="margin-top:6px"
              onclick="saveSlider()">Save slider</button>
    </div>
  </div><!-- /inspector -->
</div><!-- /workspace -->
</div><!-- /app -->

<!-- Context menu -->
<div id="ctx-menu">
  <div class="ctx-item" onclick="ctxEdit()">✏ Edit</div>
  <div class="ctx-item" onclick="ctxDuplicate()">⧉ Duplicate</div>
  <div class="ctx-item" onclick="ctxMoveUp()">↑ Move up</div>
  <div class="ctx-item" onclick="ctxMoveDown()">↓ Move down</div>
  <div class="ctx-item danger" onclick="ctxDelete()">🗑 Delete</div>
</div>

<div id="toast"></div>

<script>
// ═══════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════
let profiles = [];
let activeProfileId = null;
let folderStack = [];   // [{folder_id, name}]
let buttons = {};       // "row_col" → button object
let subFolders = [];
let cols = 5, rows = 3;
let selectedPos = null; // currently selected "row_col"
let allActions = [];    // [{plugin_id, action_id, name, description, can_configure}]
let allVariables = [];  // [{name, type, value}]
let sliderMode = false;
let sliderStartPos = null;
let keyGroups = {};     // group → [{id, label}]

// Editing state (inspector)
let editBtn = null;       // deep copy of the button being edited
let editSlider = null;    // slider config being edited

// Context menu target
let ctxPos = null;

// Debounce timer
let saveTimer = null;

// ═══════════════════════════════════════════════════════════════════
// API helpers
// ═══════════════════════════════════════════════════════════════════
const api = (method, url, body) => fetch(url, {
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body !== undefined ? JSON.stringify(body) : undefined,
}).then(r => r.json()).catch(e => ({ error: e.message }));

const GET  = url => api('GET', url);
const POST = (url, b) => api('POST', url, b);
const PUT  = (url, b) => api('PUT', url, b);
const DEL  = url => api('DELETE', url);

// ═══════════════════════════════════════════════════════════════════
// Boot
// ═══════════════════════════════════════════════════════════════════
async function boot() {
  const [pr, acts, vars] = await Promise.all([
    GET('/api/profiles'),
    GET('/api/actions'),
    GET('/api/variables'),
  ]);

  profiles      = pr.profiles || [];
  activeProfileId = pr.active_id || (profiles[0]?.id);
  allActions    = acts || [];
  allVariables  = vars || [];

  // Load key groups from keyboard_macro key_map
  try {
    const km = await GET('/api/keymap/groups');
    keyGroups = km.groups || {};
  } catch(e) { keyGroups = {}; }
  if (!Object.keys(keyGroups).length) {
    // Build minimal fallback
    keyGroups = {
      'Letters':['a','b','c','d','e','f','g','h','i','j','k','l','m',
                 'n','o','p','q','r','s','t','u','v','w','x','y','z'],
      'Digits': ['0','1','2','3','4','5','6','7','8','9'],
      'Function':['f1','f2','f3','f4','f5','f6','f7','f8','f9','f10',
                  'f11','f12','f13','f14','f15','f16','f17','f18','f19',
                  'f20','f21','f22','f23','f24'],
      'Modifiers':['ctrl','shift','alt','super','ctrl_left','ctrl_right',
                   'shift_left','shift_right','alt_left','alt_right','menu'],
      'Navigation':['up','down','left','right','home','end',
                    'page_up','page_down','insert','delete'],
      'Editing':['enter','escape','backspace','tab','space'],
      'Numpad':['num0','num1','num2','num3','num4','num5','num6','num7',
                'num8','num9','num_add','num_sub','num_mul','num_div',
                'num_decimal','num_enter'],
      'OEM':['oem_1','oem_2','oem_3','oem_4','oem_5','oem_6','oem_7',
             'oem_plus','oem_minus','oem_comma','oem_period'],
      'Media':['media_play_pause','media_next','media_prev','media_stop',
               'volume_up','volume_down','volume_mute'],
      'Mouse':['mouse_left','mouse_right','mouse_middle'],
    };
  }

  renderProfileSelect();
  populateActionPicker();
  await loadGrid();
}

// ═══════════════════════════════════════════════════════════════════
// Profile
// ═══════════════════════════════════════════════════════════════════
function renderProfileSelect() {
  const sel = document.getElementById('profile-sel');
  sel.innerHTML = profiles.map(p =>
    `<option value="${p.id}" ${p.id===activeProfileId?'selected':''}>${p.name}</option>`
  ).join('');
}

async function onProfileChange(id) {
  activeProfileId = id;
  folderStack = [];
  await loadGrid();
  closeInspector();
}

async function createProfile() {
  const name = prompt('Profile name:', 'New Profile');
  if (!name) return;
  const r = await POST('/api/profiles', { name });
  if (r.profile_id) {
    profiles.push({ id: r.profile_id, name });
    activeProfileId = r.profile_id;
    renderProfileSelect();
    folderStack = [];
    await loadGrid();
    toast('Profile created');
  }
}

async function renameProfile() {
  const current = profiles.find(p => p.id === activeProfileId);
  const newName = prompt('Rename profile:', current?.name || '');
  if (!newName || newName === current?.name) return;
  const r = await PUT(`/api/profiles/${activeProfileId}`, { name: newName });
  if (!r.error) {
    const p = profiles.find(p => p.id === activeProfileId);
    if (p) p.name = newName;
    renderProfileSelect();
    toast('Profile renamed ✓');
  } else {
    toast('Rename failed: ' + r.error, true);
  }
}

// ═══════════════════════════════════════════════════════════════════
// Grid loading
// ═══════════════════════════════════════════════════════════════════
async function loadGrid() {
  if (!activeProfileId) return;
  const fid = folderStack.length ? folderStack.at(-1).folder_id : undefined;
  const url = `/api/profiles/${activeProfileId}/buttons${fid ? '?folder_id='+fid : ''}`;
  const data = await GET(url);
  if (data.error) { toast('Failed to load grid', true); return; }

  cols = data.columns || 5;
  rows = data.rows    || 3;
  document.getElementById('cols-inp').value = cols;
  document.getElementById('rows-inp').value = rows;

  buttons    = {};
  subFolders = data.sub_folders || [];

  for (const btn of (data.buttons || [])) {
    buttons[btn.position] = btn;
  }

  renderGrid();
  renderBreadcrumb();
  renderSubfolders();
}

// ═══════════════════════════════════════════════════════════════════
// Grid rendering
// ═══════════════════════════════════════════════════════════════════
function renderGrid() {
  const grid = document.getElementById('grid');

  // ── Compute square cell size ──────────────────────────────────────
  const GAP       = 5;
  const PADDING   = 24;   // visual breathing room around the grid
  const TOPBAR_H  = document.getElementById('topbar').offsetHeight || 48;
  const insp      = document.getElementById('inspector');
  const inspW     = insp.classList.contains('hidden') ? 0 : (insp.offsetWidth || 340);
  const availW    = window.innerWidth  - inspW - PADDING * 2;
  const availH    = window.innerHeight - TOPBAR_H - PADDING * 2;
  const cellW     = Math.floor((availW - GAP * (cols - 1)) / cols);
  const cellH     = Math.floor((availH - GAP * (rows - 1)) / rows);
  const cell      = Math.max(20, Math.min(cellW, cellH));   // square, no hard min overflow

  grid.style.gridTemplateColumns = `repeat(${cols}, ${cell}px)`;
  grid.style.gridTemplateRows    = `repeat(${rows}, ${cell}px)`;
  grid.style.gap                 = `${GAP}px`;
  grid.innerHTML = '';

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const pos = `${r}_${c}`;
      const btn = buttons[pos];
      const cellEl = makeCell(pos, btn);
      grid.appendChild(cellEl);
    }
  }
}

function makeCell(pos, btn) {
  const el = document.createElement('div');
  el.className = 'cell';
  el.dataset.pos = pos;

  if (!btn) {
    el.classList.add('empty');
    el.innerHTML = `<span class="cell-add-icon">+</span>`;
    el.onclick = () => onCellClick(pos, null);
  } else if (btn.button_type === 'slider_occupied') {
    el.classList.add('slider-occ');
    el.innerHTML = `<span style="font-size:.65rem;color:var(--accent)44">⎸ slider</span>`;
  } else if (btn.button_type === 'slider') {
    el.classList.add('slider-head');
    const cfg = btn.slider_config || {};
    el.innerHTML = `
      <span style="font-size:.9rem">⎸</span>
      <span class="cell-label" style="color:var(--accent)">${cfg.label||'Slider'}</span>
      <span class="cell-type-badge">slider</span>`;
    el.onclick = () => onCellClick(pos, btn);
  } else {
    // Normal button
    if (btn.icon) {
      const img = document.createElement('img');
      img.className = 'cell-icon';
      img.src = btn.icon.startsWith('data:') ? btn.icon : `data:image/png;base64,${btn.icon}`;
      img.onerror = () => img.remove();
      el.appendChild(img);
    }
    if (btn.label) {
      const sp = document.createElement('span');
      sp.className = 'cell-label';
      sp.style.color = btn.label_color || '#fff';
      sp.textContent = btn.label;
      el.appendChild(sp);
    }
    if (!btn.icon && !btn.label) {
      el.innerHTML += `<span class="cell-add-icon" style="opacity:.15">btn</span>`;
    }
    if (btn.background_color && btn.background_color !== '#000000') {
      el.style.background = btn.background_color;
    }
    if (pos === selectedPos) el.classList.add('selected');
    el.onclick = () => onCellClick(pos, btn);
    el.ondblclick = () => { onCellClick(pos, btn); showTab('actions'); };
  }

  // Drag-and-drop (normal buttons only)
  if (btn && btn.button_type !== 'slider_occupied') {
    el.draggable = true;
    el.ondragstart = e => { e.dataTransfer.setData('srcPos', pos); el.classList.add('drag-src'); };
    el.ondragend   = () => el.classList.remove('drag-src');
  }
  el.ondragover  = e => { e.preventDefault(); el.classList.add('drag-over'); };
  el.ondragleave = () => el.classList.remove('drag-over');
  el.ondrop      = e => { e.preventDefault(); el.classList.remove('drag-over'); onDrop(e, pos); };

  // Right-click
  el.oncontextmenu = e => { e.preventDefault(); showCtxMenu(e, pos); };

  // Slider mode click
  if (sliderMode && (!btn || btn.button_type === 'slider_occupied')) {
    el.onclick = () => onSliderModeClick(pos);
  }

  return el;
}

// ═══════════════════════════════════════════════════════════════════
// Cell interaction
// ═══════════════════════════════════════════════════════════════════
async function onCellClick(pos, btn) {
  if (sliderMode) { onSliderModeClick(pos); return; }
  selectedPos = pos;
  document.querySelectorAll('.cell.selected').forEach(el => el.classList.remove('selected'));
  document.querySelector(`[data-pos="${pos}"]`)?.classList.add('selected');

  if (!btn) {
    // Create new empty button
    editBtn = {
      position: pos,
      label: '',
      label_color: '#ffffff',
      background_color: '#000000',
      label_font_size: 12,
      icon: null,
      state_binding: null,
      actions: [],
      conditions: [],
      button_type: 'button',
      slider_config: {},
    };
    openInspector('New Button', false);
  } else if (btn.button_type === 'slider') {
    editSlider = btn.slider_config ? { ...btn.slider_config } : {};
    editBtn = { ...btn };
    openInspector('Slider', true);
    populateSliderPanel(editSlider);
  } else {
    editBtn = JSON.parse(JSON.stringify(btn));
    openInspector('Button', false);
  }
  populateStylePanel(editBtn);
  populateActionsPanel(editBtn);
  await populateVariableSelect();
}

// ═══════════════════════════════════════════════════════════════════
// Inspector
// ═══════════════════════════════════════════════════════════════════
function openInspector(title, isSlider) {
  document.getElementById('inspector').classList.remove('hidden');
  document.getElementById('insp-title').textContent = title;
  const slTab = document.getElementById('tab-slider-btn');
  slTab.style.display = isSlider ? '' : 'none';
  if (isSlider) showTab('slider');
  else showTab('style');
  renderGrid();
}

function closeInspector() {
  document.getElementById('inspector').classList.add('hidden');
  selectedPos = null;
  document.querySelectorAll('.cell.selected').forEach(el => el.classList.remove('selected'));
  renderGrid();
}

function showTab(name) {
  document.querySelectorAll('.tab-btn').forEach((b,i) => {
    const names = ['style','actions','slider'];
    b.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-'+name)?.classList.add('active');
}

// ═══════════════════════════════════════════════════════════════════
// Style panel
// ═══════════════════════════════════════════════════════════════════
function populateStylePanel(btn) {
  document.getElementById('f-label').value        = btn.label || '';
  document.getElementById('f-font').value         = btn.label_font_size || 12;
  setColor('f-lc', btn.label_color || '#ffffff');
  setColor('f-bg', btn.background_color || '#000000');
  const preview = document.getElementById('icon-preview');
  if (btn.icon) {
    preview.src = btn.icon.startsWith('data:') ? btn.icon
                : `data:image/png;base64,${btn.icon}`;
    preview.style.display = '';
  } else {
    preview.style.display = 'none';
  }
}

function setColor(id, hex) {
  const safe = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : '#000000';
  document.getElementById(id+'-picker').value = safe;
  document.getElementById(id+'-text').value   = hex;
}

function syncColor(from, to) {
  document.getElementById(to).value = document.getElementById(from).value;
  debounceSave();
}

function loadIcon(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const b64 = e.target.result;
    editBtn.icon = b64;
    const preview = document.getElementById('icon-preview');
    preview.src = b64;
    preview.style.display = '';
  };
  reader.readAsDataURL(file);
}

function clearIcon() {
  editBtn.icon = null;
  document.getElementById('icon-preview').style.display = 'none';
  document.getElementById('icon-file').value = '';
}

async function populateVariableSelect() {
  const sel  = document.getElementById('f-state-bind');
  const hint = document.getElementById('auto-var-hint');
  const cur  = editBtn?.state_binding || '';

  // Fetch the auto-variable for this button position
  let autoVarName = null;
  if (activeProfileId && selectedPos) {
    try {
      const av = await GET(`/api/profiles/${activeProfileId}/buttons/${selectedPos}/variable`);
      if (av?.name) autoVarName = av.name;
    } catch(e) {}
  }

  // Refresh allVariables from server so rename reflects immediately
  try {
    allVariables = await GET('/api/variables') || allVariables;
  } catch(e) {}

  // Build options: auto-var first (if exists), then all others
  const autoOption = autoVarName
    ? `<option value="${autoVarName}" ${cur===autoVarName?'selected':''}>${autoVarName} ★</option>`
    : '';
  const rest = allVariables
    .filter(v => v.name !== autoVarName)
    .map(v => `<option value="${v.name}" ${v.name===cur?'selected':''}>${v.name} (${v.type})</option>`)
    .join('');

  sel.innerHTML = `<option value="">— none —</option>${autoOption}${rest}`;

  // Show hint when auto-var is selected or as default suggestion
  if (autoVarName) {
    hint.style.display = '';
    hint.textContent   = `Auto-variable: ${autoVarName}`;
  } else {
    hint.style.display = 'none';
  }
}

async function editBoundVariable() {
  const sel     = document.getElementById('f-state-bind');
  const varName = sel.value;
  if (!varName) {
    toast('Select a variable first', true);
    return;
  }
  const newName = prompt('Variable name:', varName);
  if (!newName) return;

  const allTypes = ['Bool', 'Integer', 'Float', 'String'];
  const cur = allVariables.find(v => v.name === varName);
  const curType = cur?.type || 'Bool';
  const newType = prompt(
    `Type (${allTypes.join(' / ')}):`,
    curType
  );
  if (!newType || !allTypes.includes(newType)) {
    toast('Invalid type', true);
    return;
  }

  const r = await PUT(`/api/variables/${encodeURIComponent(varName)}`,
                      { name: newName, type: newType });
  if (r.ok) {
    // Update local cache
    const idx = allVariables.findIndex(v => v.name === varName);
    if (idx !== -1) {
      allVariables[idx].name = newName;
      allVariables[idx].type = newType;
    }
    // If this was the bound variable, update editBtn
    if (editBtn?.state_binding === varName) {
      editBtn.state_binding = newName;
    }
    await populateVariableSelect();
    toast(`Variable renamed to ${newName} (${newType}) ✓`);
  } else {
    toast('Rename failed: ' + (r.error || 'unknown'), true);
  }
}

function collectStyleFromPanel() {
  if (!editBtn) return;
  editBtn.label            = document.getElementById('f-label').value;
  editBtn.label_font_size  = parseInt(document.getElementById('f-font').value) || 12;
  editBtn.label_color      = document.getElementById('f-lc-text').value || '#ffffff';
  editBtn.background_color = document.getElementById('f-bg-text').value || '#000000';
  editBtn.state_binding    = document.getElementById('f-state-bind').value || null;
}

// ═══════════════════════════════════════════════════════════════════
// Actions panel
// ═══════════════════════════════════════════════════════════════════
function populateActionPicker() {
  const sel = document.getElementById('action-picker');
  // Group by plugin
  const byPlugin = {};
  for (const a of allActions) {
    (byPlugin[a.plugin_id] = byPlugin[a.plugin_id] || []).push(a);
  }
  sel.innerHTML = '<option value="">Select action…</option>' +
    Object.entries(byPlugin).map(([pid, acts]) =>
      `<optgroup label="${pid}">${
        acts.map(a => `<option value="${pid}::${a.action_id}">${a.name}</option>`).join('')
      }</optgroup>`
    ).join('');
}

function populateActionsPanel(btn) {
  const list = document.getElementById('actions-list');
  list.innerHTML = '';
  for (let i = 0; i < (btn.actions||[]).length; i++) {
    list.appendChild(makeActionItem(btn.actions[i], i));
  }
  renderConditions(btn.conditions || []);
}

function makeActionItem(entry, idx) {
  const act = allActions.find(a =>
    a.plugin_id === entry.plugin_id && a.action_id === entry.action_id);
  const name = act?.name || entry.action_id;
  const isMacro = ['macro_short_press','macro_long_press','macro_double_click',
                   'macro_tap_sequence'].includes(entry.action_id);

  const wrap = document.createElement('div');
  wrap.className = 'action-item';

  const header = document.createElement('div');
  header.className = 'action-item-header';
  header.innerHTML = `
    <span title="${entry.plugin_id}">${name}</span>
    <button class="action-del" onclick="deleteAction(${idx})">✕</button>`;
  wrap.appendChild(header);

  if (act?.can_configure) {
    if (isMacro) {
      wrap.appendChild(makeKeyPicker(entry, idx));
    } else {
      const cfgDiv = makeSmartActionConfig(entry, idx);
      wrap.appendChild(cfgDiv);
    }
  }
  return wrap;
}

function _varOptions(selected) {
  return allVariables.map(v =>
    `<option value="${v.name}" ${v.name===selected?'selected':''}>${v.name} (${v.type})</option>`
  ).join('');
}

function makeSmartActionConfig(entry, idx) {
  let cfg = {};
  try { cfg = JSON.parse(entry.configuration || '{}'); } catch(e) {}

  const div = document.createElement('div');
  div.className = 'action-cfg';

  const aid = entry.action_id;

  // ── Toggle Variable ──────────────────────────────────────────────
  if (aid === 'toggle_variable') {
    div.innerHTML = `
      <div class="field">
        <label>Variable to toggle (Bool)</label>
        <select onchange="updateSmartCfg(${idx},'variable_name',this.value)">
          <option value="">— select —</option>
          ${_varOptions(cfg.variable_name||'')}
        </select>
      </div>`;
    return div;
  }

  // ── Set Variable ─────────────────────────────────────────────────
  if (aid === 'set_variable') {
    div.innerHTML = `
      <div class="field">
        <label>Variable</label>
        <select onchange="updateSmartCfg(${idx},'variable_name',this.value)">
          <option value="">— select —</option>
          ${_varOptions(cfg.variable_name||'')}
        </select>
      </div>
      <div class="field">
        <label>Value</label>
        <input class="ctrl" value="${escHtml(String(cfg.value??''))}"
          oninput="updateSmartCfg(${idx},'value',this.value)">
      </div>
      <div class="field">
        <label>Type</label>
        <select onchange="updateSmartCfg(${idx},'type',this.value)">
          ${['Bool','Integer','Float','String'].map(t =>
            `<option ${(cfg.type||'String')===t?'selected':''}>${t}</option>`).join('')}
        </select>
      </div>`;
    return div;
  }

  // ── Hotkey ───────────────────────────────────────────────────────
  if (aid === 'hotkey') {
    div.innerHTML = `
      <div class="field">
        <label>Keys (e.g. ctrl+c, ctrl+shift+t)</label>
        <input class="ctrl" value="${escHtml(cfg.keys||'')}"
          placeholder="ctrl+c"
          oninput="updateSmartCfg(${idx},'keys',this.value)">
      </div>`;
    return div;
  }

  // ── Type Text ────────────────────────────────────────────────────
  if (aid === 'type_text') {
    div.innerHTML = `
      <div class="field">
        <label>Text to type</label>
        <input class="ctrl" value="${escHtml(cfg.text||'')}"
          oninput="updateSmartCfg(${idx},'text',this.value)">
      </div>
      <div class="field">
        <label>Interval between chars (s)</label>
        <input class="ctrl" type="number" min="0" step="0.01"
          value="${cfg.interval??0.03}"
          oninput="updateSmartCfg(${idx},'interval',parseFloat(this.value))">
      </div>`;
    return div;
  }

  // ── Key Press ────────────────────────────────────────────────────
  if (aid === 'key_press') {
    div.innerHTML = `
      <div class="field">
        <label>Key</label>
        <input class="ctrl" value="${escHtml(cfg.key||'')}"
          placeholder="f5, enter, space…"
          oninput="updateSmartCfg(${idx},'key',this.value)">
      </div>`;
    return div;
  }

  // ── Run Command ──────────────────────────────────────────────────
  if (aid === 'run_command') {
    div.innerHTML = `
      <div class="field">
        <label>Command</label>
        <input class="ctrl" value="${escHtml(cfg.command||'')}"
          oninput="updateSmartCfg(${idx},'command',this.value)">
      </div>
      <div class="field" style="flex-direction:row;align-items:center;gap:8px">
        <input type="checkbox" ${cfg.wait?'checked':''} id="wait-${idx}"
          onchange="updateSmartCfg(${idx},'wait',this.checked)">
        <label for="wait-${idx}">Wait for completion</label>
      </div>`;
    return div;
  }

  // ── Open URL ─────────────────────────────────────────────────────
  if (aid === 'open_url') {
    div.innerHTML = `
      <div class="field">
        <label>URL</label>
        <input class="ctrl" value="${escHtml(cfg.url||'')}"
          placeholder="https://…"
          oninput="updateSmartCfg(${idx},'url',this.value)">
      </div>`;
    return div;
  }

  // ── Delay ────────────────────────────────────────────────────────
  if (aid === 'delay') {
    div.innerHTML = `
      <div class="field">
        <label>Duration (milliseconds)</label>
        <input class="ctrl" type="number" min="1" value="${cfg.milliseconds??500}"
          oninput="updateSmartCfg(${idx},'milliseconds',parseInt(this.value))">
      </div>`;
    return div;
  }

  // ── Generic JSON fallback ────────────────────────────────────────
  div.innerHTML = `
    <div class="field">
      <label>Configuration (JSON)</label>
      <textarea id="cfg-${idx}" onchange="updateActionCfg(${idx},this.value)"
        >${escHtml(entry.configuration||'{}')}</textarea>
    </div>`;
  return div;
}

window.updateSmartCfg = function(idx, key, value) {
  if (!editBtn?.actions?.[idx]) return;
  let cfg = {};
  try { cfg = JSON.parse(editBtn.actions[idx].configuration || '{}'); } catch(e) {}
  cfg[key] = value;
  editBtn.actions[idx].configuration = JSON.stringify(cfg);
};

function makeKeyPicker(entry, idx) {
  let cfg = {};
  try { cfg = JSON.parse(entry.configuration||'{}'); } catch(e) {}

  const keys      = cfg.keys || [''];
  const tapMs     = cfg.tap_ms || 50;
  const holdMs    = cfg.hold_ms || 500;
  const doubleInt = cfg.double_interval_ms || 80;
  const isDouble  = entry.action_id === 'macro_double_click';
  const isLong    = entry.action_id === 'macro_long_press';

  // Build key group options HTML (cached)
  if (!window._keyOptsHtml) {
    let html = '<option value="">—</option>';
    for (const [grp, ks] of Object.entries(keyGroups)) {
      html += `<optgroup label="${grp}">`;
      for (const k of ks) {
        html += `<option value="${k}">${k}</option>`;
      }
      html += '</optgroup>';
    }
    window._keyOptsHtml = html;
  }

  const div = document.createElement('div');
  div.className = 'key-picker';
  div.innerHTML = `
    <div style="font-size:.75rem;color:var(--muted)">Keys (1–5)</div>
    <div class="key-slots" id="ks-${idx}"></div>
    <div class="key-options">
      ${!isLong ? `<label>Tap ms<input type="number" class="kp-tap" data-idx="${idx}"
        value="${tapMs}" min="1" max="2000" onchange="syncKeyPicker(${idx})"></label>` : ''}
      ${isLong ? `<label>Hold ms<input type="number" class="kp-hold" data-idx="${idx}"
        value="${holdMs}" min="1" max="10000" onchange="syncKeyPicker(${idx})"></label>` : ''}
      ${isDouble ? `<label>Interval ms<input type="number" class="kp-dbl" data-idx="${idx}"
        value="${doubleInt}" min="10" onchange="syncKeyPicker(${idx})"></label>` : ''}
    </div>`;

  const slotsDiv = div.querySelector(`#ks-${idx}`);

  function renderSlots(currentKeys) {
    slotsDiv.innerHTML = '';
    const used = Math.max(1, Math.min(5, currentKeys.length));
    for (let s = 0; s < used; s++) {
      const slotEl = document.createElement('div');
      slotEl.className = 'key-slot';
      slotEl.innerHTML = `
        <select onchange="syncKeyPicker(${idx})" title="Key ${s+1}">
          ${window._keyOptsHtml}
        </select>
        ${s > 0 ? `<button class="key-slot-del" onclick="removeKeySlot(${idx},${s})">✕</button>` : ''}`;
      slotEl.querySelector('select').value = currentKeys[s] || '';
      slotsDiv.appendChild(slotEl);
    }
    if (used < 5) {
      const addBtn = document.createElement('button');
      addBtn.className = 'key-slot-add';
      addBtn.textContent = '+';
      addBtn.onclick = () => {
        try {
          const e = editBtn.actions[idx];
          const c = JSON.parse(e.configuration || '{}');
          c.keys = [...(c.keys||['']), ''];
          e.configuration = JSON.stringify(c);
        } catch(err) {}
        populateActionsPanel(editBtn);
      };
      slotsDiv.appendChild(addBtn);
    }
  }

  renderSlots(keys);
  return div;
}

window.syncKeyPicker = function(idx) {
  const entry = editBtn?.actions?.[idx];
  if (!entry) return;
  let cfg = {};
  try { cfg = JSON.parse(entry.configuration || '{}'); } catch(e) {}

  const slotsDiv = document.getElementById(`ks-${idx}`);
  if (slotsDiv) {
    cfg.keys = Array.from(slotsDiv.querySelectorAll('select'))
      .map(s => s.value).filter(v => v);
  }

  const tapEl  = document.querySelector(`.kp-tap[data-idx="${idx}"]`);
  const holdEl = document.querySelector(`.kp-hold[data-idx="${idx}"]`);
  const dblEl  = document.querySelector(`.kp-dbl[data-idx="${idx}"]`);
  if (tapEl)  cfg.tap_ms              = parseInt(tapEl.value)  || 50;
  if (holdEl) cfg.hold_ms             = parseInt(holdEl.value) || 500;
  if (dblEl)  cfg.double_interval_ms  = parseInt(dblEl.value)  || 80;

  entry.configuration = JSON.stringify(cfg);
};

window.removeKeySlot = function(idx, slotIdx) {
  const entry = editBtn?.actions?.[idx];
  if (!entry) return;
  try {
    const c = JSON.parse(entry.configuration || '{}');
    c.keys = (c.keys || []).filter((_, i) => i !== slotIdx);
    if (!c.keys.length) c.keys = [''];
    entry.configuration = JSON.stringify(c);
  } catch(e) {}
  populateActionsPanel(editBtn);
};

window.updateActionCfg = function(idx, val) {
  if (editBtn?.actions?.[idx]) editBtn.actions[idx].configuration = val;
};

window.deleteAction = function(idx) {
  editBtn.actions.splice(idx, 1);
  populateActionsPanel(editBtn);
};

function addAction() {
  const sel = document.getElementById('action-picker');
  const val = sel.value;
  if (!val) return;
  const [pid, aid] = val.split('::');
  editBtn.actions = editBtn.actions || [];
  editBtn.actions.push({
    plugin_id: pid, action_id: aid,
    configuration: '{}', configuration_summary: '',
  });
  populateActionsPanel(editBtn);
  sel.value = '';
}

// ═══════════════════════════════════════════════════════════════════
// Conditions
// ═══════════════════════════════════════════════════════════════════
function _styleFields(prefix, i, style) {
  // Inline style editor for one branch of a condition
  style = style || {};
  return `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:4px">
      <div>
        <label style="font-size:.7rem;color:var(--muted)">Label</label>
        <input class="ctrl" style="width:100%;font-size:.75rem" value="${style.label||''}"
          oninput="condStyle(${i},'${prefix}','label',this.value)">
      </div>
      <div>
        <label style="font-size:.7rem;color:var(--muted)">Label colour</label>
        <div style="display:flex;gap:4px">
          <input type="color" value="${/^#[0-9a-fA-F]{6}$/.test(style.label_color||'')?style.label_color:'#ffffff'}"
            oninput="condStyle(${i},'${prefix}','label_color',this.value)" style="width:32px;height:26px;border:none;border-radius:4px;cursor:pointer">
          <input class="ctrl" style="flex:1;font-size:.75rem" value="${style.label_color||''}"
            oninput="condStyle(${i},'${prefix}','label_color',this.value)">
        </div>
      </div>
      <div>
        <label style="font-size:.7rem;color:var(--muted)">Background</label>
        <div style="display:flex;gap:4px">
          <input type="color" value="${/^#[0-9a-fA-F]{6}$/.test(style.background_color||'')?style.background_color:'#000000'}"
            oninput="condStyle(${i},'${prefix}','background_color',this.value)" style="width:32px;height:26px;border:none;border-radius:4px;cursor:pointer">
          <input class="ctrl" style="flex:1;font-size:.75rem" value="${style.background_color||''}"
            oninput="condStyle(${i},'${prefix}','background_color',this.value)">
        </div>
      </div>
    </div>`;
}

function renderConditions(conditions) {
  const list = document.getElementById('conditions-list');
  list.innerHTML = '';
  conditions.forEach((cond, i) => {
    const d = document.createElement('div');
    d.className = 'action-item';
    d.innerHTML = `
      <div class="action-item-header">
        <span style="font-size:.8rem">
          If&nbsp;<b>${cond.variable_name||'?'}</b>&nbsp;${cond.operator||'=='}&nbsp;<b>${cond.compare_value||'?'}</b>
          &nbsp;<span style="font-size:.7rem;color:var(--muted)">(use <code>_state</code> for button toggle)</span>
        </span>
        <button class="action-del" onclick="deleteCondition(${i})">✕</button>
      </div>

      <details style="margin-top:6px">
        <summary style="font-size:.75rem;cursor:pointer;color:var(--accent)">
          ✅ When TRUE — ${(cond.actions_true||[]).length} action(s)
        </summary>
        ${_styleFields('style_true', i, cond.style_true)}
        <div style="font-size:.72rem;color:var(--muted);margin-top:6px">
          Actions: ${(cond.actions_true||[]).length} (edit via Actions tab — TODO inline)
        </div>
      </details>

      <details style="margin-top:4px">
        <summary style="font-size:.75rem;cursor:pointer;color:var(--muted)">
          ❌ When FALSE — ${(cond.actions_false||[]).length} action(s)
        </summary>
        ${_styleFields('style_false', i, cond.style_false)}
        <div style="font-size:.72rem;color:var(--muted);margin-top:6px">
          Actions: ${(cond.actions_false||[]).length} (edit via Actions tab — TODO inline)
        </div>
      </details>`;
    list.appendChild(d);
  });
}

window.condStyle = function(i, branch, key, value) {
  // Live-update a style field on a condition branch
  if (!editBtn?.conditions?.[i]) return;
  editBtn.conditions[i][branch] = editBtn.conditions[i][branch] || {};
  editBtn.conditions[i][branch][key] = value;
};

function addCondition() {
  // Build a list of variable options to show in the prompt
  const autoVarPrefix = activeProfileId && selectedPos
    ? (() => {
        // Derive the auto-var name client-side (mirrors server logic)
        const profile = profiles.find(p => p.id === activeProfileId);
        if (!profile) return null;
        const safe = profile.name.replace(/[^a-zA-Z0-9_]/g, '');
        const [r, c] = selectedPos.split('_').map(Number);
        return `Profile${safe}_x${c+1}y${r+1}`;
      })()
    : null;

  const varOptions = [
    '_state',
    ...(autoVarPrefix ? [autoVarPrefix + ' ★'] : []),
    ...allVariables.filter(v => v.name !== autoVarPrefix).map(v => v.name),
  ];
  const varName = prompt(
    'Variable name (or _state for button toggle):\n\nSuggested: ' + varOptions.slice(0,6).join(', '),
    autoVarPrefix || '_state'
  );
  if (!varName) return;
  // Strip the ★ suffix if the user left it in
  const cleanVar = varName.replace(/\s*★$/, '').trim();
  const op = prompt('Operator (==, !=, >, <, >=, <=):', '==');
  if (!op) return;
  const defaultVal = cleanVar === '_state' ? 'True' : '';
  const val = prompt('Compare value:', defaultVal);
  if (val === null) return;
  editBtn.conditions = editBtn.conditions || [];
  editBtn.conditions.push({
    variable_name: cleanVar, operator: op, compare_value: val,
    actions_true: [], actions_false: [],
    style_true: {}, style_false: {},
  });
  renderConditions(editBtn.conditions);
}

window.deleteCondition = function(i) {
  editBtn.conditions.splice(i, 1);
  renderConditions(editBtn.conditions);
};

// ═══════════════════════════════════════════════════════════════════
// Slider panel
// ═══════════════════════════════════════════════════════════════════
function populateSliderPanel(cfg) {
  document.getElementById('sl-min').value   = cfg.min_value  ?? 0;
  document.getElementById('sl-max').value   = cfg.max_value  ?? 100;
  document.getElementById('sl-step').value  = cfg.step       ?? 1;
  document.getElementById('sl-label').value = cfg.label      || '';
  document.getElementById('sl-size').value  = cfg.size       ?? 3;
  const color = cfg.color || '#7c83fd';
  document.getElementById('sl-color').value     = color;
  document.getElementById('sl-color-txt').value = color;
  renderSliderOutputs(cfg.outputs || []);
  updateSliderPreview();
}

function updateSliderPreview() {
  const min = parseFloat(document.getElementById('sl-min').value) || 0;
  const max = parseFloat(document.getElementById('sl-max').value) || 100;
  const cur = (min + max) / 2;
  document.getElementById('sv-min').textContent = min;
  document.getElementById('sv-max').textContent = max;
  document.getElementById('sv-cur').textContent = cur.toFixed(1);
  const color = document.getElementById('sl-color')?.value || '#7c83fd';
  document.getElementById('sv-track').style.background = color + '33';
  document.querySelector('.slider-thumb').style.background = color;
}

function renderSliderOutputs(outputs) {
  const wrap = document.getElementById('slider-outputs');
  wrap.innerHTML = '';
  outputs.forEach((out, i) => {
    const d = document.createElement('div');
    d.className = 'output-item';
    const type = out.type || 'variable';
    d.innerHTML = `
      <div class="output-header">
        <select onchange="changeOutputType(${i},this.value)" style="background:var(--surface3);
          color:var(--text);border:1px solid var(--border);border-radius:5px;
          padding:4px 8px;font-size:.8rem">
          <option value="variable"  ${type==='variable' ?'selected':''}>Variable</option>
          <option value="threshold" ${type==='threshold'?'selected':''}>Key Threshold</option>
        </select>
        <button class="action-del" onclick="removeSliderOutput(${i})">✕</button>
      </div>
      <div id="out-cfg-${i}">${renderOutputConfig(out, i)}</div>`;
    wrap.appendChild(d);
  });
}

function renderOutputConfig(out, i) {
  if (out.type === 'variable') {
    return `
      <div class="field">
        <label>Variable name</label>
        <input type="text" value="${out.variable_name||''}"
          onchange="updateOutputCfg(${i},'variable_name',this.value)"
          placeholder="e.g. master_volume">
      </div>
      <div class="field">
        <label>Type</label>
        <select onchange="updateOutputCfg(${i},'variable_type',this.value)">
          ${['Float','Integer','String','Bool'].map(t =>
            `<option ${(out.variable_type||'Float')===t?'selected':''}>${t}</option>`).join('')}
        </select>
      </div>`;
  }
  if (out.type === 'threshold') {
    const zones = out.thresholds || [];
    return `
      <div style="font-size:.75rem;color:var(--muted);margin-bottom:4px">
        ${zones.length} zone(s) configured
        <button class="btn btn-ghost btn-sm" style="margin-left:4px"
          onclick="editThresholds(${i})">Edit zones</button>
      </div>`;
  }
  return '';
}

window.changeOutputType = function(i, type) {
  if (!editSlider) return;
  const outs = editSlider.outputs || [];
  outs[i] = { type };
  editSlider.outputs = outs;
  renderSliderOutputs(outs);
};

window.updateOutputCfg = function(i, key, val) {
  if (!editSlider) return;
  editSlider.outputs = editSlider.outputs || [];
  editSlider.outputs[i] = { ...(editSlider.outputs[i]||{}), [key]: val };
};

window.removeSliderOutput = function(i) {
  if (!editSlider) return;
  editSlider.outputs.splice(i, 1);
  renderSliderOutputs(editSlider.outputs);
};

function addSliderOutput() {
  if (!editSlider) editSlider = {};
  editSlider.outputs = editSlider.outputs || [];
  editSlider.outputs.push({ type: 'variable', variable_name: '', variable_type: 'Float' });
  renderSliderOutputs(editSlider.outputs);
}

window.editThresholds = function(i) {
  const out = editSlider?.outputs?.[i];
  if (!out) return;
  const txt = prompt('Edit thresholds (JSON array):\n[{"min":0,"max":33,"keys":["1"],"mode":"crossing"},...]',
    JSON.stringify(out.thresholds||[], null, 2));
  if (txt === null) return;
  try {
    out.thresholds = JSON.parse(txt);
    renderSliderOutputs(editSlider.outputs);
  } catch(e) {
    toast('Invalid JSON', true);
  }
};

function collectSliderFromPanel() {
  if (!editSlider) editSlider = {};
  editSlider.min_value  = parseFloat(document.getElementById('sl-min').value)  || 0;
  editSlider.max_value  = parseFloat(document.getElementById('sl-max').value)  || 100;
  editSlider.step       = parseFloat(document.getElementById('sl-step').value) || 1;
  editSlider.label      = document.getElementById('sl-label').value;
  editSlider.size       = parseInt(document.getElementById('sl-size').value)   || 3;
  editSlider.color      = document.getElementById('sl-color').value;
  editSlider.current_value = editSlider.current_value ?? editSlider.min_value;
}

// ═══════════════════════════════════════════════════════════════════
// Save
// ═══════════════════════════════════════════════════════════════════
function debounceSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {}, 1200); // just prevent rapid triggers
}

async function saveButton() {
  if (!editBtn || !selectedPos) return;
  collectStyleFromPanel();

  const payload = {
    ...editBtn,
    position: selectedPos,
    button_type: 'button',
  };
  const fid = folderStack.length ? folderStack.at(-1).folder_id : null;
  if (fid) payload.folder_id = fid;

  const r = await POST(`/api/profiles/${activeProfileId}/buttons`, payload);
  if (r.button_id || r.position || !r.error) {
    toast('Saved ✓');
    await loadGrid();
    // Re-select
    const cell = document.querySelector(`[data-pos="${selectedPos}"]`);
    cell?.classList.add('selected');
  } else {
    toast('Save failed: '+(r.error||'unknown'), true);
  }
}

async function deleteCurrentButton() {
  if (!selectedPos || !buttons[selectedPos]) return;
  if (!confirm('Delete this button?')) return;
  ctxPos = selectedPos;
  await window.ctxDelete();
}

async function saveSlider() {
  if (!selectedPos) return;
  collectSliderFromPanel();
  const [rowStr, colStr] = selectedPos.split('_');
  const row = parseInt(rowStr), col = parseInt(colStr);
  const cfg = {
    row, col,
    slider_config: {
      ...editSlider,
      outputs: editSlider.outputs || [],
    }
  };
  const fid = folderStack.length ? folderStack.at(-1).folder_id : null;
  if (fid) cfg.slider_config.folder_id = fid;

  // Use the create_slider action via the REST API for buttons
  // Store as a button_type="slider" ActionButton directly
  const size = editSlider.size || 3;
  const headPayload = {
    position: selectedPos,
    button_type: 'slider',
    slider_config: { ...editSlider, outputs: editSlider.outputs || [], size },
    label: editSlider.label || 'Slider',
    label_color: '#7c83fd',
    background_color: '#000000',
    actions: [], conditions: [],
  };
  if (fid) headPayload.folder_id = fid;
  await POST(`/api/profiles/${activeProfileId}/buttons`, headPayload);

  // Occupied cells
  for (let i = 1; i < size; i++) {
    const occ = {
      position: `${row+i}_${col}`,
      button_type: 'slider_occupied',
      slider_config: { parent_pos: selectedPos },
      label: '', background_color: '#000000', actions: [], conditions: [],
    };
    if (fid) occ.folder_id = fid;
    await POST(`/api/profiles/${activeProfileId}/buttons`, occ);
  }

  toast('Slider saved ✓');
  await loadGrid();
}

// ═══════════════════════════════════════════════════════════════════
// Drag-and-drop reorder
// ═══════════════════════════════════════════════════════════════════
async function onDrop(e, targetPos) {
  const srcPos = e.dataTransfer.getData('srcPos');
  if (!srcPos || srcPos === targetPos) return;
  const srcBtn = buttons[srcPos];
  const tgtBtn = buttons[targetPos];
  if (!srcBtn || srcBtn.button_type === 'slider_occupied') return;

  const fid = folderStack.length ? folderStack.at(-1).folder_id : null;

  // Swap or move
  if (tgtBtn && tgtBtn.button_type !== 'slider_occupied') {
    // Swap
    await POST(`/api/profiles/${activeProfileId}/buttons`,
      { ...tgtBtn, position: srcPos, ...(fid?{folder_id:fid}:{}) });
    await POST(`/api/profiles/${activeProfileId}/buttons`,
      { ...srcBtn, position: targetPos, ...(fid?{folder_id:fid}:{}) });
  } else if (!tgtBtn) {
    // Move to empty cell
    await DEL(`/api/profiles/${activeProfileId}/buttons/${srcPos}${fid?'?folder_id='+fid:''}`);
    await POST(`/api/profiles/${activeProfileId}/buttons`,
      { ...srcBtn, position: targetPos, ...(fid?{folder_id:fid}:{}) });
  }
  await loadGrid();
  toast('Moved ✓');
}

// ═══════════════════════════════════════════════════════════════════
// Grid resize
// ═══════════════════════════════════════════════════════════════════
async function resizeGrid() {
  const newCols = parseInt(document.getElementById('cols-inp').value) || 5;
  const newRows = parseInt(document.getElementById('rows-inp').value) || 3;
  // Persist on the profile's folder (not global config)
  await PUT(`/api/profiles/${activeProfileId}`, { columns: newCols, rows: newRows });
  cols = newCols; rows = newRows;
  renderGrid();
}

// ═══════════════════════════════════════════════════════════════════
// Slider mode
// ═══════════════════════════════════════════════════════════════════
function toggleSliderMode() {
  sliderMode = !sliderMode;
  document.body.classList.toggle('slider-mode', sliderMode);
  const btn = document.getElementById('slider-mode-btn');
  btn.style.background = sliderMode ? 'var(--accent)' : '';
  btn.style.color      = sliderMode ? '#fff' : '';
  sliderStartPos = null;
}

function onSliderModeClick(pos) {
  if (!sliderMode) return;
  const [r, c] = pos.split('_').map(Number);
  if (sliderStartPos === null) {
    sliderStartPos = pos;
    document.querySelector(`[data-pos="${pos}"]`)?.classList.add('slider-candidate');
    return;
  }
  // Second click — create slider from sliderStartPos to pos (same column required)
  const [sr, sc] = sliderStartPos.split('_').map(Number);
  if (sc !== c) {
    toast('Slider must be in the same column', true);
    sliderStartPos = null;
    document.querySelectorAll('.slider-candidate').forEach(el =>
      el.classList.remove('slider-candidate'));
    return;
  }
  const startRow = Math.min(sr, r);
  const size = Math.abs(r - sr) + 1;
  sliderStartPos = null;
  document.querySelectorAll('.slider-candidate').forEach(el =>
    el.classList.remove('slider-candidate'));
  toggleSliderMode();

  // Open inspector pre-filled for slider at startRow_c
  selectedPos = `${startRow}_${sc}`;
  editSlider = { size, min_value:0, max_value:100, step:1,
                  label:'Slider', color:'#7c83fd', outputs:[] };
  editBtn = { position: selectedPos, button_type:'slider', slider_config: editSlider,
               label:'', actions:[], conditions:[] };
  openInspector('New Slider', true);
  populateSliderPanel(editSlider);
  document.getElementById('sl-size').value = size;
}

// ═══════════════════════════════════════════════════════════════════
// Context menu
// ═══════════════════════════════════════════════════════════════════
function showCtxMenu(e, pos) {
  ctxPos = pos;
  const menu = document.getElementById('ctx-menu');
  menu.style.display = 'block';
  menu.style.left = Math.min(e.clientX, window.innerWidth-160)+'px';
  menu.style.top  = Math.min(e.clientY, window.innerHeight-160)+'px';
}
document.addEventListener('click', () => {
  document.getElementById('ctx-menu').style.display = 'none';
});

window.ctxEdit = function() {
  if (ctxPos) onCellClick(ctxPos, buttons[ctxPos]);
};

window.ctxDuplicate = async function() {
  if (!ctxPos || !buttons[ctxPos]) return;
  // Find next empty cell
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const p = `${r}_${c}`;
      if (!buttons[p]) {
        const fid = folderStack.length ? folderStack.at(-1).folder_id : null;
        await POST(`/api/profiles/${activeProfileId}/buttons`,
          { ...buttons[ctxPos], position:p, ...(fid?{folder_id:fid}:{}) });
        await loadGrid();
        toast('Duplicated ✓');
        return;
      }
    }
  }
  toast('No empty cell found', true);
};

window.ctxMoveUp = async function() {
  if (!ctxPos) return;
  const [r,c] = ctxPos.split('_').map(Number);
  if (r === 0) return;
  const newPos = `${r-1}_${c}`;
  const fid = folderStack.length ? folderStack.at(-1).folder_id : null;
  const src = buttons[ctxPos], tgt = buttons[newPos];
  if (tgt) await POST(`/api/profiles/${activeProfileId}/buttons`,
    { ...tgt, position:ctxPos, ...(fid?{folder_id:fid}:{}) });
  else await DEL(`/api/profiles/${activeProfileId}/buttons/${ctxPos}${fid?'?folder_id='+fid:''}`);
  await POST(`/api/profiles/${activeProfileId}/buttons`,
    { ...src, position:newPos, ...(fid?{folder_id:fid}:{}) });
  await loadGrid();
};

window.ctxMoveDown = async function() {
  if (!ctxPos) return;
  const [r,c] = ctxPos.split('_').map(Number);
  if (r >= rows-1) return;
  const newPos = `${r+1}_${c}`;
  const fid = folderStack.length ? folderStack.at(-1).folder_id : null;
  const src = buttons[ctxPos], tgt = buttons[newPos];
  if (tgt) await POST(`/api/profiles/${activeProfileId}/buttons`,
    { ...tgt, position:ctxPos, ...(fid?{folder_id:fid}:{}) });
  else await DEL(`/api/profiles/${activeProfileId}/buttons/${ctxPos}${fid?'?folder_id='+fid:''}`);
  await POST(`/api/profiles/${activeProfileId}/buttons`,
    { ...src, position:newPos, ...(fid?{folder_id:fid}:{}) });
  await loadGrid();
};

window.ctxDelete = async function() {
  if (!ctxPos) return;
  const btn = buttons[ctxPos];
  if (!btn) return;
  if (!confirm(`Delete button at ${ctxPos}?`)) return;
  const fid = folderStack.length ? folderStack.at(-1).folder_id : null;
  if (btn.button_type === 'slider') {
    // Remove slider head + occupied
    const size = (btn.slider_config?.size) || 1;
    const [r,c] = ctxPos.split('_').map(Number);
    for (let i = 0; i < size; i++) {
      await DEL(`/api/profiles/${activeProfileId}/buttons/${r+i}_${c}${fid?'?folder_id='+fid:''}`);
    }
  } else {
    await DEL(`/api/profiles/${activeProfileId}/buttons/${ctxPos}${fid?'?folder_id='+fid:''}`);
  }
  await loadGrid();
  closeInspector();
  toast('Deleted ✓');
};

// ═══════════════════════════════════════════════════════════════════
// Folder navigation
// ═══════════════════════════════════════════════════════════════════
function navRoot() {
  folderStack = [];
  loadGrid();
  closeInspector();
}

function renderBreadcrumb() {
  const bc = document.getElementById('breadcrumb');
  let html = '<span onclick="navRoot()">Root</span>';
  for (let i = 0; i < folderStack.length; i++) {
    const item = folderStack[i];
    html += ` / <span onclick="navTo(${i})">${item.name}</span>`;
  }
  bc.innerHTML = html;
}

window.navTo = function(idx) {
  folderStack = folderStack.slice(0, idx+1);
  loadGrid();
  closeInspector();
};

function renderSubfolders() {
  const wrap = document.getElementById('subfolder-list');
  wrap.innerHTML = '';
  for (const sf of subFolders) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-ghost btn-sm';
    btn.textContent = '📁 ' + sf.name;
    btn.onclick = () => {
      folderStack.push({ folder_id: sf.folder_id, name: sf.name });
      loadGrid();
      closeInspector();
    };
    wrap.appendChild(btn);
  }
}

// ═══════════════════════════════════════════════════════════════════
// Utils
// ═══════════════════════════════════════════════════════════════════
function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function toast(msg, isErr=false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = isErr ? 'var(--danger)' : 'var(--accent)';
  t.style.display = 'block';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.style.display='none', 2500);
}

// ═══════════════════════════════════════════════════════════════════
// Keymap API endpoint (register in web_config)
// ═══════════════════════════════════════════════════════════════════
// /api/keymap/groups is handled server-side (see web_config.py)

boot();

// Re-render grid on window resize so squares stay square
window.addEventListener('resize', () => {
  if (cols > 0 && rows > 0) renderGrid();
});
</script>
</body>
</html>"""


def get_editor_html() -> str:
    return EDITOR_HTML