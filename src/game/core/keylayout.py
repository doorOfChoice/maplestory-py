"""虚拟键盘布局：键盘式按键设置窗的键格数据。

覆盖常用可绑定键：数字行 + 字母主区 + Space/Enter/Tab + 方向键。
Esc 入列只为显示「固定取消」，由窗口层排除出绑定落点。
width 以键帽为单位（1 = 标准单键），首行最宽决定窗体尺寸；
键面文字用 keybindings.display_key 现算，布局不重复存名字。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pygame


@dataclass(frozen=True)
class KeySpec:
    key: int
    width: float = 1.0


def _digits() -> List[KeySpec]:
    return [KeySpec(getattr(pygame, f"K_{d}")) for d in "1234567890"]


def _letters(word: str) -> List[KeySpec]:
    return [KeySpec(getattr(pygame, f"K_{ch}")) for ch in word]


KEY_ROWS: List[List[KeySpec]] = [
    [KeySpec(pygame.K_ESCAPE), KeySpec(pygame.K_BACKQUOTE), *_digits(),
     KeySpec(pygame.K_MINUS), KeySpec(pygame.K_EQUALS),
     KeySpec(pygame.K_BACKSPACE, 2.0)],
    [KeySpec(pygame.K_TAB, 1.5), *_letters("qwertyuiop"),
     KeySpec(pygame.K_LEFTBRACKET), KeySpec(pygame.K_RIGHTBRACKET),
     KeySpec(pygame.K_BACKSLASH, 1.5)],
    [KeySpec(pygame.K_CAPSLOCK, 1.75), *_letters("asdfghjkl"),
     KeySpec(pygame.K_SEMICOLON), KeySpec(pygame.K_QUOTE),
     KeySpec(pygame.K_RETURN, 2.25)],
    [KeySpec(pygame.K_LSHIFT, 2.25), *_letters("zxcvbnm"),
     KeySpec(pygame.K_COMMA), KeySpec(pygame.K_PERIOD),
     KeySpec(pygame.K_SLASH), KeySpec(pygame.K_RSHIFT, 2.25)],
    [KeySpec(pygame.K_SPACE, 8.0)],
    [KeySpec(pygame.K_LEFT), KeySpec(pygame.K_UP),
     KeySpec(pygame.K_DOWN), KeySpec(pygame.K_RIGHT)],
]


def key_units_total(row: List[KeySpec]) -> float:
    """一行的单位宽合计（首行 = 全宽基准）。"""
    return sum(spec.width for spec in row)
