"""
WebSocket message protocol.
All messages are JSON objects with a "method" field.

Client → Server:
  CONNECT              { method, client_id, device_type, api_version }
  BUTTON_PRESS         { method, profile_id, folder_id, button_id, position }
  GET_BUTTONS          { method, profile_id, folder_id }
  GET_PROFILES         { method }
  SET_PROFILE          { method, profile_id }
  GET_VARIABLES        { method }
  SET_VARIABLE         { method, name, value, type }
  GET_ICONS            { method }
  GET_CONNECTED_CLIENTS{ method }
  PING                 { method }
  SLIDER_CHANGE        { method, slider_id, value }
  GET_SLIDERS          { method, folder_id? }
  ADD_SLIDER           { method, slider: {...}, folder_id? }
  REMOVE_SLIDER        { method, slider_id, folder_id? }
  UPDATE_SLIDER        { method, slider: {...}, folder_id? }

Server → Client:
  CONNECTED            { method, client_id }
  BUTTONS              { method, buttons: [...] }
  PROFILES             { method, profiles: [...], active_id }
  VARIABLES            { method, variables: [...] }
  VARIABLE_CHANGED     { method, variable: {...} }
  BUTTON_STATE         { method, button_id, state }
  CONNECTED_CLIENTS    { method, clients: [...] }
  ERROR                { method, message }
  PONG                 { method }
  SLIDER_UPDATE        { method, slider_id, value }

Client → Server (Slider):
  SLIDER_CHANGE        { method, slider_id, value, position?, profile_id?, folder_id? }
  UPDATE_AVAILABLE     { method, version, download_url }
  SLIDER_STATE         { method, slider_id, value }
  SLIDERS              { method, folder_id, sliders: [...] }
  SLIDER_ADDED         { method, slider: {...} }
  SLIDER_REMOVED       { method, slider_id }
  SLIDER_UPDATED       { method, slider: {...} }
"""
from __future__ import annotations
import json
from typing import Any


def encode(method: str, **kwargs: Any) -> str:
    return json.dumps({"method": method, **kwargs})


def decode(raw: str) -> dict:
    return json.loads(raw)
