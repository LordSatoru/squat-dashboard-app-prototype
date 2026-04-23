import json
import time
from collections import deque
from typing import Any, Dict, List, Optional

from config import GESTURE_STABLE_WINDOW

flex_buffers: Dict[str, Optional[List[Dict[str, Any]]]] = {
    "Flexible1": None,
    "Flexible2": None,
}

flex_status: Dict[str, str] = {
    "Flexible1": "DISCONNECTED",
    "Flexible2": "DISCONNECTED",
}

flex_last_raw_hex: Dict[str, Optional[str]] = {
    "Flexible1": None,
    "Flexible2": None,
}

acc_queue = deque(maxlen=200)
discovered_settings: Dict[int, bytes] = {}
polar_status = "DISCONNECTED"
last_csv_write_time = 0.0
start_monotonic = time.monotonic()

latest_state: Dict[str, Any] = {
    "ready": False,
    "hr": None,
    "polar": {"acc_x": None, "acc_y": None, "acc_z": None},
    "polar_status": "DISCONNECTED",
    "flex1_status": "DISCONNECTED",
    "flex2_status": "DISCONNECTED",
    "flex1": None,
    "flex2": None,
    "flex1_gesture": "UNKNOWN",
    "flex2_gesture": "UNKNOWN",
    "log": [],
    "last_update": None,
    "history": {
        "flex1": {
            "t": [],
            "ax": [], "ay": [], "az": [],
            "gx": [], "gy": [], "gz": [],
            "angle_x": [], "angle_y": [], "angle_mag_disabled": [],
        },
        "flex2": {
            "t": [],
            "ax": [], "ay": [], "az": [],
            "gx": [], "gy": [], "gz": [],
            "angle_x": [], "angle_y": [], "angle_mag_disabled": [],
        },
        "polar": {
            "t": [],
            "acc_x": [], "acc_y": [], "acc_z": [],
        },
    },
}

clients: set[Any] = set()
flex_gesture_windows: Dict[str, deque[str]] = {
    "Flexible1": deque(maxlen=GESTURE_STABLE_WINDOW),
    "Flexible2": deque(maxlen=GESTURE_STABLE_WINDOW),
}


def set_flex_status(name: str, status: str) -> None:
    flex_status[name] = status
    key = "flex1_status" if name == "Flexible1" else "flex2_status"
    latest_state[key] = status


async def broadcast_state() -> None:
    if not clients:
        return

    msg = json.dumps(latest_state)
    dead = []

    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)
