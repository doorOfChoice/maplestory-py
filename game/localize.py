"""中文本地化：WZ（台版）文本为繁体，在游戏层出口统一转为简体。

转换只发生在 game/ 层（wzpy 保持原样返回 WZ 数据）；结果以 lru_cache
缓存，同一词条只转换一次。
"""

from __future__ import annotations

from functools import lru_cache

from opencc import OpenCC

_CC = OpenCC("t2s")


@lru_cache(maxsize=8192)
def to_simplified(text: str) -> str:
    """繁体 → 简体（空串直接返回）。"""
    return _CC.convert(text) if text else text
