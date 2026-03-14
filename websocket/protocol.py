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
  UPDATE_AVAILABLE     { method, version, download_url }
"""
from __future__ import annotations
import json
from typing import Any


def encode(method: str, **kwargs: Any) -> str:
    return json.dumps({"method": method, **kwargs})


def decode(raw: str) -> dict:
    """Decode JSON message and normalize field names for C# client compatibility.
    
    Handles both PascalCase (C# format) and lowercase (Python format) field names:
    - Method → method
    - Client-Id → client_id
    - Button-Id → button_id
    - Profile-Id → profile_id
    - Folder-Id → folder_id
    """
    data = json.loads(raw)
    normalized = {}
    
    for key, value in data.items():
        # Convert PascalCase/kebab-case to lowercase
        # Method → method
        # Client-Id → client_id  
        # Button-Id → button_id
        normalized_key = key.lower().replace("-", "_")
        normalized[normalized_key] = value
    
    return normalized
