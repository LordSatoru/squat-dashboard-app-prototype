import math
from typing import Any, Dict, List, Optional

from config import FLEX_AXIS_SIGN, HISTORY_MAXLEN


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


def format_polar_log_line(latest_state: Dict[str, Any], start_monotonic: float) -> str:
    elapsed = __import__("time").monotonic() - start_monotonic
    x = latest_state["polar"].get("acc_x")
    y = latest_state["polar"].get("acc_y")
    z = latest_state["polar"].get("acc_z")
    hr = latest_state.get("hr")
    return f"{elapsed:.3f}s | HR: {hr if hr is not None else '-'} | ACC X:{x}g Y:{y}g Z:{z}g"


def append_history(series: Dict[str, List[Any]], point: Dict[str, Any], maxlen: int = HISTORY_MAXLEN) -> None:
    for key, value in point.items():
        if key not in series:
            continue
        series[key].append(value)
        if len(series[key]) > maxlen:
            series[key].pop(0)
