import struct
from typing import Any, Dict, List, Optional


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
