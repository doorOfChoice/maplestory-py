"""自绘鼠标光标：官方客户端的鼠标样式不在 WZ 里（在 cursor.wzl），
本项目改用 resources/cursor/ 下的 PNG 序列，隐藏系统光标后每帧跟随绘制。

四种状态（按优先级）：按住左键 → click；按住右键 → click_right；
拖拽进行中（物品/技能/按键/窗口标题） → drag（抓握手动画）；
其余（含普通悬停） → default（指手）。热点取每帧最顶不透明像素行的
中心，保证指尖对准鼠标点。
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import pygame

from game import settings

DEFAULT = "default"
DRAG = "drag"
CLICK = "click"
CLICK_RIGHT = "click_right"

_ALPHA_THRESHOLD = 32


def hotspot_of(surface: pygame.Surface) -> Tuple[int, int]:
    """取表面最顶一行不透明像素的中心作为热点（指尖/箭头顶端）。"""
    w, h = surface.get_size()
    for y in range(h):
        xs = [x for x in range(w)
              if surface.get_at((x, y))[3] >= _ALPHA_THRESHOLD]
        if xs:
            return ((min(xs) + max(xs)) // 2, y)
    return (0, 0)


class GameCursor:
    """持有各状态帧序列，按时间取帧并带热点偏移地绘制到画布上。"""

    def __init__(self, frames: Mapping[str, Sequence[pygame.Surface]],
                 frame_ms: int = settings.CURSOR_FRAME_MS) -> None:
        self.frames: Dict[str, List[pygame.Surface]] = \
            {k: list(v) for k, v in frames.items() if v}
        self._hotspots = {k: [hotspot_of(s) for s in v]
                          for k, v in self.frames.items()}
        self._frame_ms = frame_ms
        self._state = DEFAULT
        self._t0 = 0
        self._now = 0

    @staticmethod
    def pick_state(dragging: bool, left_down: bool,
                   right_down: bool) -> str:
        """状态选择：拖拽中优先（此时左键仍按住），其次左键、右键。"""
        if dragging:
            return DRAG
        if left_down:
            return CLICK
        if right_down:
            return CLICK_RIGHT
        return DEFAULT

    @classmethod
    def from_dir(cls, path: Path) -> Optional["GameCursor"]:
        """从目录加载官方命名的光标 PNG；任一文件缺失则返回 None（回退系统光标）。"""
        spec = {
            DEFAULT: ["point.png"],
            DRAG: [f"grab-page-0{i}.png" for i in range(1, 6)],
            CLICK: ["point-click-page-01.png", "point-click-page-02.png"],
            CLICK_RIGHT: ["point-click-right-page-01.png",
                          "point-click-right-page-02.png"],
        }
        frames: Dict[str, List[pygame.Surface]] = {}
        for state, names in spec.items():
            loaded = []
            for n in names:
                f = Path(path) / n
                if not f.exists():
                    return None
                surf = pygame.image.load(str(f)).convert_alpha()
                loaded.append(surf)
            frames[state] = loaded
        return cls(frames)

    def update(self, state: str, now_ms: int) -> None:
        """切换状态并推进动画时钟；未知状态保持当前帧不变。"""
        if state not in self.frames:
            return
        if state != self._state:
            self._state = state
            self._t0 = now_ms
        self._now = now_ms

    @property
    def _index(self) -> int:
        frames = self.frames[self._state]
        return ((self._now - self._t0) // self._frame_ms) % len(frames)

    @property
    def current(self) -> pygame.Surface:
        return self.frames[self._state][self._index]

    def draw(self, surface, pos: Tuple[int, int]) -> None:
        """把当前帧按热点对齐到 pos（画布/视口坐标）绘制。"""
        i = self._index
        hx, hy = self._hotspots[self._state][i]
        surface.blit(self.frames[self._state][i], (pos[0] - hx, pos[1] - hy))
