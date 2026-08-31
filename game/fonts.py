"""CJK 中文字体加载：避免 pygame 默认字体（Font(None)）把汉字渲染成方块。

pygame 的 `pygame.font.Font(None, size)` 只带 ASCII 字形，遇到 CJK 会统一
绘制成 .notdef 矩形（乱码口口口）。这里按平台常见中文字体名依次匹配系统
字体，首个命中即返回；全部落空时回退 Font(None)（保持可用，不抛异常）。
"""

from __future__ import annotations

import pygame

# 候选顺序：macOS 优先（项目运行环境），再广覆盖 Windows / Linux 常见中文字体
_FONT_CANDIDATES = (
    "hiraginosansgb", "pingfang", "stheitilight", "songti",
    "arialunicode", "microsoftyahei", "simhei", "simsun",
    "notosanscjk", "notosanscjksc",
)


def has_cjk_font() -> bool:
    """系统是否匹配到候选 CJK 字体（供测试跳过无中文字体环境）。"""
    return any(pygame.font.match_font(name) for name in _FONT_CANDIDATES)


def load_cjk_font(size: int) -> pygame.font.Font:
    """返回一个可渲染中文的 pygame 字体；无可用中文字体时回退 Font(None)。"""
    for name in _FONT_CANDIDATES:
        path = pygame.font.match_font(name)
        if path:
            try:
                return pygame.font.Font(path, size)
            except Exception:
                continue
    return pygame.font.Font(None, size)
