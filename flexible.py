import asyncio
from typing import Any

from bleak import BleakClient

from config import (
    CTRL_UUID,
    DATA_UUID,
    FLEX_CONNECT_TIMEOUT,
    FLEX_KEEPALIVE_SLEEP,
    FLEX_RETRY_DELAY,
)
from core.state import flex_buffers, flex_last_raw_hex, latest_state, set_flex_status
from sensors.decoder import decode_packet
from services.logger import push_log


def create_flex_handler(name: str, first_packet_event: asyncio.Event):
    def handler(sender: Any, data: bytearray) -> None:
        raw = bytes(data)
        flex_last_raw_hex[name] = raw.hex()

        decoded = decode_packet(raw)
        if decoded is None:
            push_log(latest_state, f"{name}: packet ignored (len={len(raw)})")
            return

        flex_buffers[name] = decoded

        if not first_packet_event.is_set():
            push_log(latest_state, f"{name}: first valid packet received ({len(decoded)} sample(s))")
            first_packet_event.set()

    return handler


async def safe_write(client: BleakClient, uuid: str, payload: bytes, label: str) -> bool:
    try:
        await client.write_gatt_char(uuid, payload, response=True)
        push_log(latest_state, f"{label}: write ok (response) -> {payload.hex()}")
        return True
    except Exception as e1:
        push_log(latest_state, f"{label}: write failed (response) -> {payload.hex()} | {e1}")

    try:
        await client.write_gatt_char(uuid, payload, response=False)
        push_log(latest_state, f"{label}: write ok (no response) -> {payload.hex()}")
        return True
    except Exception as e2:
        push_log(latest_state, f"{label}: write failed (no response) -> {payload.hex()} | {e2}")

    return False


async def start_flex_stream(client: BleakClient, name: str) -> None:
    push_log(latest_state, f"{name}: trying command sequences")

    sequences = [
        [("set 10 Hz", bytes([0x01, 0x01])), ("start", bytes([0x04])), ("set 20 Hz", bytes([0x01, 0x02]))],
        [("set 10 Hz", bytes([0x01, 0x01])), ("start", bytes([0x04]))],
        [("start", bytes([0x04]))],
        [("set 20 Hz", bytes([0x01, 0x02])), ("start", bytes([0x04]))],
    ]

    for i, seq in enumerate(sequences, start=1):
        push_log(latest_state, f"{name}: trying sequence #{i}")
        ok_all = True

        for label, payload in seq:
            ok = await safe_write(client, CTRL_UUID, payload, f"{name} {label}")
            await asyncio.sleep(0.3)
            if not ok:
                ok_all = False
                push_log(latest_state, f"{name}: sequence #{i} failed at '{label}'")
                break

        if ok_all:
            push_log(latest_state, f"{name}: sequence #{i} accepted")
            return

    raise RuntimeError("No control command sequence accepted by flexible device")


async def run_flexible(name: str, addr: str) -> None:
    while True:
        first_packet_event = asyncio.Event()

        try:
            set_flex_status(name, "CONNECTING")
            push_log(latest_state, f"{name}: connecting to {addr}")

            async with BleakClient(addr) as client:
                push_log(latest_state, f"{name}: BLE connected")
                await client.start_notify(DATA_UUID, create_flex_handler(name, first_packet_event))
                push_log(latest_state, f"{name}: notify subscribed")

                await start_flex_stream(client, name)

                try:
                    await asyncio.wait_for(first_packet_event.wait(), timeout=FLEX_CONNECT_TIMEOUT)
                    set_flex_status(name, "CONNECTED")
                    push_log(latest_state, f"{name}: stream active")
                except asyncio.TimeoutError:
                    set_flex_status(name, "NO_DATA")
                    push_log(latest_state, f"{name}: connected but no valid packet within {FLEX_CONNECT_TIMEOUT:.0f}s")
                    raw_hex = flex_last_raw_hex.get(name)
                    if raw_hex:
                        preview = raw_hex[:80] + ("..." if len(raw_hex) > 80 else "")
                        push_log(latest_state, f"{name}: last raw packet = {preview}")
                    raise RuntimeError("No valid data packet received from flexible sensor")

                while True:
                    await asyncio.sleep(FLEX_KEEPALIVE_SLEEP)
                    if not client.is_connected:
                        raise RuntimeError("BLE disconnected")

        except Exception as e:
            set_flex_status(name, "DISCONNECTED")
            push_log(latest_state, f"{name}: error -> {e}")
            await asyncio.sleep(FLEX_RETRY_DELAY)
