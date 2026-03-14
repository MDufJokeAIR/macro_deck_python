"""
registry.py — module-level singleton store for SliderState objects.

This module is always imported as
  macro_deck_python.plugins.builtin.analog_slider.registry
which is stable across dynamic plugin reloads. The plugin's main.py
and any test that imports SliderRegistry both end up pointing at the
same _SLIDERS dict and the same broadcast callback.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

logger = logging.getLogger("plugin.analog_slider.registry")

# ── module-level singletons (survives plugin hot-reload) ─────────────
_SLIDERS: Dict[str, Any]       = {}          # slider_id → SliderState
_LOCK    = threading.Lock()
_BROADCAST_CB: Optional[Callable[[str, float], None]] = None


def register(slider_id: str, state: Any) -> None:
    with _LOCK:
        old = _SLIDERS.get(slider_id)
        if old is not None:
            try: old.cleanup()
            except Exception: pass
        _SLIDERS[slider_id] = state


def unregister(slider_id: str) -> None:
    with _LOCK:
        state = _SLIDERS.pop(slider_id, None)
    if state is not None:
        try: state.cleanup()
        except Exception: pass


def get_state(slider_id: str) -> Optional[Any]:
    with _LOCK:
        return _SLIDERS.get(slider_id)


def all_slider_ids() -> List[str]:
    with _LOCK:
        return list(_SLIDERS.keys())


def set_broadcast_cb(cb: Optional[Callable[[str, float], None]]) -> None:
    global _BROADCAST_CB
    _BROADCAST_CB = cb


def get_broadcast_cb() -> Optional[Callable[[str, float], None]]:
    return _BROADCAST_CB


def on_change(slider_id: str, new_value: float) -> None:
    """
    Called when a client sends SLIDER_CHANGE.
    Applies throttle then dispatches outputs in a background thread.
    """
    with _LOCK:
        state = _SLIDERS.get(slider_id)
    if state is None:
        return

    with state._lock:
        state.current = state.clamp(new_value)
        now = time.monotonic()
        elapsed_ms = (now - state._last_apply) * 1000
        if state.throttle_ms > 0 and elapsed_ms < state.throttle_ms:
            if not state._pending:
                state._pending = True
                delay = (state.throttle_ms - elapsed_ms) / 1000.0
                threading.Timer(delay, _delayed_apply, args=(slider_id,)).start()
            return
        state._last_apply = now
        state._pending    = False
        value_snap        = state.current

    _dispatch(state, value_snap)


def _delayed_apply(slider_id: str) -> None:
    with _LOCK:
        state = _SLIDERS.get(slider_id)
    if state is None:
        return
    with state._lock:
        state._last_apply = time.monotonic()
        state._pending    = False
        value             = state.current
    _dispatch(state, value)


def _dispatch(state: Any, value: float) -> None:
    cb = _BROADCAST_CB

    def _run():
        state.apply_outputs(value)
        if cb:
            try: cb(state.slider_id, value)
            except Exception as exc:
                logger.error("broadcast cb: %s", exc)

    threading.Thread(target=_run, daemon=True).start()
