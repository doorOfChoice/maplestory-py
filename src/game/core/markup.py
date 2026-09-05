"""对话文本颜色标记：#r 红 / #g 绿 / #b 蓝 / #d 橙 / #e 强调 / #k 或 #n 基色。

官方 Say 文本的单字母颜色码，与实体名标记（#t#o#m#p#i，字母后跟数字）
天然不冲突。#e ... #n 是官方强调对（如剧情重点词），#n 与 #k 同义回基色。
systems 层负责在文本里埋码（手写码透传 + 实体名自动包色），
渲染层用 split_colors 把一行折成 (片段, 颜色)，颜色 None 表示基色。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

RGB = Tuple[int, int, int]

MARKUP_COLORS: dict[str, Optional[RGB]] = {
    "r": (228, 68, 68),
    "g": (66, 160, 66),
    "b": (60, 120, 224),
    "d": (224, 138, 32),
    "e": (232, 104, 24),
    "k": None,
    "n": None,
}

_COLOR_TOKEN_RE = re.compile(r"#([rgbdken])")


def split_colors(text: str,
                 initial: Optional[RGB] = None) -> List[Tuple[str, Optional[RGB]]]:
    """按颜色码把文本切成 (片段, 颜色) 列表；无码时返回单段基色。

    initial 为上游残留的色码状态（如跨图标段的续色），等价于文本前置该色。
    """
    out: List[Tuple[str, Optional[RGB]]] = []
    pos = 0
    color: Optional[RGB] = initial
    for m in _COLOR_TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], color))
        color = MARKUP_COLORS[m.group(1)]
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], color))
    return out or [(text, initial)]


def final_color(text: str, initial: Optional[RGB] = None) -> Optional[RGB]:
    """返回 text 消费完色码后的残留颜色状态（无码则原样透传 initial）。"""
    color = initial
    for m in _COLOR_TOKEN_RE.finditer(text):
        color = MARKUP_COLORS[m.group(1)]
    return color


# ── #c 内联物品图标 ─────────────────────────────────────────────────

_ICON_CODE_RE = re.compile(r"#c(\d+)#")


def split_item_icons(text: str) -> List[Tuple[str, object]]:
    """把文本按 #c<物品id># 内联图标码切成 ("t", str) / ("i", int) 段序列。"""
    text = text or ""
    out: List[Tuple[str, object]] = []
    pos = 0
    for m in _ICON_CODE_RE.finditer(text):
        if m.start() > pos:
            out.append(("t", text[pos:m.start()]))
        out.append(("i", int(m.group(1))))
        pos = m.end()
    if pos < len(text):
        out.append(("t", text[pos:]))
    return out


# ── 折行片段：文本段 / 图标段 ───────────────────────────────────────


@dataclass
class TextSeg:
    """一段同色文本；color None = 基色。"""
    text: str
    color: Optional[RGB] = None


@dataclass(frozen=True)
class IconSeg:
    """内联物品图标占位段，由渲染层解析成 Surface。"""
    item_id: int


Segment = Union[TextSeg, IconSeg]
