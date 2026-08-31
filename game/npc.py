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
        # 任务指示灯（由 Game 每帧传入 marker）
        self._marker = -1
        self._marker_accum = 0.0

    def set_marker(self, marker: int) -> None:
        self._marker = marker

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

    def draw(self, surface: pygame.Surface, camera, marker: int = -1) -> None:
        if not self.frames:
            return
        frame_surf, _ = self.frames[self.frame]
        sx, sy = camera.to_screen(self.x, self.cy)
        top_left = (sx - self.origin[0], sy - self.origin[1])
        surface.blit(frame_surf, (int(top_left[0]), int(top_left[1])))
        if marker >= 0:
            self._draw_marker(surface, camera, marker)

    def _draw_marker(self, surface: pygame.Surface, camera, marker: int) -> None:
        """头顶任务灯泡：0=可接取 1=进行中 2=可交付（QuestIcon 帧动画）。"""
        frames = self.assets.quest_icon_frames(marker)
        if not frames:
            return
        self._marker_accum += 1
        total = sum(d for _, d in frames) or 1
        img = frames[int(self._marker_accum * 60 % total) % len(frames)][0]
        sx, sy = camera.to_screen(self.x, self.cy)
        w, h = img.get_size()
        # 画在 NPC 头顶：以 sprite 顶边为基准再抬高一点
        top = sy - self.origin[1] - h + 6
        surface.blit(img, (int(sx - w / 2), int(top)))
