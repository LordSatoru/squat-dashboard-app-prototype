import asyncio
import os
import time
from typing import Any, Dict, Optional, Tuple

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import CSV_FILE, CSV_WRITE_INTERVAL_SEC, DEVICES
from core.gesture import update_smoothed_gesture
from core.state import (
    acc_queue,
    broadcast_state,
    flex_buffers,
    flex_status,
    latest_state,
    start_monotonic,
)
from core import state
from core.utils import append_history, format_flex_full, format_polar_log_line, summarize_flex
from sensors.flexible import run_flexible
from sensors.polar import run_polar
from services.csv_writer import init_csv, save_row_to_csv
from services.logger import push_log
from web.routes import register_routes
from web.websocket import register_websocket

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
register_routes(app)
register_websocket(app)


async def state_loop() -> None:
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

        latest_state["polar_status"] = state.polar_status
        latest_state["flex1_status"] = flex_status["Flexible1"]
        latest_state["flex2_status"] = flex_status["Flexible2"]
        latest_state["last_update"] = time.strftime("%H:%M:%S")

        now = time.monotonic()
        if now - last_summary_time >= 1.0 and (has_flex1 or has_flex2 or latest_state["polar"]["acc_x"] is not None):
            push_log(latest_state, "====== FLEXIBLE ======")
            push_log(latest_state, format_flex_full(flex1_full, "F1", "Flexible1") + f" | gesture={latest_state['flex1_gesture']}")
            push_log(latest_state, format_flex_full(flex2_full, "F2", "Flexible2") + f" | gesture={latest_state['flex2_gesture']}")
            push_log(latest_state, "------ POLAR ------")
            push_log(latest_state, format_polar_log_line(latest_state, start_monotonic))
            last_summary_time = now

        if polar_xyz and flex1_summary and flex2_summary and (now - state.last_csv_write_time >= CSV_WRITE_INTERVAL_SEC):
            save_row_to_csv(
                elapsed=elapsed,
                hr=latest_state.get("hr"),
                polar_xyz=polar_xyz,
                f1=flex1_summary,
                f2=flex2_summary,
            )
            state.last_csv_write_time = now

        await broadcast_state()
        await asyncio.sleep(0.1)


@app.on_event("startup")
async def startup_event() -> None:
    init_csv()
    asyncio.create_task(run_polar())
    asyncio.create_task(run_flexible("Flexible1", DEVICES["Flexible1"]))
    asyncio.create_task(run_flexible("Flexible2", DEVICES["Flexible2"]))
    asyncio.create_task(state_loop())
    push_log(latest_state, f"Startup complete | CSV -> {os.path.abspath(CSV_FILE)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8007, reload=False)
