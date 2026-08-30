"""WZ 帧特效：命中火花、升级光环等（Effect.wz / Skill.wz / Item.wz canvas 序列）。

Effect 以世界坐标锚点居中播放，帧间隔取自 WZ 的 delay（缺省 100ms）。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame


class Effect:
    def __init__(self, frames: List[Tuple[pygame.Surface, Tuple[int, int], int]],
                 x: float, y: float, delay_ms: int = 100):
        self.frames = frames
        self.x = x
        self.y = y
        self.delay = max(1, delay_ms)
        self.frame = 0
        self.accum = 0.0
        self.done = not frames

    def update(self, dt: float) -> None:
        if self.done or not self.frames:
            self.done = True
            return
        self.accum += dt * 1000.0
        while self.accum >= self.delay:
            self.accum -= self.delay
            self.frame += 1
            if self.frame >= len(self.frames):
                self.done = True
                return

    def draw(self, surface: pygame.Surface, camera) -> None:
        if self.done or not self.frames:
            return
        img = self.frames[self.frame][0]
        sx, sy = camera.to_screen(self.x, self.y)
        surface.blit(img, (int(sx - img.get_width() / 2),
                           int(sy - img.get_height() / 2)))
