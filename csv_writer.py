import csv
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from config import CSV_FILE


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


def save_row_to_csv(
    elapsed: float,
    hr: Optional[int],
    polar_xyz: Optional[Tuple[float, float, float]],
    f1: Optional[Dict[str, Any]],
    f2: Optional[Dict[str, Any]],
) -> None:
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
