"""WZ 帧特效：命中火花、升级光环等（Effect.wz / Skill.wz / Item.wz canvas 序列）。

Effect 以世界坐标锚点居中播放，帧间隔取自 WZ 的 delay。
"""

from __future__ import annotations

from typing import List, Tuple

import pygame

from .animation import Animation


class Effect:
    def __init__(self, frames: List[Tuple[pygame.Surface, Tuple[int, int], int]],
                 x: float, y: float):
        self.anim = Animation(frames, loop=False)
        self.x = x
        self.y = y

    @property
    def done(self) -> bool:
        return self.anim.done

    def update(self, dt: float) -> None:
        self.anim.advance(dt)

    def draw(self, surface: pygame.Surface, camera) -> None:
        if self.done:
            return
        img = self.anim.surface
        if img is None:
            return
        sx, sy = camera.to_screen(self.x, self.y)
        surface.blit(img, (int(sx - img.get_width() / 2),
                           int(sy - img.get_height() / 2)))