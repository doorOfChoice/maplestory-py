"""CJK 中文字体加载：避免 pygame 默认字体（Font(None)）把汉字渲染成方块。

pygame 的 `pygame.font.Font(None, size)` 只带 ASCII 字形，遇到 CJK 会统一
绘制成 .notdef 矩形（乱码口口口）。这里按平台常见中文字体名依次匹配系统
字体，首个命中即返回；全部落空时回退 Font(None)（保持可用，不抛异常）。

另提供 render_text：对反复出现的文本做 LRU 缓存（HUD/伤害数字每帧渲染，
字体渲染很贵，缓存 Surface 可消除帧时间尖峰）。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Tuple

import pygame

# 候选顺序：macOS 优先（项目运行环境），再广覆盖 Windows / Linux 常见中文字体
_FONT_CANDIDATES = (
    "hiraginosansgb", "pingfang", "stheitilight", "songti",
    "arialunicode", "microsoftyahei", "simhei", "simsun",
    "notosanscjk", "notosanscjksc",
)

# 按字号缓存字体对象，避免每帧反复 match_font 搜索系统字体。
_FONT_CACHE: dict = {}

# 文本渲染 LRU 缓存：键 (id(font), text, color, antialias)。
# 字体对象经 _FONT_CACHE 常驻，id 稳定；超限时淘汰最久未用。
_TEXT_CACHE: "OrderedDict[Tuple, pygame.Surface]" = OrderedDict()
_TEXT_CACHE_MAX = 512


def has_cjk_font() -> bool:
    """系统是否匹配到候选 CJK 字体（供测试跳过无中文字体环境）。"""
    return any(pygame.font.match_font(name) for name in _FONT_CANDIDATES)


def load_cjk_font(size: int) -> pygame.font.Font:
    """返回一个可渲染中文的 pygame 字体；无可用中文字体时回退 Font(None)。"""
    hit = _FONT_CACHE.get(size)
    if hit is not None:
        return hit
    for name in _FONT_CANDIDATES:
        path = pygame.font.match_font(name)
        if path:
            try:
                font = pygame.font.Font(path, size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue
    font = pygame.font.Font(None, size)
    _FONT_CACHE[size] = font
    return font


def render_text(font: pygame.font.Font, text: str, color,
                antialias: bool = True) -> pygame.Surface:
    """缓存渲染文本（LRU），供每帧重复渲染的 HUD / 伤害数字使用。

    文本不变时命中缓存直接返回 Surface，避免每帧调用 font.render。
    """
    key = (id(font), text, color, antialias)
    hit = _TEXT_CACHE.get(key)
    if hit is not None:
        _TEXT_CACHE.move_to_end(key)
        return hit
    surf = font.render(text, antialias, color)
    _TEXT_CACHE[key] = surf
    if len(_TEXT_CACHE) > _TEXT_CACHE_MAX:
        _TEXT_CACHE.popitem(last=False)
    return surf
