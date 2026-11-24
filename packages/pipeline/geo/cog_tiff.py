"""Minimal tiled TIFF/COG IFD parser and DEFLATE tile decoder."""
from __future__ import annotations

import struct
import zlib
from typing import Any

import numpy as np


def decode_deflate_rgb_tile(
    compressed: bytes,
    tile_w: int,
    tile_h: int,
    samples: int = 3,
    predictor: int = 2,
    bytes_per_sample: int = 1,
) -> np.ndarray:
    """Decompress a TIFF Deflate tile and undo horizontal differencing predictor."""
    raw = zlib.decompress(compressed)
    dtype = np.uint16 if bytes_per_sample == 2 else np.uint8
    arr = np.frombuffer(raw, dtype=dtype).reshape((tile_h, tile_w, samples)).copy()
    if predictor == 2:
        arr = np.cumsum(arr, axis=1, dtype=dtype)
    return arr


def _read_u32_array(buf: bytes, endian: str, count: int, offset: int) -> list[int]:
    return list(struct.unpack_from(f"{endian}{count}I", buf, offset))


def parse_tiff_ifd(header_bytes: bytes) -> dict[str, Any]:
    """Parse IFD0 from a tiled TIFF/COG header buffer."""
    endian = "<" if header_bytes[:2] == b"II" else ">"
    _, ifd_off = struct.unpack_from(endian + "HI", header_bytes, 2)
    num_tags = struct.unpack_from(endian + "H", header_bytes, ifd_off)[0]
    raw_tags: dict[int, tuple[int, int, int]] = {}
    for i in range(num_tags):
        tag, typ, cnt, val = struct.unpack_from(endian + "HHII", header_bytes, ifd_off + 2 + i * 12)
        raw_tags[tag] = (typ, cnt, val)

    def scalar(tag: int, default: int = 0) -> int:
        return raw_tags[tag][2] if tag in raw_tags else default

    def array_u32(tag: int) -> list[int]:
        if tag not in raw_tags:
            return []
        typ, cnt, val = raw_tags[tag]
        if cnt == 1:
            return [val]
        if typ == 3:
            return list(struct.unpack_from(f"{endian}{cnt}H", header_bytes, val))
        return _read_u32_array(header_bytes, endian, cnt, val)

    bps_raw = raw_tags.get(258)
    bits_per_sample = 8
    if bps_raw:
        if bps_raw[1] == 1:
            bits_per_sample = bps_raw[2]
        elif bps_raw[2] + bps_raw[1] * 2 <= len(header_bytes):
            bits_per_sample = struct.unpack_from(f"{endian}H", header_bytes, bps_raw[2])[0]

    return {
        "width": scalar(256),
        "height": scalar(257),
        "bits_per_sample": bits_per_sample,
        "compression": scalar(259, 1),
        "samples_per_pixel": scalar(277, 1),
        "predictor": scalar(317, 1),
        "tile_w": scalar(322),
        "tile_h": scalar(323),
        "tile_offsets": array_u32(324),
        "tile_byte_counts": array_u32(325),
    }
