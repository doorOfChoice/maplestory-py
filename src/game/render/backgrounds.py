"""背景逐帧渲染：相机视差 + 平铺铺满视口（复刻原版客户端 CMapleMap 背景绘制）。

原版客户端每帧相对相机绘制 back 层，而非把背景烤进整图：
  · 屏幕锚点 = (x, y) - 相机左上角 × (100 + r) / 100（r = rx/ry，视差系数）
  · type 4-7 另加随时间自动滚动（rx/ry 作速度，rx * t / 200）
  · type 1/3/4/6/7 横向平铺、2/3/5/6/7 纵向平铺，步长 cx/cy（0 取图宽/高）
  · 平铺范围铺满整个视口 —— 宽视口下也不会出现烤图的硬边 / 空缺

flip 与半透明（a 字段）在 assets 装载时预烘焙进 Surface，本模块每帧只做
选帧 + 坐标计算 + blit。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

import pygame

from game.core.animation import Animation

# type → 平铺 / 滚动方向（原版客户端语义）
_H_TILE = {1, 3, 4, 6, 7}
_V_TILE = {2, 3, 5, 6, 7}
_H_SCROLL = {4, 6}
_V_SCROLL = {5, 7}

# 单次平铺的最大拷贝数（防御 cx/cy 异常小的脏数据）
_MAX_COPIES = 10_000


@dataclass(frozen=True)
class BackLayer:
    """单个 back 项的渲染数据（帧已预解码为 pygame Surface）。

    frames 元素为 (surface, origin, delay_ms)；origin 为锚点在图内的像素位置。
    """

    x: int
    y: int
    rx: int
    ry: int
    bg_type: int
    cx: int
    cy: int
    front: bool
    frames: List[Tuple[pygame.Surface, Tuple[int, int], int]] = field(
        default_factory=list)


def tile_offsets(first_left: float, size: int, step: int,
                 view_start: int, view_end: int) -> List[int]:
    """平铺偏移列表：第一张图左缘在 first_left、间距 step 时，
    返回覆盖 [view_start, view_end) 所需的全部拷贝偏移（相对锚点，= 索引 × step）。
    覆盖不到时返回空列表。"""
    if step <= 0:
        return [0]
    first = math.floor((view_start - first_left - size) / step) + 1
    last = math.ceil((view_end - first_left) / step) - 1
    if last < first:
        return []
    if last - first > _MAX_COPIES:
        last = first + _MAX_COPIES
    return [index * step for index in range(first, last + 1)]


def layer_blits(layer: BackLayer, cam_x: float, cam_y: float,
                view_w: int, view_h: int, t_ms: float,
                ) -> List[Tuple[pygame.Surface, int, int]]:
    """计算该 back 项本帧的全部 blit：(surface, 屏幕左上 x, y)。"""
    if not layer.frames:
        return []
    surface, (ox, oy), _delay = layer.frames[Animation.frame_at(layer.frames, t_ms)]
    w, h = surface.get_size()

    ax = layer.x - cam_x * (100 + layer.rx) / 100.0
    ay = layer.y - cam_y * (100 + layer.ry) / 100.0
    if layer.bg_type in _H_SCROLL:
        ax += layer.rx * t_ms / 200.0
    if layer.bg_type in _V_SCROLL:
        ay += layer.ry * t_ms / 200.0

    left0 = ax - ox
    top0 = ay - oy
    xs = (tile_offsets(left0, w, layer.cx or w, 0, view_w)
          if layer.bg_type in _H_TILE else [0])
    ys = (tile_offsets(top0, h, layer.cy or h, 0, view_h)
          if layer.bg_type in _V_TILE else [0])
    return [(surface, round(left0 + dx), round(top0 + dy))
            for dx in xs for dy in ys]


def draw_layers(surface: pygame.Surface, layers: List[BackLayer],
                cam_x: float, cam_y: float, view_w: int, view_h: int,
                t_ms: float, *, front: bool) -> None:
    """绘制一层背景（front=False 在地图之前、True 在实体之后），保持 WZ 顺序。"""
    for layer in layers:
        if layer.front != front:
            continue
        for blit_surface, sx, sy in layer_blits(
                layer, cam_x, cam_y, view_w, view_h, t_ms):
            surface.blit(blit_surface, (sx, sy))
