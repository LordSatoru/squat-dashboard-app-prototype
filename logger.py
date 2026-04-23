import time
from typing import Any, Dict


def push_log(latest_state: Dict[str, Any], line: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    latest_state["log"].append(f"[{stamp}] {line}")
    latest_state["log"] = latest_state["log"][-40:]
    print(line)
