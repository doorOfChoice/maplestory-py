"""canvas 像素解码向量化后与逐像素参考实现完全一致（合成数据，不需 WZ）。"""
from __future__ import annotations

import random

from wzpy.canvas import _decode_pixels


def _ref_fmt1(data: bytes, w: int, h: int):
    out = bytearray(w * h * 4)
    for i in range(w * h):
        lo = data[i * 2]
        hi = data[i * 2 + 1]
        out[i * 4 + 0] = (hi & 0x0F) | ((hi & 0x0F) << 4)
        out[i * 4 + 1] = (lo & 0xF0) | ((lo & 0xF0) >> 4)
        out[i * 4 + 2] = (lo & 0x0F) | ((lo & 0x0F) << 4)
        out[i * 4 + 3] = (hi & 0xF0) | ((hi & 0xF0) >> 4)
    return bytes(out)


def _ref_565(data: bytes, n: int):
    out = bytearray(n * 4)
    for i in range(n):
        v = data[i * 2] | (data[i * 2 + 1] << 8)
        out[i * 4:i * 4 + 4] = bytes([((v >> 11) & 0x1F) * 8,
                                      ((v >> 5) & 0x3F) * 4,
                                      (v & 0x1F) * 8, 0xFF])
    return bytes(out)


def _rand_bytes(n: int, seed: int) -> bytes:
    rng = random.Random(seed)
    return bytes(rng.randrange(256) for _ in range(n))


def test_argb4444_matches_reference():
    """ARGB4444 向量化解码与逐像素循环输出一致。"""
    w, h = 7, 5
    data = _rand_bytes(w * h * 2, 1)
    img = _decode_pixels(data, w, h, fmt=1)
    assert img.tobytes() == _ref_fmt1(data, w, h)


def test_argb1555_matches_reference():
    """ARGB1555：alpha 位展开为 0x00/0xFF，RGB 5 位 ×8。"""
    w, h = 6, 4
    data = _rand_bytes(w * h * 2, 2)
    img = _decode_pixels(data, w, h, fmt=257)
    ref = bytearray(w * h * 4)
    for i in range(w * h):
        v = data[i * 2] | (data[i * 2 + 1] << 8)
        ref[i * 4:i * 4 + 4] = bytes([((v >> 10) & 0x1F) * 8,
                                      ((v >> 5) & 0x1F) * 8,
                                      (v & 0x1F) * 8,
                                      0xFF if v & 0x8000 else 0x00])
    assert img.tobytes() == bytes(ref)


def test_rgb565_matches_reference():
    """RGB565 全不透明输出与参考实现一致。"""
    w, h = 9, 3
    data = _rand_bytes(w * h * 2, 3)
    img = _decode_pixels(data, w, h, fmt=513)
    assert img.tobytes() == _ref_565(data, w * h)


def test_downsampled_rgb565_matches_reference():
    """下采样 565：先解小图再 NEAREST 放大，与小图逐像素结果一致。"""
    w, h = 32, 16
    sw, sh = (w + 15) // 16, (h + 15) // 16
    data = _rand_bytes(sw * sh * 2, 4)
    img = _decode_pixels(data, w, h, fmt=517)
    small = _ref_565(data, sw * sh)
    from PIL import Image
    ref = Image.frombytes("RGBA", (sw, sh), small).resize((w, h), Image.NEAREST)
    assert img.tobytes() == ref.tobytes()
