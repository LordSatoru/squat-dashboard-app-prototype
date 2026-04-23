import asyncio
from bleak import BleakClient

from config import HR_UUID, PMD_CONTROL, PMD_DATA, POLAR_ACC_DIVISOR, POLAR_ADDR
from core import state
from services.logger import push_log


def hr_handler(sender, data: bytearray) -> None:
    if len(data) > 1:
        state.latest_state["hr"] = data[1]


def cp_handler(sender, data: bytearray) -> None:
    if len(data) >= 6 and data[0] == 0xF0 and data[1] == 0x01:
        state.discovered_settings[data[2]] = bytes(data[5:])


def acc_handler(sender, data: bytearray) -> None:
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
        state.acc_queue.append((x, y, z))
        offset += 6


async def run_polar() -> None:
    while True:
        try:
            state.polar_status = "CONNECTING"
            state.latest_state["polar_status"] = "CONNECTING"
            push_log(state.latest_state, "Polar: connecting...")

            async with BleakClient(POLAR_ADDR) as client:
                await client.start_notify(HR_UUID, hr_handler)
                await client.start_notify(PMD_CONTROL, cp_handler)
                await client.start_notify(PMD_DATA, acc_handler)

                await client.write_gatt_char(PMD_CONTROL, bytearray([0x01, 0x02]), response=True)
                await asyncio.sleep(0.5)

                if 0x02 in state.discovered_settings:
                    cmd = bytearray([0x02, 0x02]) + state.discovered_settings[0x02]
                    await client.write_gatt_char(PMD_CONTROL, cmd, response=True)

                state.polar_status = "CONNECTED"
                state.latest_state["polar_status"] = "CONNECTED"
                push_log(state.latest_state, "Polar: connected")

                while True:
                    await asyncio.sleep(1)
                    if not client.is_connected:
                        raise RuntimeError("Polar BLE disconnected")

        except Exception as e:
            state.polar_status = "DISCONNECTED"
            state.latest_state["polar_status"] = "DISCONNECTED"
            push_log(state.latest_state, f"Polar: error -> {e}")
            await asyncio.sleep(3)
