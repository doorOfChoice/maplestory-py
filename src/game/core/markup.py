"""对话文本颜色标记：#r 红 / #g 绿 / #b 蓝 / #d 橙 / #k 基色。

官方 Say 文本的单字母颜色码，与实体名标记（#t#o#m#p#i，字母后跟数字）
天然不冲突。systems 层负责在文本里埋码（手写码透传 + 实体名自动包色），
渲染层用 split_colors 把一行折成 (片段, 颜色)，颜色 None 表示基色。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

RGB = Tuple[int, int, int]

MARKUP_COLORS: dict[str, Optional[RGB]] = {
    "r": (228, 68, 68),
    "g": (66, 160, 66),
    "b": (60, 120, 224),
    "d": (224, 138, 32),
    "k": None,
}

_COLOR_TOKEN_RE = re.compile(r"#([rgbdk])")


def split_colors(text: str) -> List[Tuple[str, Optional[RGB]]]:
    """按颜色码把文本切成 (片段, 颜色) 列表；无码时返回单段基色。"""
    out: List[Tuple[str, Optional[RGB]]] = []
    pos = 0
    color: Optional[RGB] = None
    for m in _COLOR_TOKEN_RE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], color))
        color = MARKUP_COLORS[m.group(1)]
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], color))
    return out or [(text, None)]
