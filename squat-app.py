import asyncio
import csv
import json
import math
import os
import struct
import time
from collections import Counter, deque
from typing import Any, Dict, List, Optional, Tuple

from bleak import BleakClient
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from datetime import datetime

# ================= FLEXIBLE =================
DEVICES = {
    "Flexible1": "F4:72:03:60:13:3A",
    "Flexible2": "F4:D0:89:62:0F:F3",
}

DATA_UUID = "12345678-1234-5678-1234-56789ABCDEF1"
CTRL_UUID = "12345678-1234-5678-1234-56789ABCDEF2"

FLEX_CONNECT_TIMEOUT = 5.0
FLEX_RETRY_DELAY = 3.0
FLEX_KEEPALIVE_SLEEP = 1.0
HISTORY_MAXLEN = 300
GESTURE_THRESHOLD_DEG = 5.0
GESTURE_DIAGONAL_THRESHOLD_DEG = 5.0
GESTURE_STABLE_WINDOW = 3

# Axis calibration: fix left/right interpretation when sensor mounting is mirrored.
# -1 means invert the reported axis before gesture detection / dashboard display.
FLEX_AXIS_SIGN: Dict[str, Dict[str, int]] = {
    "Flexible1": {"x": -1, "y": 1},
    "Flexible2": {"x": -1, "y": 1},
}

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

# ================= POLAR =================
POLAR_ADDR = "A0:9E:1A:E3:AA:65"
PMD_CONTROL = "FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8"
PMD_DATA = "FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8"
HR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
POLAR_ACC_DIVISOR = 1000.0  # convert mg -> g

acc_queue = deque(maxlen=200)
discovered_settings: Dict[int, bytes] = {}
polar_status = "DISCONNECTED"

# ================= CSV =================
CSV_FILE = f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
CSV_WRITE_INTERVAL_SEC = 0.05
last_csv_write_time = 0.0

# ================= SHARED STATE =================
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

clients: set[WebSocket] = set()
start_monotonic = time.monotonic()
flex_gesture_windows: Dict[str, deque[str]] = {
    "Flexible1": deque(maxlen=GESTURE_STABLE_WINDOW),
    "Flexible2": deque(maxlen=GESTURE_STABLE_WINDOW),
}


# ================= HELPERS =================
def init_csv() -> None:
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp_iso", "date", "time",
                "time_s", "hr",
                "polar_x", "polar_y", "polar_z",
                "f1_ts", "f1_ax", "f1_ay", "f1_az", "f1_gx", "f1_gy", "f1_gz",
                "f1_bend", "f1_stretch", "f1_ads2_x", "f1_ads2_y", "f1_angle_x", "f1_angle_y", "f1_gesture",
                "f2_ts", "f2_ax", "f2_ay", "f2_az", "f2_gx", "f2_gy", "f2_gz",
                "f2_bend", "f2_stretch", "f2_ads2_x", "f2_ads2_y", "f2_angle_x", "f2_angle_y", "f2_gesture",
            ])


def save_row_to_csv(elapsed: float, hr: Optional[int], polar_xyz: Optional[Tuple[float, float, float]],
                    f1: Optional[Dict[str, Any]], f2: Optional[Dict[str, Any]]) -> None:
    now = datetime.now()
    timestamp_iso = now.isoformat(timespec="milliseconds")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S.%f")[:-3]

    px, py, pz = polar_xyz if polar_xyz else (None, None, None)
    f1 = f1 or {}
    f2 = f2 or {}

    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp_iso, date_str, time_str,
            round(elapsed, 3), hr,
            px, py, pz,

            f1.get("ts"), f1.get("ax"), f1.get("ay"), f1.get("az"),
            f1.get("gx"), f1.get("gy"), f1.get("gz"),
            f1.get("bend"), f1.get("stretch"), f1.get("ads2_x"), f1.get("ads2_y"),
            f1.get("angle_x"), f1.get("angle_y"), f1.get("gesture"),

            f2.get("ts"), f2.get("ax"), f2.get("ay"), f2.get("az"),
            f2.get("gx"), f2.get("gy"), f2.get("gz"),
            f2.get("bend"), f2.get("stretch"), f2.get("ads2_x"), f2.get("ads2_y"),
            f2.get("angle_x"), f2.get("angle_y"), f2.get("gesture"),
        ])


def push_log(line: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    latest_state["log"].append(f"[{stamp}] {line}")
    latest_state["log"] = latest_state["log"][-40:]
    print(line)


def set_flex_status(name: str, status: str) -> None:
    flex_status[name] = status
    key = "flex1_status" if name == "Flexible1" else "flex2_status"
    latest_state[key] = status


def apply_flex_axis_calibration(sample: Dict[str, Any], name: str) -> Dict[str, Any]:
    calibrated = dict(sample)
    axis = FLEX_AXIS_SIGN.get(name, {"x": 1, "y": 1})

    if calibrated.get("ads2_x") is not None:
        calibrated["ads2_x"] = round(float(calibrated["ads2_x"]) * axis.get("x", 1), 1)
    if calibrated.get("ads2_y") is not None:
        calibrated["ads2_y"] = round(float(calibrated["ads2_y"]) * axis.get("y", 1), 1)

    return calibrated


def compute_flex_angles(sample: Dict[str, Any]) -> Dict[str, Optional[float]]:
    angle_x = sample.get("ads2_x")
    angle_y = sample.get("ads2_y")

    if angle_x is None or angle_y is None:
        return {"angle_x": None, "angle_y": None, "angle_mag_disabled": None}

    try:
        angle_mag_disabled = math.hypot(angle_x, angle_y)
    except Exception:
        return {"angle_x": None, "angle_y": None, "angle_mag_disabled": None}

    return {
        "angle_x": round(float(angle_x), 1),
        "angle_y": round(float(angle_y), 1),
        "angle_mag_disabled": round(float(angle_mag_disabled), 1),
    }


def summarize_flex(sample: Optional[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    if not sample:
        return None

    calibrated = apply_flex_axis_calibration(sample, name)
    angles = compute_flex_angles(calibrated)
    out = dict(calibrated)
    out.update(angles)
    return out


def format_flex_full(sample: Optional[Dict[str, Any]], short_name: str, name: str) -> str:
    if not sample:
        return f"{short_name}: -"

    calibrated = apply_flex_axis_calibration(sample, name)
    enriched = dict(calibrated)
    enriched.update(compute_flex_angles(calibrated))
    return f"{short_name}: {enriched}"


def format_polar_log_line() -> str:
    elapsed = time.monotonic() - start_monotonic
    x = latest_state["polar"].get("acc_x")
    y = latest_state["polar"].get("acc_y")
    z = latest_state["polar"].get("acc_z")
    hr = latest_state.get("hr")
    return f"{elapsed:.3f}s | HR: {hr if hr is not None else '-'} | ACC X:{x}g Y:{y}g Z:{z}g"


def detect_gesture(angle_x: Optional[float], angle_y: Optional[float]) -> str:
    if angle_x is None or angle_y is None:
        return "UNKNOWN"

    ax = float(angle_x)
    ay = float(angle_y)

    if abs(ax) < GESTURE_THRESHOLD_DEG and abs(ay) < GESTURE_THRESHOLD_DEG:
        return "CENTER"
    if ay >= GESTURE_THRESHOLD_DEG and ax >= GESTURE_DIAGONAL_THRESHOLD_DEG:
        return "UP-RIGHT"
    if ay >= GESTURE_THRESHOLD_DEG and ax <= -GESTURE_DIAGONAL_THRESHOLD_DEG:
        return "UP-LEFT"
    if ay <= -GESTURE_THRESHOLD_DEG and ax >= GESTURE_DIAGONAL_THRESHOLD_DEG:
        return "DOWN-RIGHT"
    if ay <= -GESTURE_THRESHOLD_DEG and ax <= -GESTURE_DIAGONAL_THRESHOLD_DEG:
        return "DOWN-LEFT"
    if ax >= GESTURE_THRESHOLD_DEG:
        return "RIGHT"
    if ax <= -GESTURE_THRESHOLD_DEG:
        return "LEFT"
    if ay >= GESTURE_THRESHOLD_DEG:
        return "UP"
    if ay <= -GESTURE_THRESHOLD_DEG:
        return "DOWN"
    return "CENTER"


def update_smoothed_gesture(name: str, angle_x: Optional[float], angle_y: Optional[float]) -> str:
    raw_gesture = detect_gesture(angle_x, angle_y)
    window = flex_gesture_windows[name]
    window.append(raw_gesture)
    counts = Counter(window)
    return counts.most_common(1)[0][0] if counts else raw_gesture


def append_history(series: Dict[str, List[Any]], point: Dict[str, Any], maxlen: int = HISTORY_MAXLEN) -> None:
    for key, value in point.items():
        if key not in series:
            continue
        series[key].append(value)
        if len(series[key]) > maxlen:
            series[key].pop(0)


# ================= FLEX DECODE =================
def decode_packet(data: bytes) -> Optional[List[Dict[str, Any]]]:
    if not data or len(data) < 10:
        return None

    try:
        version, seq, ts, n, flags = struct.unpack("<HHIBB", data[:10])
    except struct.error:
        return None

    if n <= 0:
        return None

    sample_size = 20
    expected_len = 10 + (n * sample_size)
    if len(data) < expected_len:
        return None

    offset = 10
    results: List[Dict[str, Any]] = []

    for _ in range(n):
        chunk = data[offset:offset + sample_size]
        if len(chunk) != sample_size:
            return None

        try:
            s = struct.unpack("<hhhhhhhhhh", chunk)
        except struct.error:
            return None

        results.append({
            "version": version,
            "seq": seq,
            "flags": flags,
            "ts": ts,
            "ax": s[0] / 1000,
            "ay": s[1] / 1000,
            "az": s[2] / 1000,
            "gx": s[3],
            "gy": s[4],
            "gz": s[5],
            "bend": s[6] / 10,
            "stretch": s[7] / 10,
            "ads2_x": s[8] / 10,
            "ads2_y": s[9] / 10,
        })
        offset += sample_size

    return results if results else None


# ================= WEBSOCKET =================
async def broadcast_state() -> None:
    if not clients:
        return

    msg = json.dumps(latest_state)
    dead: List[WebSocket] = []

    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)

    for ws in dead:
        clients.discard(ws)


# ================= FLEX HANDLER =================
def create_flex_handler(name: str, first_packet_event: asyncio.Event):
    def handler(sender: Any, data: bytearray) -> None:
        raw = bytes(data)
        flex_last_raw_hex[name] = raw.hex()

        decoded = decode_packet(raw)
        if decoded is None:
            push_log(f"{name}: packet ignored (len={len(raw)})")
            return

        flex_buffers[name] = decoded

        if not first_packet_event.is_set():
            push_log(f"{name}: first valid packet received ({len(decoded)} sample(s))")
            first_packet_event.set()

    return handler


# ================= POLAR HANDLERS =================
def hr_handler(sender: Any, data: bytearray) -> None:
    if len(data) > 1:
        latest_state["hr"] = data[1]


def cp_handler(sender: Any, data: bytearray) -> None:
    if len(data) >= 6 and data[0] == 0xF0 and data[1] == 0x01:
        discovered_settings[data[2]] = bytes(data[5:])


def acc_handler(sender: Any, data: bytearray) -> None:
    if not data or data[0] != 0x02:
        return

    payload = data[10:]
    offset = 0

    while offset + 6 <= len(payload):
        x_raw = int.from_bytes(payload[offset:offset + 2], "little", signed=True)
        y_raw = int.from_bytes(payload[offset + 2:offset + 4], "little", signed=True)
        z_raw = int.from_bytes(payload[offset + 4:offset + 6], "little", signed=True)

        x = round(x_raw / POLAR_ACC_DIVISOR, 3)
        y = round(y_raw / POLAR_ACC_DIVISOR, 3)
        z = round(z_raw / POLAR_ACC_DIVISOR, 3)
        acc_queue.append((x, y, z))
        offset += 6


# ================= FLEX COMMANDS =================
async def safe_write(client: BleakClient, uuid: str, payload: bytes, label: str) -> bool:
    try:
        await client.write_gatt_char(uuid, payload, response=True)
        push_log(f"{label}: write ok (response) -> {payload.hex()}")
        return True
    except Exception as e1:
        push_log(f"{label}: write failed (response) -> {payload.hex()} | {e1}")

    try:
        await client.write_gatt_char(uuid, payload, response=False)
        push_log(f"{label}: write ok (no response) -> {payload.hex()}")
        return True
    except Exception as e2:
        push_log(f"{label}: write failed (no response) -> {payload.hex()} | {e2}")

    return False


async def start_flex_stream(client: BleakClient, name: str) -> None:
    push_log(f"{name}: trying command sequences")

    sequences = [
        [("set 10 Hz", bytes([0x01, 0x01])), ("start", bytes([0x04])), ("set 20 Hz", bytes([0x01, 0x02]))],
        [("set 10 Hz", bytes([0x01, 0x01])), ("start", bytes([0x04]))],
        [("start", bytes([0x04]))],
        [("set 20 Hz", bytes([0x01, 0x02])), ("start", bytes([0x04]))],
    ]

    for i, seq in enumerate(sequences, start=1):
        push_log(f"{name}: trying sequence #{i}")
        ok_all = True

        for label, payload in seq:
            ok = await safe_write(client, CTRL_UUID, payload, f"{name} {label}")
            await asyncio.sleep(0.3)
            if not ok:
                ok_all = False
                push_log(f"{name}: sequence #{i} failed at '{label}'")
                break

        if ok_all:
            push_log(f"{name}: sequence #{i} accepted")
            return

    raise RuntimeError("No control command sequence accepted by flexible device")


# ================= FLEX TASK =================
async def run_flexible(name: str, addr: str) -> None:
    while True:
        first_packet_event = asyncio.Event()

        try:
            set_flex_status(name, "CONNECTING")
            push_log(f"{name}: connecting to {addr}")

            async with BleakClient(addr) as client:
                push_log(f"{name}: BLE connected")
                await client.start_notify(DATA_UUID, create_flex_handler(name, first_packet_event))
                push_log(f"{name}: notify subscribed")

                await start_flex_stream(client, name)

                try:
                    await asyncio.wait_for(first_packet_event.wait(), timeout=FLEX_CONNECT_TIMEOUT)
                    set_flex_status(name, "CONNECTED")
                    push_log(f"{name}: stream active")
                except asyncio.TimeoutError:
                    set_flex_status(name, "NO_DATA")
                    push_log(f"{name}: connected but no valid packet within {FLEX_CONNECT_TIMEOUT:.0f}s")
                    raw_hex = flex_last_raw_hex.get(name)
                    if raw_hex:
                        preview = raw_hex[:80] + ("..." if len(raw_hex) > 80 else "")
                        push_log(f"{name}: last raw packet = {preview}")
                    raise RuntimeError("No valid data packet received from flexible sensor")

                while True:
                    await asyncio.sleep(FLEX_KEEPALIVE_SLEEP)
                    if not client.is_connected:
                        raise RuntimeError("BLE disconnected")

        except Exception as e:
            set_flex_status(name, "DISCONNECTED")
            push_log(f"{name}: error -> {e}")
            await asyncio.sleep(FLEX_RETRY_DELAY)


# ================= POLAR TASK =================
async def run_polar() -> None:
    global polar_status

    while True:
        try:
            polar_status = "CONNECTING"
            latest_state["polar_status"] = "CONNECTING"
            push_log("Polar: connecting...")

            async with BleakClient(POLAR_ADDR) as client:
                await client.start_notify(HR_UUID, hr_handler)
                await client.start_notify(PMD_CONTROL, cp_handler)
                await client.start_notify(PMD_DATA, acc_handler)

                await client.write_gatt_char(PMD_CONTROL, bytearray([0x01, 0x02]), response=True)
                await asyncio.sleep(0.5)

                if 0x02 in discovered_settings:
                    cmd = bytearray([0x02, 0x02]) + discovered_settings[0x02]
                    await client.write_gatt_char(PMD_CONTROL, cmd, response=True)

                polar_status = "CONNECTED"
                latest_state["polar_status"] = "CONNECTED"
                push_log("Polar: connected")

                while True:
                    await asyncio.sleep(1)
                    if not client.is_connected:
                        raise RuntimeError("Polar BLE disconnected")

        except Exception as e:
            polar_status = "DISCONNECTED"
            latest_state["polar_status"] = "DISCONNECTED"
            push_log(f"Polar: error -> {e}")
            await asyncio.sleep(3)


# ================= STATE LOOP =================
async def state_loop() -> None:
    global last_csv_write_time
    last_summary_time = 0.0

    while True:
        has_flex1 = bool(flex_buffers["Flexible1"])
        has_flex2 = bool(flex_buffers["Flexible2"])
        has_polar = len(acc_queue) > 0

        latest_state["ready"] = has_polar or has_flex1 or has_flex2

        flex1_full = flex_buffers["Flexible1"][-1] if has_flex1 else None
        flex2_full = flex_buffers["Flexible2"][-1] if has_flex2 else None

        polar_xyz: Optional[Tuple[float, float, float]] = None
        elapsed = round(time.monotonic() - start_monotonic, 3)

        if has_polar:
            acc_x, acc_y, acc_z = acc_queue.popleft()
            polar_xyz = (acc_x, acc_y, acc_z)
            latest_state["polar"] = {"acc_x": acc_x, "acc_y": acc_y, "acc_z": acc_z}
            append_history(
                latest_state["history"]["polar"],
                {"t": elapsed, "acc_x": acc_x, "acc_y": acc_y, "acc_z": acc_z},
            )

        flex1_summary = summarize_flex(flex1_full, "Flexible1")
        flex2_summary = summarize_flex(flex2_full, "Flexible2")

        if flex1_summary:
            flex1_summary["gesture"] = update_smoothed_gesture(
                "Flexible1",
                flex1_summary.get("angle_x"),
                flex1_summary.get("angle_y"),
            )
        if flex2_summary:
            flex2_summary["gesture"] = update_smoothed_gesture(
                "Flexible2",
                flex2_summary.get("angle_x"),
                flex2_summary.get("angle_y"),
            )

        latest_state["flex1"] = flex1_summary
        latest_state["flex2"] = flex2_summary
        latest_state["flex1_gesture"] = flex1_summary.get("gesture", "UNKNOWN") if flex1_summary else "UNKNOWN"
        latest_state["flex2_gesture"] = flex2_summary.get("gesture", "UNKNOWN") if flex2_summary else "UNKNOWN"

        if flex1_summary:
            append_history(
                latest_state["history"]["flex1"],
                {
                    "t": elapsed,
                    "ax": flex1_summary.get("ax"),
                    "ay": flex1_summary.get("ay"),
                    "az": flex1_summary.get("az"),
                    "gx": flex1_summary.get("gx"),
                    "gy": flex1_summary.get("gy"),
                    "gz": flex1_summary.get("gz"),
                    "angle_x": flex1_summary.get("angle_x"),
                    "angle_y": flex1_summary.get("angle_y"),
                    "angle_mag_disabled": flex1_summary.get("angle_mag_disabled"),
                },
            )

        if flex2_summary:
            append_history(
                latest_state["history"]["flex2"],
                {
                    "t": elapsed,
                    "ax": flex2_summary.get("ax"),
                    "ay": flex2_summary.get("ay"),
                    "az": flex2_summary.get("az"),
                    "gx": flex2_summary.get("gx"),
                    "gy": flex2_summary.get("gy"),
                    "gz": flex2_summary.get("gz"),
                    "angle_x": flex2_summary.get("angle_x"),
                    "angle_y": flex2_summary.get("angle_y"),
                    "angle_mag_disabled": flex2_summary.get("angle_mag_disabled"),
                },
            )

        latest_state["polar_status"] = polar_status
        latest_state["flex1_status"] = flex_status["Flexible1"]
        latest_state["flex2_status"] = flex_status["Flexible2"]
        latest_state["last_update"] = time.strftime("%H:%M:%S")

        now = time.monotonic()
        if now - last_summary_time >= 1.0 and (has_flex1 or has_flex2 or latest_state["polar"]["acc_x"] is not None):
            push_log("====== FLEXIBLE ======")
            push_log(format_flex_full(flex1_full, "F1", "Flexible1") + f" | gesture={latest_state['flex1_gesture']}")
            push_log(format_flex_full(flex2_full, "F2", "Flexible2") + f" | gesture={latest_state['flex2_gesture']}")
            push_log("------ POLAR ------")
            push_log(format_polar_log_line())
            last_summary_time = now

        # CSV logging: save only when all three streams have usable values.
        if polar_xyz and flex1_summary and flex2_summary and (now - last_csv_write_time >= CSV_WRITE_INTERVAL_SEC):
            save_row_to_csv(
                elapsed=elapsed,
                hr=latest_state.get("hr"),
                polar_xyz=polar_xyz,
                f1=flex1_summary,
                f2=flex2_summary,
            )
            last_csv_write_time = now

        await broadcast_state()
        await asyncio.sleep(0.1)


# ================= WEB APP =================
app = FastAPI()

HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Simple Realtime Dashboard</title>
  <style>
    :root {
      --bg: linear-gradient(180deg, #eef4ff 0%, #f7f9fc 100%);
      --card: #ffffff;
      --ink: #1f2937;
      --muted: #667085;
      --line: #dbe4f0;
    }
    body {
      font-family: Arial, sans-serif;
      margin: 24px;
      background: var(--bg);
      color: var(--ink);
    }
    h1 { margin-bottom: 8px; }
    h3 { margin: 0 0 12px 0; }
    .small { color: var(--muted); margin-bottom: 16px; }
    .card {
      background: var(--card);
      border-radius: 18px;
      padding: 16px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
      border: 1px solid rgba(148, 163, 184, 0.18);
    }
    .hero-card {
      background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 100%);
      color: white;
    }
    .hero-card .small-line { color: rgba(255,255,255,0.82); }
    .status-chip-wrap {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 14px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.16);
    }
    .chip-dot {
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: #93c5fd;
      box-shadow: 0 0 0 4px rgba(147,197,253,0.18);
    }
    .summary-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 16px;
      margin-top: 16px;
    }
    .summary-card {
      border-radius: 20px;
      padding: 16px;
      border: 1px solid var(--line);
      box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
    }
    .polar-card { background: linear-gradient(135deg, #ecfeff 0%, #eff6ff 100%); }
    .f1-card { background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%); }
    .f2-card { background: linear-gradient(135deg, #f3e8ff 0%, #faf5ff 100%); }
    .section-tag {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
      background: rgba(255,255,255,0.7);
      border: 1px solid rgba(148, 163, 184, 0.18);
    }
    .log {
      background: #0b1220;
      color: #86efac;
      font-family: monospace;
      padding: 12px;
      border-radius: 16px;
      height: 300px;
      overflow: auto;
      margin-top: 16px;
      border: 1px solid rgba(148, 163, 184, 0.14);
    }
    .badge {
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(255,255,255,0.7);
      font-size: 12px;
      margin-left: 6px;
      border: 1px solid rgba(148,163,184,0.18);
    }
    .metric-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 10px;
    }
    .metric {
      border-radius: 14px;
      padding: 12px;
      border: 1px solid rgba(148,163,184,0.16);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
    }
    .polar-card .metric { background: #dbeafe; }
    .f1-card .metric { background: #eff6ff; }
    .f2-card .metric { background: #faf5ff; }
    .metric-title {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }
    .metric-value {
      font-size: 18px;
      font-weight: 800;
      color: var(--ink);
    }
    .chart-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      margin-top: 18px;
    }
    .chart-card { background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }
    .legend-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .legend-btn {
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .legend-btn:hover { transform: translateY(-1px); }
    .legend-btn.active-blue { background: #dbeafe; border-color: #93c5fd; }
    .legend-btn.active-red { background: #fee2e2; border-color: #fca5a5; }
    .legend-btn.active-green { background: #dcfce7; border-color: #86efac; }
    .legend-btn.active-purple { background: #f3e8ff; border-color: #d8b4fe; }
    .legend-btn.inactive { opacity: 0.45; background: #f8fafc; }
    canvas {
      width: 100%;
      height: 420px;
      background: #fff;
      border-radius: 16px;
      border: 1px solid #e5edf6;
    }
    @media (max-width: 980px) {
      .summary-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <h1>Simple Realtime Dashboard</h1>
  <div class="small">Flex graphs are split into ACC, GYRO, and ANGLE. Polar stays on ACC in g.</div>

  <div class="card hero-card" style="margin-bottom:16px;">
    <div style="font-size:22px; font-weight:800;">Sensor Control Room</div>
    <div class="small-line" style="margin-top:6px;">Realtime monitor for Polar + Flexible1 + Flexible2 with interactive chart toggles and CSV logging.</div>
    <div class="status-chip-wrap">
      <div class="chip"><span class="chip-dot"></span>Status: <span id="ready">WAITING</span></div>
      <div class="chip"><span class="chip-dot"></span>HR: <span id="hr">-</span></div>
      <div class="chip"><span class="chip-dot"></span>Updated: <span id="updated">-</span></div>
    </div>
  </div>

  <div class="summary-grid">
    <div class="summary-card polar-card">
      <div class="section-tag">POLAR</div>
      <h3>Polar <span class="badge" id="polar_status">-</span></h3>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">ACC X (g)</div><div class="metric-value" id="px">-</div></div>
        <div class="metric"><div class="metric-title">ACC Y (g)</div><div class="metric-value" id="py">-</div></div>
        <div class="metric"><div class="metric-title">ACC Z (g)</div><div class="metric-value" id="pz">-</div></div>
      </div>
    </div>

    <div class="summary-card f1-card">
      <div class="section-tag">FLEX 1</div>
      <h3>Flexible1 <span class="badge" id="f1_status">-</span></h3>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">ACC X</div><div class="metric-value" id="f1_ax">-</div></div>
        <div class="metric"><div class="metric-title">ACC Y</div><div class="metric-value" id="f1_ay">-</div></div>
        <div class="metric"><div class="metric-title">ACC Z</div><div class="metric-value" id="f1_az">-</div></div>
      </div>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">GYRO X</div><div class="metric-value" id="f1_gx">-</div></div>
        <div class="metric"><div class="metric-title">GYRO Y</div><div class="metric-value" id="f1_gy">-</div></div>
        <div class="metric"><div class="metric-title">GYRO Z</div><div class="metric-value" id="f1_gz">-</div></div>
      </div>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">Angle X°</div><div class="metric-value" id="f1_anglex">-</div></div>
        <div class="metric"><div class="metric-title">Angle Y°</div><div class="metric-value" id="f1_angley">-</div></div>
        <div class="metric"><div class="metric-title">Gesture</div><div class="metric-value" id="f1_gesture">-</div></div>
      </div>
    </div>

    <div class="summary-card f2-card">
      <div class="section-tag">FLEX 2</div>
      <h3>Flexible2 <span class="badge" id="f2_status">-</span></h3>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">ACC X</div><div class="metric-value" id="f2_ax">-</div></div>
        <div class="metric"><div class="metric-title">ACC Y</div><div class="metric-value" id="f2_ay">-</div></div>
        <div class="metric"><div class="metric-title">ACC Z</div><div class="metric-value" id="f2_az">-</div></div>
      </div>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">GYRO X</div><div class="metric-value" id="f2_gx">-</div></div>
        <div class="metric"><div class="metric-title">GYRO Y</div><div class="metric-value" id="f2_gy">-</div></div>
        <div class="metric"><div class="metric-title">GYRO Z</div><div class="metric-value" id="f2_gz">-</div></div>
      </div>
      <div class="metric-row">
        <div class="metric"><div class="metric-title">Angle X°</div><div class="metric-value" id="f2_anglex">-</div></div>
        <div class="metric"><div class="metric-title">Angle Y°</div><div class="metric-value" id="f2_angley">-</div></div>
        <div class="metric"><div class="metric-title">Gesture</div><div class="metric-value" id="f2_gesture">-</div></div>
      </div>
    </div>
  </div>

  <div class="chart-grid">
    <div class="card chart-card">
      <h3>Flexible1 ACC Realtime Graph</h3>
      <div class="legend-controls" id="f1AccLegendControls"></div>
      <canvas id="f1AccChart" width="1200" height="420"></canvas>
    </div>
    <div class="card chart-card">
      <h3>Flexible1 GYRO Realtime Graph</h3>
      <div class="legend-controls" id="f1GyroLegendControls"></div>
      <canvas id="f1GyroChart" width="1200" height="420"></canvas>
    </div>
    <div class="card chart-card">
      <h3>Flexible1 ANGLE Realtime Graph</h3>
      <div class="legend-controls" id="f1AngleLegendControls"></div>
      <canvas id="f1AngleChart" width="1200" height="420"></canvas>
    </div>

    <div class="card chart-card">
      <h3>Flexible2 ACC Realtime Graph</h3>
      <div class="legend-controls" id="f2AccLegendControls"></div>
      <canvas id="f2AccChart" width="1200" height="420"></canvas>
    </div>
    <div class="card chart-card">
      <h3>Flexible2 GYRO Realtime Graph</h3>
      <div class="legend-controls" id="f2GyroLegendControls"></div>
      <canvas id="f2GyroChart" width="1200" height="420"></canvas>
    </div>
    <div class="card chart-card">
      <h3>Flexible2 ANGLE Realtime Graph</h3>
      <div class="legend-controls" id="f2AngleLegendControls"></div>
      <canvas id="f2AngleChart" width="1200" height="420"></canvas>
    </div>

    <div class="card chart-card">
      <h3>Polar ACC Realtime Graph</h3>
      <div class="legend-controls" id="polarLegendControls"></div>
      <canvas id="polarChart" width="1200" height="420"></canvas>
    </div>
  </div>

  <h3>Live Log</h3>
  <div class="log" id="log"></div>

  <script>
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${location.host}/ws`);

    const f1AccCanvas = document.getElementById("f1AccChart");
    const f1GyroCanvas = document.getElementById("f1GyroChart");
    const f1AngleCanvas = document.getElementById("f1AngleChart");
    const f2AccCanvas = document.getElementById("f2AccChart");
    const f2GyroCanvas = document.getElementById("f2GyroChart");
    const f2AngleCanvas = document.getElementById("f2AngleChart");
    const polarCanvas = document.getElementById("polarChart");

    const f1AccCtx = f1AccCanvas.getContext("2d");
    const f1GyroCtx = f1GyroCanvas.getContext("2d");
    const f1AngleCtx = f1AngleCanvas.getContext("2d");
    const f2AccCtx = f2AccCanvas.getContext("2d");
    const f2GyroCtx = f2GyroCanvas.getContext("2d");
    const f2AngleCtx = f2AngleCanvas.getContext("2d");
    const polarCtx = polarCanvas.getContext("2d");

    const chartState = {
      f1Acc: { ax: true, ay: true, az: true },
      f1Gyro: { gx: true, gy: true, gz: true },
      f1Angle: { angle_x: true, angle_y: true, angle_mag_disabled: true },
      f2Acc: { ax: true, ay: true, az: true },
      f2Gyro: { gx: true, gy: true, gz: true },
      f2Angle: { angle_x: true, angle_y: true, angle_mag_disabled: true },
      polar: { acc_x: true, acc_y: true, acc_z: true },
    };

    function setText(id, value) {
      document.getElementById(id).textContent = value ?? "-";
    }

    function buildLegendControls(containerId, config, stateKey) {
      const el = document.getElementById(containerId);
      el.innerHTML = "";
      config.forEach(item => {
        const btn = document.createElement("button");
        btn.className = `legend-btn ${item.className}`;
        btn.textContent = item.label;
        btn.dataset.key = item.key;
        btn.onclick = () => {
          chartState[stateKey][item.key] = !chartState[stateKey][item.key];
          refreshLegendStyles();
        };
        el.appendChild(btn);
      });
    }

    function refreshLegendStyles() {
      document.querySelectorAll(".legend-controls").forEach(group => {
        const groupId = group.id;
        const map = {
          f1AccLegendControls: chartState.f1Acc,
          f1GyroLegendControls: chartState.f1Gyro,
          f1AngleLegendControls: chartState.f1Angle,
          f2AccLegendControls: chartState.f2Acc,
          f2GyroLegendControls: chartState.f2Gyro,
          f2AngleLegendControls: chartState.f2Angle,
          polarLegendControls: chartState.polar,
        };
        const state = map[groupId];
        if (!state) return;

        group.querySelectorAll("button").forEach(btn => {
          const key = btn.dataset.key;
          btn.classList.remove("inactive");
          if (!state[key]) btn.classList.add("inactive");
        });
      });
    }

    buildLegendControls("f1AccLegendControls", [
      { key: "ax", label: "F1 ACC X", className: "active-blue" },
      { key: "ay", label: "F1 ACC Y", className: "active-red" },
      { key: "az", label: "F1 ACC Z", className: "active-green" }
    ], "f1Acc");
    buildLegendControls("f1GyroLegendControls", [
      { key: "gx", label: "F1 GYRO X", className: "active-purple" },
      { key: "gy", label: "F1 GYRO Y", className: "active-blue" },
      { key: "gz", label: "F1 GYRO Z", className: "active-red" }
    ], "f1Gyro");
    buildLegendControls("f1AngleLegendControls", [
      { key: "angle_x", label: "F1 Angle X°", className: "active-blue" },
      { key: "angle_y", label: "F1 Angle Y°", className: "active-red" },
      { key: "angle_mag_disabled", label: "F1 Angle Mag", className: "active-green" }
    ], "f1Angle");

    buildLegendControls("f2AccLegendControls", [
      { key: "ax", label: "F2 ACC X", className: "active-blue" },
      { key: "ay", label: "F2 ACC Y", className: "active-purple" },
      { key: "az", label: "F2 ACC Z", className: "active-green" }
    ], "f2Acc");
    buildLegendControls("f2GyroLegendControls", [
      { key: "gx", label: "F2 GYRO X", className: "active-red" },
      { key: "gy", label: "F2 GYRO Y", className: "active-blue" },
      { key: "gz", label: "F2 GYRO Z", className: "active-purple" }
    ], "f2Gyro");
    buildLegendControls("f2AngleLegendControls", [
      { key: "angle_x", label: "F2 Angle X°", className: "active-green" },
      { key: "angle_y", label: "F2 Angle Y°", className: "active-red" },
      { key: "angle_mag_disabled", label: "F2 Angle Mag", className: "active-blue" }
    ], "f2Angle");

    buildLegendControls("polarLegendControls", [
      { key: "acc_x", label: "ACC X", className: "active-blue" },
      { key: "acc_y", label: "ACC Y", className: "active-red" },
      { key: "acc_z", label: "ACC Z", className: "active-green" }
    ], "polar");

    refreshLegendStyles();

    function drawAxesOnly(ctx, left, right, top, bottom, minV, maxV, yLabel, xLabel, t) {
      for (let i = 0; i <= 4; i++) {
        const y = top + ((bottom - top) * i / 4);
        ctx.beginPath();
        ctx.strokeStyle = "#e8eef5";
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();
      }

      const tickCount = 6;
      for (let i = 0; i < tickCount; i++) {
        const x = left + ((right - left) * i / (tickCount - 1));
        ctx.beginPath();
        ctx.strokeStyle = "#f1f5f9";
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.stroke();
      }

      ctx.beginPath();
      ctx.strokeStyle = "#94a3b8";
      ctx.lineWidth = 1;
      ctx.moveTo(left, top);
      ctx.lineTo(left, bottom);
      ctx.lineTo(right, bottom);
      ctx.stroke();

      ctx.fillStyle = "#334155";
      ctx.font = "12px Arial";
      ctx.fillText(maxV.toFixed(2), 12, top + 4);
      ctx.fillText(((maxV + minV) / 2).toFixed(2), 12, top + (bottom - top) / 2 + 4);
      ctx.fillText(minV.toFixed(2), 12, bottom + 4);
      ctx.fillText(yLabel, 12, top - 10);
      ctx.fillText(xLabel, right - 60, bottom + 34);

      if (Array.isArray(t) && t.length >= 2) {
        for (let i = 0; i < tickCount; i++) {
          const idx = Math.round((t.length - 1) * i / (tickCount - 1));
          const x = left + ((right - left) * i / (tickCount - 1));
          ctx.fillStyle = "#64748b";
          ctx.fillText(`${Number(t[idx]).toFixed(1)}s`, x - 14, bottom + 18);
        }
      }
    }

    function drawSeries(ctx, canvas, t, series, options = {}) {
      const w = canvas.width;
      const h = canvas.height;
      const left = 72;
      const right = w - 24;
      const top = 34;
      const bottom = h - 54;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, w, h);

      const activeSeries = series.filter(s => s.visible);
      const flat = [];
      activeSeries.forEach(s => {
        (s.values || []).forEach(v => {
          if (v !== null && v !== undefined && !Number.isNaN(v)) flat.push(Number(v));
        });
      });

      if (!Array.isArray(t) || t.length < 2 || flat.length === 0) {
        drawAxesOnly(ctx, left, right, top, bottom, -1, 1, options.yLabel || "value", options.xLabel || "time", []);
        ctx.fillStyle = "#64748b";
        ctx.font = "14px Arial";
        ctx.fillText("toggle a line on, or wait for data...", left + 12, top + 24);
        return;
      }

      const minV = Math.min(...flat);
      const maxRaw = Math.max(...flat);
      const maxV = maxRaw === minV ? minV + 1 : maxRaw;
      drawAxesOnly(ctx, left, right, top, bottom, minV, maxV, options.yLabel || "value", options.xLabel || "time", t);

      const xSpan = Math.max(t.length - 1, 1);
      const ySpan = maxV - minV;

      activeSeries.forEach(s => {
        if (!Array.isArray(s.values) || s.values.length === 0) return;
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2.5;
        ctx.setLineDash(s.dashed ? [10, 7] : []);
        ctx.beginPath();
        s.values.forEach((rawV, i) => {
          const v = rawV ?? minV;
          const x = left + (i / xSpan) * (right - left);
          const y = bottom - ((v - minV) / ySpan) * (bottom - top);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
      });
      ctx.setLineDash([]);
    }

    ws.onopen = () => console.log("ws connected");
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      setText("ready", data.ready ? "READY" : "WAITING");
      setText("hr", data.hr);
      setText("updated", data.last_update ?? "-");

      setText("polar_status", data.polar_status);
      setText("f1_status", data.flex1_status);
      setText("f2_status", data.flex2_status);

      setText("px", data.polar?.acc_x);
      setText("py", data.polar?.acc_y);
      setText("pz", data.polar?.acc_z);

      setText("f1_ax", data.flex1?.ax);
      setText("f1_ay", data.flex1?.ay);
      setText("f1_az", data.flex1?.az);
      setText("f1_gx", data.flex1?.gx);
      setText("f1_gy", data.flex1?.gy);
      setText("f1_gz", data.flex1?.gz);
      setText("f1_anglex", data.flex1?.angle_x);
      setText("f1_angley", data.flex1?.angle_y);
      setText("f1_gesture", data.flex1_gesture);

      setText("f2_ax", data.flex2?.ax);
      setText("f2_ay", data.flex2?.ay);
      setText("f2_az", data.flex2?.az);
      setText("f2_gx", data.flex2?.gx);
      setText("f2_gy", data.flex2?.gy);
      setText("f2_gz", data.flex2?.gz);
      setText("f2_anglex", data.flex2?.angle_x);
      setText("f2_angley", data.flex2?.angle_y);
      setText("f2_gesture", data.flex2_gesture);

      document.getElementById("log").innerHTML = (data.log || []).map(x => `<div>${x}</div>`).join("");

      const h = data.history || {};
      const f1 = h.flex1 || {};
      const f2 = h.flex2 || {};
      const p = h.polar || {};

      drawSeries(f1AccCtx, f1AccCanvas, f1.t || [], [
        { label: "F1 ACC X", values: f1.ax || [], color: "#2563eb", visible: chartState.f1Acc.ax, dashed: false },
        { label: "F1 ACC Y", values: f1.ay || [], color: "#dc2626", visible: chartState.f1Acc.ay, dashed: false },
        { label: "F1 ACC Z", values: f1.az || [], color: "#16a34a", visible: chartState.f1Acc.az, dashed: false },
      ], { yLabel: "acceleration", xLabel: "time" });

      drawSeries(f1GyroCtx, f1GyroCanvas, f1.t || [], [
        { label: "F1 GYRO X", values: f1.gx || [], color: "#9333ea", visible: chartState.f1Gyro.gx, dashed: false },
        { label: "F1 GYRO Y", values: f1.gy || [], color: "#0ea5e9", visible: chartState.f1Gyro.gy, dashed: false },
        { label: "F1 GYRO Z", values: f1.gz || [], color: "#ef4444", visible: chartState.f1Gyro.gz, dashed: false },
      ], { yLabel: "gyro", xLabel: "time" });

      drawSeries(f1AngleCtx, f1AngleCanvas, f1.t || [], [
        { label: "F1 Angle X°", values: f1.angle_x || [], color: "#2563eb", visible: chartState.f1Angle.angle_x, dashed: false },
        { label: "F1 Angle Y°", values: f1.angle_y || [], color: "#dc2626", visible: chartState.f1Angle.angle_y, dashed: false },
        { label: "F1 Angle Mag", values: f1.angle_mag_disabled || [], color: "#16a34a", visible: chartState.f1Angle.angle_mag_disabled, dashed: false },
      ], { yLabel: "angle (deg)", xLabel: "time" });

      drawSeries(f2AccCtx, f2AccCanvas, f2.t || [], [
        { label: "F2 ACC X", values: f2.ax || [], color: "#2563eb", visible: chartState.f2Acc.ax, dashed: true },
        { label: "F2 ACC Y", values: f2.ay || [], color: "#9333ea", visible: chartState.f2Acc.ay, dashed: true },
        { label: "F2 ACC Z", values: f2.az || [], color: "#16a34a", visible: chartState.f2Acc.az, dashed: true },
      ], { yLabel: "acceleration", xLabel: "time" });

      drawSeries(f2GyroCtx, f2GyroCanvas, f2.t || [], [
        { label: "F2 GYRO X", values: f2.gx || [], color: "#ef4444", visible: chartState.f2Gyro.gx, dashed: true },
        { label: "F2 GYRO Y", values: f2.gy || [], color: "#0ea5e9", visible: chartState.f2Gyro.gy, dashed: true },
        { label: "F2 GYRO Z", values: f2.gz || [], color: "#a855f7", visible: chartState.f2Gyro.gz, dashed: true },
      ], { yLabel: "gyro", xLabel: "time" });

      drawSeries(f2AngleCtx, f2AngleCanvas, f2.t || [], [
        { label: "F2 Angle X°", values: f2.angle_x || [], color: "#22c55e", visible: chartState.f2Angle.angle_x, dashed: true },
        { label: "F2 Angle Y°", values: f2.angle_y || [], color: "#f97316", visible: chartState.f2Angle.angle_y, dashed: true },
        { label: "F2 Angle Mag", values: f2.angle_mag_disabled || [], color: "#1d4ed8", visible: chartState.f2Angle.angle_mag_disabled, dashed: true },
      ], { yLabel: "angle (deg)", xLabel: "time" });

      drawSeries(polarCtx, polarCanvas, p.t || [], [
        { label: "ACC X", values: p.acc_x || [], color: "#2563eb", visible: chartState.polar.acc_x, dashed: false },
        { label: "ACC Y", values: p.acc_y || [], color: "#dc2626", visible: chartState.polar.acc_y, dashed: false },
        { label: "ACC Z", values: p.acc_z || [], color: "#16a34a", visible: chartState.polar.acc_z, dashed: false },
      ], { yLabel: "acceleration (g)", xLabel: "time" });
    };

    ws.onerror = (e) => console.log("ws error", e);
    ws.onclose = () => console.log("ws closed");
  </script>
</body>
</html>
"""


@app.get("/")
async def home() -> HTMLResponse:
    return HTMLResponse(HTML)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    push_log("WebSocket: browser connected")

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        clients.discard(ws)
        push_log("WebSocket: browser disconnected")


@app.on_event("startup")
async def startup_event() -> None:
    init_csv()
    asyncio.create_task(run_polar())
    asyncio.create_task(run_flexible("Flexible1", DEVICES["Flexible1"]))
    asyncio.create_task(run_flexible("Flexible2", DEVICES["Flexible2"]))
    asyncio.create_task(state_loop())
    push_log(f"Startup complete | CSV -> {os.path.abspath(CSV_FILE)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8007, reload=False)
