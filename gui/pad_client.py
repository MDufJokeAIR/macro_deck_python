"""
pad_client.py
=============
Returns the full single-file browser button-pad client HTML.

This is the page the Raspberry Pi (or any phone/tablet) opens in its browser
to use Macro Deck as a remote macro pad. It:
  1. Fetches /api/info to discover the WebSocket port
  2. Connects to ws://<same-host>:<ws_port> via WebSocket
  3. Sends CONNECT, then GET_BUTTONS
  4. Renders the button grid, handles BUTTONS / VARIABLE_CHANGED / BUTTON_STATE
  5. Sends BUTTON_PRESS on tap
  6. Sends SLIDER_CHANGE on slider drag
  7. Auto-reconnects on disconnect with exponential backoff
  8. Adapts layout to screen size (mobile-first CSS grid)
"""

PAD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<title>Macro Deck</title>
<style>
/* ── Reset & base ── */
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden;background:#0d0d1a;color:#e0e0e0;
  font-family:system-ui,-apple-system,sans-serif;touch-action:manipulation}

/* ── Status bar ── */
#status-bar{display:flex;align-items:center;justify-content:space-between;
  padding:6px 12px;background:#16213e;font-size:.75rem;gap:8px;min-height:32px}
#status-dot{width:8px;height:8px;border-radius:50%;background:#e05a5a;
  flex-shrink:0;transition:background .3s}
#status-dot.connected{background:#4ade80}
#status-dot.connecting{background:#facc15;animation:pulse 1s infinite}
#status-text{flex:1;color:#9ca3af}
#profile-select{background:#0f3460;color:#e0e0e0;border:1px solid #7c83fd44;
  border-radius:4px;padding:2px 6px;font-size:.75rem;max-width:140px}
#folder-nav{display:flex;align-items:center;gap:4px}
#btn-back{background:#0f3460;border:none;color:#7c83fd;border-radius:4px;
  padding:2px 8px;font-size:.75rem;cursor:pointer;display:none}

/* ── Grid wrapper: centers the fixed-size grid on screen ── */
#grid-wrap{display:flex;flex:1;align-items:center;justify-content:center;
  height:calc(100vh - 32px);overflow:hidden;max-width:100vw}

/* ── Grid: sized entirely by JS (square cells) ── */
#grid{display:grid;gap:5px;flex-shrink:0}

/* ── Button ── */
.macro-btn{
  background:#16213e;border:1px solid #1e2d4a;border-radius:8px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:4px;cursor:pointer;padding:6px;overflow:hidden;position:relative;
  transition:transform .08s,background .1s,border-color .1s;user-select:none;
  -webkit-user-select:none;min-height:0}
.macro-btn:active{transform:scale(.93)}
.macro-btn.state-on{background:#1e3a5f;border-color:#7c83fd}
.macro-btn.has-actions{border-color:#2a3a5a}
.macro-btn img.btn-icon{width:60%;height:60%;object-fit:contain;flex-shrink:0}
.macro-btn .btn-label{text-align:center;line-height:1.15;
  word-break:break-word;max-width:90%;overflow:hidden;
  flex-shrink:1;min-height:auto}
.macro-btn.empty{cursor:default;border-color:transparent;background:transparent}
.macro-btn.is-slider{background:#0f1f3a;border:1px solid #7c83fd55;
  cursor:default;border-radius:8px;padding:8px 4px;overflow:visible}

/* ── Press ripple ── */
.macro-btn::after{content:"";position:absolute;inset:0;border-radius:inherit;
  background:#7c83fd22;opacity:0;transition:opacity .15s}
.macro-btn.pressed::after{opacity:1}

/* ── Slider ── */
.slider-wrap{display:flex;flex-direction:column;align-items:center;
  height:100%;width:100%;gap:4px}
.slider-label{font-size:.6rem;color:#7c83fd;text-align:center;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:100%}
.slider-track-wrap{flex:1;display:flex;align-items:center;
  justify-content:center;width:100%;position:relative}
input[type=range].vslider{
  -webkit-appearance:none;appearance:none;
  writing-mode:vertical-lr;direction:rtl;  /* vertical, bottom=min */
  width:36px;height:100%;
  background:transparent;cursor:pointer}
input[type=range].vslider::-webkit-slider-thumb{
  -webkit-appearance:none;width:28px;height:14px;
  background:#7c83fd;border-radius:4px;margin-left:-9px}
input[type=range].vslider::-webkit-slider-runnable-track{
  width:10px;border-radius:5px;background:#1e2d4a;border:1px solid #7c83fd44}
input[type=range].vslider::-moz-range-thumb{
  width:28px;height:14px;background:#7c83fd;border-radius:4px;border:none}
input[type=range].vslider::-moz-range-track{
  width:10px;border-radius:5px;background:#1e2d4a}
/* Horizontal slider */
input[type=range].hslider{
  -webkit-appearance:none;appearance:none;
  width:100%;height:12px;
  background:transparent;cursor:pointer;
  vertical-align:middle;display:flex;align-items:center;
  pointer-events:auto}
input[type=range].hslider::-webkit-slider-thumb{
  -webkit-appearance:none;width:14px;height:28px;
  background:#7c83fd;border-radius:4px;cursor:pointer;
  margin-top:-8px;pointer-events:auto;touch-action:none}
input[type=range].hslider::-webkit-slider-runnable-track{
  height:10px;border-radius:5px;background:#1e2d4a;
  border:1px solid #7c83fd44;margin:1px 0;pointer-events:auto}
input[type=range].hslider::-moz-range-thumb{
  width:14px;height:28px;background:#7c83fd;
  border-radius:4px;border:none;cursor:pointer;
  margin-top:-9px;pointer-events:auto}
input[type=range].hslider::-moz-range-track{
  height:10px;border-radius:5px;background:#1e2d4a;
  margin:1px 0;border:1px solid #7c83fd44;pointer-events:auto}
.slider-value{font-size:.6rem;color:#9ca3af;font-variant-numeric:tabular-nums}

/* ── Sub-folder button ── */
.folder-btn{background:#0f3460;border:1px solid #7c83fd55;border-radius:8px;
  display:flex;align-items:center;justify-content:center;gap:4px;cursor:pointer;
  padding:8px 4px;font-size:.7rem;color:#7c83fd;grid-column:1/-1;
  transition:background .1s}
.folder-btn:active{background:#1a4a80}

/* ── Toast ── */
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);
  background:#7c83fd;color:#fff;padding:8px 16px;border-radius:20px;
  font-size:.8rem;display:none;z-index:100;white-space:nowrap}

/* ── Overlay (reconnecting) ── */
#overlay{position:fixed;inset:0;background:#0d0d1acc;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:12px;z-index:50}
#overlay.hidden{display:none}
.spinner{width:32px;height:32px;border:3px solid #7c83fd44;
  border-top-color:#7c83fd;border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
</style>
</head>
<body>

<div id="status-bar">
  <div id="status-dot"></div>
  <span id="status-text">Connecting…</span>
  <div id="folder-nav">
    <button id="btn-back" onclick="navBack()">← Back</button>
    <select id="profile-select" onchange="switchProfile(this.value)"></select>
    <a href="/editor" target="_blank" style="color:#7c83fd;font-size:.7rem;margin-left:4px;text-decoration:none">✏</a>
  </div>
</div>

<div id="grid-wrap"><div id="grid"></div></div>
<div id="toast"></div>

<div id="overlay">
  <div class="spinner"></div>
  <div style="color:#9ca3af;font-size:.85rem" id="overlay-text">Connecting to Macro Deck…</div>
</div>

<script>
console.log('🎛 Macro Deck PAD client loaded');

// ── State ──────────────────────────────────────────────────────────────
let ws         = null;
let clientId   = null;
let profiles   = [];
let activeProfileId = null;
let folderStack = [];           // stack of {folder_id, folder_name}
// Cache last render data so resize can replay renderGrid
let _lastButtons = [], _lastSubFolders = [], _lastSliderCells = {};
let currentColumns = 8;
let currentRows    = 4;
let variables  = {};            // name → value
let sliderValues = {};          // slider_id → current value
let reconnectDelay = 500;
let wsPort     = 8191;          // discovered via /api/info
let wsHost     = null;          // will be set on first connect, with fallback

// ── Boot ──────────────────────────────────────────────────────────────
console.log('📡 Booting Macro Deck PAD...');
(async () => {
  try {
    const info = await fetch('/api/info').then(r => r.json());
    wsPort = info.ws_port || 8191;
    console.log('📍 API info loaded, ws_port=' + wsPort);
  } catch(e) {
    console.warn('Could not fetch /api/info, defaulting ws_port=8191');
  }
  console.log('🔗 Calling connect()...');
  connect();

  // Re-render grid on resize or orientation change so squares recompute
  window.addEventListener('resize', () => {
    if (typeof currentColumns !== 'undefined' && currentColumns > 0) {
      renderGrid(_lastButtons, _lastSubFolders, _lastSliderCells);
    }
  });
  console.log('✅ Boot complete');
})();

// ── WebSocket ─────────────────────────────────────────────────────────
function connect() {
  console.log('🌐 connect() called, wsHost=' + wsHost);
  // On first connection, use the current hostname
  // If 127.0.0.1 fails, fallback to localhost
  if (!wsHost) {
    wsHost = window.location.hostname;
    console.log('📍 Set wsHost to ' + wsHost);
  }
  
  const url  = `ws://${wsHost}:${wsPort}`;
  console.log('🔌 Creating WebSocket: ' + url);
  setStatus('connecting', `Connecting to ${url}…`);

  ws = new WebSocket(url);

  ws.onopen = () => {
    console.log('✅ WebSocket connected!');
    reconnectDelay = 500;
    hideOverlay();
    send({ method: 'CONNECT', device_type: 'browser', api_version: 20 });
  };

  ws.onmessage = e => handleMessage(JSON.parse(e.data));

  ws.onclose = () => {
    console.log('❌ WebSocket closed');
    setStatus('disconnected', 'Disconnected — reconnecting…');
    showOverlay(`Reconnecting in ${(reconnectDelay/1000).toFixed(1)}s…`);
    setTimeout(() => { reconnectDelay = Math.min(reconnectDelay * 1.5, 10000); connect(); },
               reconnectDelay);
  };

  ws.onerror = err => {
    console.error('❌ WS error connecting to ' + wsHost, err);
    // On first connection error with 127.0.0.1, try localhost
    if (wsHost === '127.0.0.1' && reconnectDelay < 1000) {
      console.log('🔄 127.0.0.1 failed, trying localhost...');
      wsHost = '127.0.0.1';
      reconnectDelay = 100;  // Quick retry with new host
    }
  };
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

// ── Auto-fit font size ────────────────────────────────────────────────
// Offscreen canvas reused for overflow guard text measurements.
const _mc = (() => { const c = document.createElement('canvas'); return c.getContext('2d'); })();

/**
 * Return the largest font size (px) where the longest word in `words`
 * fits within `availPx` pixels.  Used only as a safety cap to prevent
 * very long words from overflowing the button — the primary sizing is
 * screen-proportional (see screenProportionalFontSize).
 */
function fitFontSize(words, availPx) {
  if (!words.length || availPx <= 0) return 99999;
  const target = availPx * 0.88;
  let lo = 5, hi = availPx;
  for (let i = 0; i < 18; i++) {
    const mid = (lo + hi) * 0.5;
    _mc.font = `600 ${mid}px system-ui,-apple-system,sans-serif`;
    let maxW = 0;
    for (const w of words) {
      const m = _mc.measureText(w).width;
      if (m > maxW) maxW = m;
    }
    if (maxW <= target) lo = mid; else hi = mid;
  }
  return Math.floor(lo);
}

/**
 * Compute the base font size for auto-fit labels from the cell size.
 *
 * Font size scales linearly with the cell (which itself scales with the
 * device screen size), so the same label looks proportionally identical
 * on a phone, a tablet, and a desktop — regardless of word length.
 *
 * The factor 0.22 is chosen so that on a typical 5×3 phone grid
 * (~70 px cells) the font is ~15 px: readable without being huge.
 * A safety cap via fitFontSize() prevents very long words from
 * overflowing the button edge.
 */
function screenProportionalFontSize(words, cellSize) {
  const proportional = Math.max(7, Math.round(cellSize * 0.22));
  const cap = fitFontSize(words, cellSize - 12);   // prevent overflow
  return Math.min(proportional, cap);
}

// ── Message handling ──────────────────────────────────────────────────
function handleMessage(msg) {
  switch(msg.method) {

    case 'CONNECTED':
      clientId = msg.client_id;
      setStatus('connected', `Connected • ${clientId.slice(0,8)}`);
      send({ method: 'GET_PROFILES' });
      send({ method: 'GET_VARIABLES' });
      requestButtons();
      break;

    case 'BUTTONS':
      currentColumns  = msg.columns || 8;
      currentRows     = msg.rows    || 4;
      renderGrid(msg.buttons || [], msg.sub_folders || [], msg.slider_cells || {});
      break;

    case 'PROFILES':
      profiles = msg.profiles || [];
      activeProfileId = msg.active_id;
      renderProfileSelect();
      break;

    case 'VARIABLES':
      (msg.variables || []).forEach(v => { variables[v.name] = v.value; });
      break;

    case 'VARIABLE_CHANGED':
      if (msg.variable) variables[msg.variable.name] = msg.variable.value;
      // Re-render labels that use this variable.
      // Auto-fit spans (data-autofit) keep their word-per-line layout.
      document.querySelectorAll('[data-label-template]').forEach(el => {
        const text = renderTemplate(el.dataset.labelTemplate);
        if (el.dataset.autofit) {
          el.textContent = text.trim().split(/\s+/).filter(Boolean).join('\n');
        } else {
          el.textContent = text;
        }
      });
      // Update slider values if they bind to this variable
      document.querySelectorAll('[data-slider-variable]').forEach(el => {
        if (el.dataset.sliderVariable === msg.variable.name) {
          const input = el.querySelector('input[type=range]');
          if (input) {
            const val = Math.max(0, Math.min(100, Number(msg.variable.value) || 0));
            input.value = val;
            const valEl = el.querySelector('.slider-value');
            if (valEl) valEl.textContent = Math.round(val) + '%';
          }
        }
      });
      break;

    case 'BUTTON_STATE':
      const btnEl = document.querySelector(`[data-button-id="${msg.button_id}"]`);
      if (btnEl) {
        btnEl.classList.toggle('state-on', !!msg.state);
      }
      break;

    case 'SLIDER_STATE':
      sliderValues[msg.slider_id] = msg.value;
      const inp = document.querySelector(`[data-slider-id="${msg.slider_id}"] input`);
      if (inp) {
        inp.value = msg.value;
        const valEl = inp.closest('.slider-wrap')?.querySelector('.slider-value');
        if (valEl) valEl.textContent = formatSliderVal(msg.value);
      }
      break;

    case 'SLIDER_ADDED':
    case 'SLIDER_REMOVED':
    case 'SLIDER_UPDATED':
      requestButtons();   // simplest: re-fetch the whole layout
      break;

    case 'PONG': break;

    case 'ERROR':
      console.warn('Server error:', msg.message);
      showToast('⚠ ' + msg.message, true);
      break;
  }
}

// ── Grid rendering ────────────────────────────────────────────────────
function renderGrid(buttons, subFolders, sliderCells) {
  // Cache for resize replay
  _lastButtons = buttons; _lastSubFolders = subFolders; _lastSliderCells = sliderCells;

  const grid = document.getElementById('grid');
  grid.innerHTML = '';

  // ── Compute square cell size ──────────────────────────────────────
  const GAP     = 5;
  const PADDING = 8;   // breathing room each side
  const availW  = window.innerWidth  - PADDING * 2;
  const availH  = window.innerHeight - 32 - PADDING * 2; // subtract status bar
  // Use (cols-1) gaps between cells, not (cols+1)
  const cellW   = Math.floor((availW - GAP * (currentColumns - 1)) / currentColumns);
  const cellH   = Math.floor((availH - GAP * (currentRows    - 1)) / currentRows);
  // Square = smallest axis; no hard minimum so many buttons still fit on screen
  const cell    = Math.max(20, Math.min(cellW, cellH));

  // Apply to grid: fixed pixel columns/rows so it doesn't stretch
  grid.style.gridTemplateColumns = `repeat(${currentColumns}, ${cell}px)`;
  grid.style.gridTemplateRows    = `repeat(${currentRows},    ${cell}px)`;
  grid.style.gap                 = `${GAP}px`;

  // Build lookup: "row_col" → button
  const btnMap = {};
  (buttons || []).forEach(b => { btnMap[b.position] = b; });

  // Build lookup: "row_col" → slider_id
  const sliderMap = sliderCells || {};

  // Collect unique slider_ids to avoid duplicate cells
  const renderedSliders = new Set();

  for (let r = 0; r < currentRows; r++) {
    for (let c = 0; c < currentColumns; c++) {
      const pos = `${r}_${c}`;
      const btn = btnMap[pos];
      const sliderId = sliderMap[pos];

      // Skip if this cell is occupied by a new-style slider
      if (btn && btn.slider_parent_position) {
        continue;
      }

      // Legacy slider cell from old system
      if (sliderId) {
        if (renderedSliders.has(sliderId)) {
          continue;
        }
        let h = 0;
        while (sliderMap[`${r + h}_${c}`] === sliderId) h++;
        renderedSliders.add(sliderId);
        const sliderEl = makeSliderCell(sliderId, r, c, h, sliderCells);
        grid.appendChild(sliderEl);
      } 
      // New-style slider button
      else if (btn && btn.is_slider) {
        if (renderedSliders.has(btn.button_id)) {
          continue;
        }
        renderedSliders.add(btn.button_id);
        const sliderEl = makeSliderButton(btn, cell, r, c);
        grid.appendChild(sliderEl);
      } 
      // Regular button
      else if (btn) {
        grid.appendChild(makeButton(btn, cell));
      } 
      // Empty cell
      else {
        const empty = document.createElement('div');
        empty.className = 'macro-btn empty';
        grid.appendChild(empty);
      }
    }
  }

  // Sub-folder navigation buttons (append below grid)
  (subFolders || []).forEach(sf => {
    const btn = document.createElement('div');
    btn.className = 'folder-btn';
    btn.textContent = '📁 ' + sf.name;
    btn.onclick = () => navInto(sf.folder_id, sf.name);
    grid.appendChild(btn);
  });

  // Update back button visibility
  document.getElementById('btn-back').style.display =
    folderStack.length > 0 ? '' : 'none';
}

/**
 * Create a slider button element.
 * Renders a horizontal or vertical range input with label and value display.
 * Spans multiple cells if slider_size > 1.
 */
function makeSliderButton(btn, cellSize, row, col) {
  const el = document.createElement('div');
  el.className = 'macro-btn is-slider';
  el.dataset.buttonId = btn.button_id;
  el.dataset.sliderVariable = btn.slider_variable || '';
  el.style.background = btn.background_color || '#0f1f3a';
  el.style.borderColor = '#7c83fd55';
  
  // Set grid position and span
  const size = btn.slider_size || 1;
  const orientation = btn.slider_orientation || 'vertical';
  el.style.gridColumn = orientation === 'horizontal' 
    ? `${col + 1} / span ${size}` 
    : `${col + 1}`;
  el.style.gridRow = orientation === 'vertical'
    ? `${row + 1} / span ${size}`
    : `${row + 1}`;

  const wrap = document.createElement('div');
  let isVertical = orientation === 'vertical';
  wrap.className = 'slider-wrap';
  wrap.style.flexDirection = isVertical ? 'column' : 'row';
  wrap.style.justifyContent = isVertical ? 'flex-start' : 'center';

  // Label
  if (btn.label) {
    const label = document.createElement('div');
    label.className = 'slider-label';
    label.style.color = btn.label_color || '#ffffff';
    label.textContent = btn.label;
    wrap.appendChild(label);
  }

  // Track wrapper
  const trackWrap = document.createElement('div');
  trackWrap.className = 'slider-track-wrap';
  trackWrap.style.flex = '1';
  trackWrap.style.display = 'flex';
  trackWrap.style.alignItems = isVertical ? 'center' : 'center';
  trackWrap.style.justifyContent = 'center';
  trackWrap.style.minHeight = isVertical ? '60px' : '60px';
  trackWrap.style.minWidth = isVertical ? 'auto' : '60px';
  trackWrap.style.pointerEvents = 'auto';
  trackWrap.style.overflow = 'visible';

  // Range input
  const input = document.createElement('input');
  input.type = 'range';
  input.className = isVertical ? 'vslider' : 'hslider';
  input.min = '0';
  input.max = '100';
  input.step = '1';
  input.value = '50';
  input.style.cursor = 'pointer';
  
  // Apply responsive sizing via inline styles
  if (isVertical) {
    input.style.width = '36px';
    input.style.height = '100%';
  } else {
    input.style.width = '100%';
    input.style.height = '12px';
  }

  // Send SET_VARIABLE when slider changes
  const sendSliderValue = () => {
    const val = parseFloat(input.value) || 0;
    console.log(`[Slider] Value changed to ${val}, variable: ${btn.slider_variable}`);
    if (btn.slider_variable) {
      send({ 
        method: 'SET_VARIABLE', 
        name: btn.slider_variable, 
        value: val,
        type: 'Float'
      });
    }
  };
  input.addEventListener('input', sendSliderValue);
  input.addEventListener('change', sendSliderValue);
  input.addEventListener('mouseup', sendSliderValue);

  // Value display
  const valEl = document.createElement('div');
  valEl.className = 'slider-value';
  valEl.style.color = '#7c83fd';
  valEl.textContent = '50%';
  input.addEventListener('input', () => {
    valEl.textContent = Math.round(input.value) + '%';
  });

  trackWrap.appendChild(input);
  wrap.appendChild(trackWrap);
  wrap.appendChild(valEl);
  el.appendChild(wrap);

  return el;
}

function makeButton(btn, cellSize) {
  // If this button is configured as a slider, render as slider instead
  if (btn.is_slider) {
    return makeSliderButton(btn, cellSize);
  }

  const el = document.createElement('div');
  el.className = 'macro-btn' +
    (btn.state ? ' state-on' : '') +
    (btn.has_actions ? ' has-actions' : '');
  el.dataset.buttonId = btn.button_id;

  // Icon
  if (btn.icon) {
    const img = document.createElement('img');
    img.className = 'btn-icon';
    img.src = btn.icon.startsWith('data:') ? btn.icon : `data:image/png;base64,${btn.icon}`;
    img.onerror = () => img.remove();
    el.appendChild(img);
  }

  // Label
  if (btn.label) {
    const span = document.createElement('span');
    span.className = 'btn-label';
    span.style.color = btn.label_color || '#ffffff';
    span.dataset.labelTemplate = btn.label;

    if (btn.label_font_size == null && cellSize > 0) {
      // ── Auto-fit mode ──────────────────────────────────────────────
      // Font size is proportional to the cell size (i.e. to the device
      // screen), so every button on the same client shows the same size
      // text regardless of how many characters it contains.
      // Words are laid one-per-line; fitFontSize() caps the size so that
      // no word overflows the button width.
      const text  = renderTemplate(btn.label);
      const words = text.trim().split(/\s+/).filter(Boolean);
      const fs    = screenProportionalFontSize(words, cellSize);
      span.style.fontSize   = fs + 'px';
      span.style.lineHeight = '1.2';
      span.style.whiteSpace = 'pre-line';
      span.dataset.autofit  = '1';
      span.textContent = words.join('\n');
    } else {
      // ── Explicit size mode ─────────────────────────────────────────
      if (btn.label_font_size) {
        span.style.fontSize = btn.label_font_size + 'px';
      } else {
        // Fallback when cellSize unknown (shouldn't happen in normal flow)
        span.style.fontSize = 'clamp(8px, 2vw, 14px)';
      }
      span.textContent = renderTemplate(btn.label);
    }
    el.appendChild(span);
  }

  // Background colour
  if (btn.background_color && btn.background_color !== '#000000') {
    el.style.background = btn.background_color;
  }

  // Touch / click
  el.addEventListener('pointerdown', () => el.classList.add('pressed'));
  el.addEventListener('pointerup',   () => { el.classList.remove('pressed'); pressButton(btn); });
  el.addEventListener('pointerleave',() => el.classList.remove('pressed'));

  return el;
}

function makeSliderCell(sliderId, row, col, height, sliderCells) {
  // Find the slider definition — stored in the server's BUTTONS response
  // We only have slider_id here; fetch full slider data from the last SLIDERS msg
  // For now, use stored sliderValues and defaults
  const el = document.createElement('div');
  el.className = 'macro-btn is-slider';
  el.dataset.sliderId = sliderId;
  el.style.gridColumn = `${col + 1}`;
  el.style.gridRow    = `${row + 1} / span ${height}`;

  const wrap = document.createElement('div');
  wrap.className = 'slider-wrap';

  const label = document.createElement('div');
  label.className = 'slider-label';
  label.textContent = '⎸';   // placeholder — updated when SLIDERS arrives

  const trackWrap = document.createElement('div');
  trackWrap.className = 'slider-track-wrap';

  const input = document.createElement('input');
  input.type  = 'range';
  input.className = 'vslider';
  input.min   = '0';
  input.max   = '100';
  input.step  = '1';
  input.value = sliderValues[sliderId] ?? '50';

  // Send SLIDER_CHANGE on input (continuous) and change (final)
  const sendSlider = () => {
    send({ method: 'SLIDER_CHANGE', slider_id: sliderId, value: parseFloat(input.value) });
  };
  input.addEventListener('input',  sendSlider);
  input.addEventListener('change', sendSlider);

  const valEl = document.createElement('div');
  valEl.className = 'slider-value';
  valEl.textContent = formatSliderVal(input.value);
  input.addEventListener('input', () => { valEl.textContent = formatSliderVal(input.value); });

  trackWrap.appendChild(input);
  wrap.appendChild(label);
  wrap.appendChild(trackWrap);
  wrap.appendChild(valEl);
  el.appendChild(wrap);

  // Fetch full slider details to fill in label/range
  fetchSliderDetails(sliderId, el, input, label, valEl);

  return el;
}

function fetchSliderDetails(sliderId, el, input, labelEl, valEl) {
  if (!activeProfileId) return;
  fetch(`/api/profiles/${activeProfileId}/sliders`)
    .then(r => r.json())
    .then(sliders => {
      const s = sliders.find(x => x.slider_id === sliderId);
      if (!s) return;
      input.min   = String(s.min_value ?? 0);
      input.max   = String(s.max_value ?? 100);
      input.step  = String(s.step      ?? 1);
      input.value = String(s.current_value ?? s.initial_value ?? 50);
      input.style.accentColor  = s.track_color  || '#7c83fd';
      labelEl.textContent      = s.label || '⎸';
      labelEl.style.color      = s.label_color  || '#7c83fd';
      valEl.textContent        = formatSliderVal(input.value);
    })
    .catch(() => {});
}

function formatSliderVal(v) {
  const n = parseFloat(v);
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

// ── Actions ───────────────────────────────────────────────────────────
function pressButton(btn) {
  send({ method: 'BUTTON_PRESS', position: btn.position, button_id: btn.button_id });
}

function switchProfile(profileId) {
  folderStack = [];
  activeProfileId = profileId;
  send({ method: 'SET_PROFILE', profile_id: profileId });
}

function navInto(folderId, folderName) {
  folderStack.push({ folder_id: folderId, folder_name: folderName });
  requestButtons();
}

function navBack() {
  if (folderStack.length > 0) folderStack.pop();
  requestButtons();
}

function requestButtons() {
  const fid = folderStack.length > 0 ? folderStack[folderStack.length-1].folder_id : undefined;
  send({ method: 'GET_BUTTONS', ...(fid ? { folder_id: fid } : {}) });
}

// ── Template renderer (mirrors server-side template.py) ───────────────
function renderTemplate(tpl) {
  if (!tpl) return '';
  return tpl.replace(/\{([^}]+)\}/g, (match, expr) => {
    const [varPart, fmtSpec] = expr.split(':');
    const val = variables[varPart.trim()];
    if (val === undefined) return match;
    if (fmtSpec) {
      // Basic float format: .2f etc.
      const m = fmtSpec.match(/\.(\d+)f/);
      if (m) return parseFloat(val).toFixed(parseInt(m[1]));
    }
    return String(val);
  });
}

// ── Profile select ────────────────────────────────────────────────────
function renderProfileSelect() {
  const sel = document.getElementById('profile-select');
  sel.innerHTML = profiles.map(p =>
    `<option value="${p.id}" ${p.id === activeProfileId ? 'selected' : ''}>${p.name}</option>`
  ).join('');
}

// ── Status helpers ────────────────────────────────────────────────────
function setStatus(state, text) {
  const dot  = document.getElementById('status-dot');
  const span = document.getElementById('status-text');
  dot.className  = 'status-dot ' + state;
  dot.id         = 'status-dot';   // keep id
  dot.classList.add(state === 'connected' ? 'connected'
                  : state === 'connecting' ? 'connecting' : '');
  span.textContent = text;
}

function showOverlay(text) {
  document.getElementById('overlay').classList.remove('hidden');
  document.getElementById('overlay-text').textContent = text;
}
function hideOverlay() {
  document.getElementById('overlay').classList.add('hidden');
}

function showToast(msg, isError=false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.style.background = isError ? '#e05a5a' : '#7c83fd';
  t.style.display = 'block';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.display = 'none'; }, 3000);
}
</script>
</body>
</html>"""


def get_pad_html() -> str:
    return PAD_HTML