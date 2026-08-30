"""NPC 实体：站立动画 + 头顶名牌。

坐标：(x, cy) 为 NPC 脚底锚点（地图 life.cy）。
"""

from __future__ import annotations

from typing import List, Tuple

import pygame

from . import settings
from .assets import Assets


class NPC:
    def __init__(self, assets: Assets, data: dict, index: int):
        self.assets = assets
        self.npc_id = str(int(data["id"]))
        self.index = index
        self.x = float(data["x"])
        self.cy = float(data.get("cy") or data["y"])
        self.flip = bool(data.get("flip"))
        self.name = assets.npc_name(self.npc_id)

        self.frames: List[Tuple[pygame.Surface, int]] = assets.npc_frames(self.npc_id, "stand")
        self.origin = assets.npc_origin(self.npc_id, "stand") or (0, 0)
        self.frame = 0
        self.accum = 0.0
        self.talking = False

    def update(self, dt: float) -> None:
        if not self.frames:
            return
        delay = self.frames[self.frame][1]
        self.accum += dt * 1000.0
        while self.accum >= delay:
            self.accum -= delay
            self.frame = (self.frame + 1) % len(self.frames)

    def rect(self) -> pygame.Rect:
        w, h = 34, 40
        if self.frames:
            w, h = self.frames[self.frame][0].get_size()
        return pygame.Rect(int(self.x - w / 2), int(self.cy - h), w, h)

    def draw(self, surface: pygame.Surface, camera) -> None:
        if not self.frames:
            return
        frame_surf, _ = self.frames[self.frame]
        sx, sy = camera.to_screen(self.x, self.cy)
        top_left = (sx - self.origin[0], sy - self.origin[1])
        surface.blit(frame_surf, (int(top_left[0]), int(top_left[1])))
