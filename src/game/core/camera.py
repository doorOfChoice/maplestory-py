"""视口相机：世界坐标 → 地图图像坐标 → 屏幕坐标。

地图已整图预渲染成一张 Surface，相机只决定 blit 哪个子区域。
对外暴露 cam_img_offset（地图图像坐标下视口左上角），以及两个坐标换算函数。
"""

from __future__ import annotations

from typing import Tuple

from game import settings


class Camera:
    def __init__(self, map_width: int, map_height: int,
                 bounds_left: int, bounds_top: int):
        self.map_width = map_width
        self.map_height = map_height
        self.bounds_left = float(bounds_left)
        self.bounds_top = float(bounds_top)
        self.x = 0.0    # 世界坐标下视口左上角
        self.y = 0.0

    @property
    def img_x(self) -> int:
        return int(self.x - self.bounds_left)

    @property
    def img_y(self) -> int:
        return int(self.y - self.bounds_top)

    @property
    def cam_img_offset(self) -> Tuple[int, int]:
        return (self.img_x, self.img_y)

    def center_on(self, wx: float, wy: float) -> None:
        """把目标世界坐标尽量放到视口中央，并夹紧到地图边界。

        相机位置取整成像素：地图 blit 用 int(img_x)，实体用浮点再取整，
        两者若不共用同一整数基准会在±1px 间来回抖动。取整后两处一致即可消除。
        """
        vw, vh = settings.VIEW_W, settings.VIEW_H
        tx = wx - vw / 2
        tx = max(self.bounds_left, min(tx, self.bounds_left + self.map_width - vw))
        ty = wy - vh * 0.6
        ty = max(self.bounds_top, min(ty, self.bounds_top + self.map_height - vh))
        self.x, self.y = int(tx), int(ty)

    def to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
        """世界坐标 → 屏幕坐标。"""
        return (wx - self.x, wy - self.y)

    def to_image(self, wx: float, wy: float) -> Tuple[float, float]:
        return (wx - self.bounds_left, wy - self.bounds_top)

    def screen_rect_from_image(self) -> "pygame.Rect":
        import pygame
        return pygame.Rect(self.img_x, self.img_y, settings.VIEW_W, settings.VIEW_H)
