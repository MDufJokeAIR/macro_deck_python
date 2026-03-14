"""
slider_manager.py
=================
Global registry of all active SliderWidgets and their AnalogOutput engines.

SliderManager is the bridge between:
  - The WebSocket server   (receives SLIDER_CHANGE from clients)
  - The Profile / Folder   (where sliders are stored)
  - The AnalogOutput layer (produces actual key / variable / axis events)

Thread-safety: all mutating operations are protected by _lock.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional

from macro_deck_python.models.slider import SliderWidget

logger = logging.getLogger("plugin.analog_slider.manager")


class SliderManager:
    """Singleton-style class (all class-level state)."""

    _lock    = threading.Lock()
    _outputs: Dict[str, "AnalogOutput"] = {}   # slider_id → AnalogOutput
    # Change listeners: (slider_id, new_value) — for WebSocket broadcast
    _listeners: List[Callable[[str, float], None]] = []

    # ── registration ──────────────────────────────────────────────────

    @classmethod
    def register(cls, slider: SliderWidget) -> None:
        """
        Start tracking a slider and create its AnalogOutput engine.
        Safe to call on an already-registered slider (re-initialises it).
        """
        from macro_deck_python.plugins.builtin.analog_slider.analog_output import AnalogOutput
        with cls._lock:
            # Tear down old engine if replacing
            old = cls._outputs.pop(slider.slider_id, None)
            if old:
                old.stop()
            engine = AnalogOutput(slider)
            cls._outputs[slider.slider_id] = engine
            logger.info("Registered slider %s (mode=%s)", slider.label, slider.mode)

    @classmethod
    def unregister(cls, slider_id: str) -> None:
        with cls._lock:
            engine = cls._outputs.pop(slider_id, None)
        if engine:
            engine.stop()
            logger.info("Unregistered slider %s", slider_id[:8])

    @classmethod
    def unregister_all(cls) -> None:
        with cls._lock:
            engines = list(cls._outputs.values())
            cls._outputs.clear()
        for eng in engines:
            eng.stop()

    # ── value change (called by WebSocket handler) ────────────────────

    @classmethod
    def apply_change(cls, slider_id: str, new_value: float,
                     folder=None) -> Optional[SliderWidget]:
        """
        Process a SLIDER_CHANGE message from a client.
        Updates the slider's current_value, fires the AnalogOutput, and
        persists the new value to the profile.

        Returns the updated SliderWidget, or None if slider not found.
        """
        # Find slider in registry
        with cls._lock:
            engine = cls._outputs.get(slider_id)
        if engine is None:
            # Try to find and re-register from the active profile
            slider = cls._find_in_profile(slider_id)
            if slider is None:
                logger.warning("SLIDER_CHANGE for unknown slider %s", slider_id[:8])
                return None
            cls.register(slider)
            with cls._lock:
                engine = cls._outputs.get(slider_id)

        slider = engine.slider
        old_value = slider.current_value
        engine.on_value_change(new_value, old_value)

        # Notify WebSocket listeners (for broadcasting state to other clients)
        for cb in list(cls._listeners):
            try:
                cb(slider_id, slider.current_value)
            except Exception as exc:
                logger.error("Slider listener error: %s", exc)

        return slider

    # ── listener registration ────────────────────────────────────────

    @classmethod
    def on_change(cls, cb: Callable[[str, float], None]) -> None:
        cls._listeners.append(cb)

    # ── load all sliders from all profiles ───────────────────────────

    @classmethod
    def load_from_profiles(cls) -> None:
        """
        Called at startup. Register an AnalogOutput for every slider
        found in every loaded profile.
        """
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.utils.folder_utils import find_folder

        for profile in ProfileManager.get_all():
            cls._register_folder_sliders(profile.folder)

    @classmethod
    def _register_folder_sliders(cls, folder) -> None:
        for slider in folder.sliders.values():
            cls.register(slider)
        for sub in folder.sub_folders:
            cls._register_folder_sliders(sub)

    # ── profile lookup ────────────────────────────────────────────────

    @classmethod
    def _find_in_profile(cls, slider_id: str) -> Optional[SliderWidget]:
        from macro_deck_python.services.profile_manager import ProfileManager

        def _search(folder):
            if slider_id in folder.sliders:
                return folder.sliders[slider_id]
            for sub in folder.sub_folders:
                r = _search(sub)
                if r: return r
            return None

        for profile in ProfileManager.get_all():
            r = _search(profile.folder)
            if r: return r
        return None

    # ── CRUD helpers (used by REST API) ──────────────────────────────

    @classmethod
    def add_slider(cls, slider: SliderWidget, profile_id: str,
                   folder_id: Optional[str] = None) -> bool:
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.utils.folder_utils import find_folder

        profile = ProfileManager.get_profile(profile_id)
        if not profile:
            return False
        folder = (find_folder(profile.folder, folder_id)
                  if folder_id else profile.folder) or profile.folder

        # Validate: check height ≥ 1 and slot not already occupied
        if slider.height < 1:
            slider.height = 1
        occupied = set(folder.sliders.keys())
        for sid, sw in folder.sliders.items():
            if sid != slider.slider_id:
                for cell in sw.occupied_cells:
                    if cell in set(slider.occupied_cells):
                        logger.warning("Slider %s overlaps with existing %s",
                                       slider.slider_id[:8], sid[:8])

        folder.sliders[slider.slider_id] = slider
        cls.register(slider)
        ProfileManager.save()
        return True

    @classmethod
    def remove_slider(cls, slider_id: str, profile_id: str,
                      folder_id: Optional[str] = None) -> bool:
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.utils.folder_utils import find_folder

        profile = ProfileManager.get_profile(profile_id)
        if not profile:
            return False
        folder = (find_folder(profile.folder, folder_id)
                  if folder_id else profile.folder) or profile.folder

        if slider_id not in folder.sliders:
            return False
        del folder.sliders[slider_id]
        cls.unregister(slider_id)
        ProfileManager.save()
        return True

    @classmethod
    def update_slider(cls, slider: SliderWidget, profile_id: str,
                      folder_id: Optional[str] = None) -> bool:
        from macro_deck_python.services.profile_manager import ProfileManager
        from macro_deck_python.utils.folder_utils import find_folder

        profile = ProfileManager.get_profile(profile_id)
        if not profile:
            return False
        folder = (find_folder(profile.folder, folder_id)
                  if folder_id else profile.folder) or profile.folder

        if slider.slider_id not in folder.sliders:
            return False
        folder.sliders[slider.slider_id] = slider
        cls.register(slider)   # re-init engine with new config
        ProfileManager.save()
        return True
