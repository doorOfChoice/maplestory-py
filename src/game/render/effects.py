"""WZ 帧特效：命中火花、升级光环等（Effect.wz / Skill.wz / Item.wz canvas 序列）。

Effect 以世界坐标锚点居中播放，帧间隔取自 WZ 的 delay。
"""

from __future__ import annotations

from typing import List, Tuple

import pygame

from game.core.animation import Animation


class Effect:
    def __init__(self, frames: List[Tuple[pygame.Surface, Tuple[int, int], int]],
                 x: float, y: float, loop: bool = False,
                 use_origin: bool = False, follow=None,
                 flip: bool = False, face_follow: bool = False):
        """WZ 帧特效。

        loop=True 时持续循环（通道技按住特效），永不 done；
        use_origin=True 时按帧 origin 对齐锚点（默认以贴图中心对齐）；
        follow 提供 x/y 属性时每帧跟随（如跟随玩家的持续特效）；
        flip=True 时水平镜像，face_follow=True 时随 follow 的朝向实时翻转
        （特效素材朝左，与人物一致；玩家朝右时镜像）。
        """
        self.anim = Animation(frames, loop=loop)
        self.x = x
        self.y = y
        self.loop = loop
        self.use_origin = use_origin
        self.follow = follow
        self.flip = flip
        self.face_follow = face_follow
        self._flip_cache: dict = {}

    @property
    def done(self) -> bool:
        return (not self.loop) and self.anim.done

    def update(self, dt: float) -> None:
        self.anim.advance(dt)
        if self.follow is not None:
            self.x = self.follow.x
            self.y = self.follow.y
            if self.face_follow:
                self.flip = getattr(self.follow, "facing_right", True)

    def _mirror(self, idx: int, img: pygame.Surface) -> pygame.Surface:
        cached = self._flip_cache.get(idx)
        if cached is None:
            cached = pygame.transform.flip(img, True, False)
            self._flip_cache[idx] = cached
        return cached

    def draw(self, surface: pygame.Surface, camera) -> None:
        if self.done:
            return
        idx = self.anim.frame
        img = self.anim.surface
        if img is None:
            return
        if self.flip:
            img = self._mirror(idx, img)
        sx, sy = camera.to_screen(self.x, self.y)
        if self.use_origin:
            ox, oy = self.anim.frames[idx][1]
            if ox or oy:        # 个别 WZ 帧无 origin（0,0）：退回居中，避免贴左上角
                if self.flip:
                    ox = self.anim.frames[idx][0].get_width() - 1 - ox
                surface.blit(img, (int(sx - ox), int(sy - oy)))
                return
        surface.blit(img, (int(sx - img.get_width() / 2),
                           int(sy - img.get_height() / 2)))