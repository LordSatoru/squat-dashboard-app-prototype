from datetime import datetime
from typing import Dict

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

# ================= POLAR =================
POLAR_ADDR = "A0:9E:1A:E3:AA:65"
PMD_CONTROL = "FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8"
PMD_DATA = "FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8"
HR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
POLAR_ACC_DIVISOR = 1000.0  # convert mg -> g

# ================= CSV =================
CSV_FILE = f"sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
CSV_WRITE_INTERVAL_SEC = 0.05
