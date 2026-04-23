from collections import Counter
from typing import Optional

from config import GESTURE_DIAGONAL_THRESHOLD_DEG, GESTURE_THRESHOLD_DEG
from core.state import flex_gesture_windows


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
