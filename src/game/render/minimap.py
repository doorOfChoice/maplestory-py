"""小地图（复刻原版冒险岛）：右上角跟随玩家的窗口。

原版行为：固定大小窗口，以玩家为中心（边缘时夹紧），只显示玩家周围区域；
怪物/NPC/传送门画点并裁剪在框内。

清晰度：底图优先用全分辨率地图 surface（避免低分辨率 canvas 放大后变糊），
从底图上裁出「窗口 = MINIMAP_W×mag 世界像素」的区域并缩小到面板。找不到
底图时按 canvas → 线条绘制依次回退（合成资料可测）。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import pygame

from game import settings


class MiniMap:
    """右上角小地图。数据驱动、可开关。"""

    def __init__(self, footholds: List[Dict], ropes: List[Dict],
                 portals: List[Dict], bounds: Dict[str, int],
                 map_width: int, map_height: int,
                 mag: Optional[int] = None,
                 canvas: Optional[pygame.Surface] = None,
                 map_surface: Optional[pygame.Surface] = None):
        self.visible = True
        self.bounds = bounds
        self.map_width = map_width
        self.map_height = map_height
        self.mag = mag or settings.MINIMAP_MAG_FALLBACK
        self.set_map(footholds, ropes, portals, bounds, map_width, map_height,
                     mag=self.mag, canvas=canvas, map_surface=map_surface)

    # ── 数据 / 重建 ───────────────────────────────────────────────────
    def set_map(self, footholds: List[Dict], ropes: List[Dict],
                portals: List[Dict], bounds: Dict[str, int],
                map_width: int, map_height: int,
                mag: Optional[int] = None,
                canvas: Optional[pygame.Surface] = None,
                map_surface: Optional[pygame.Surface] = None) -> None:
        if mag:
            self.mag = mag
        self.bounds = bounds
        self.map_width = map_width
        self.map_height = map_height
        self.portals = portals

        if map_surface is not None:
            self.base_layer = map_surface
            self.base_scale_x = map_surface.get_width() / max(1, map_width)
            self.base_scale_y = map_surface.get_height() / max(1, map_height)
        elif canvas is not None:
            self.base_layer = canvas
            self.base_scale_x = canvas.get_width() / max(1, map_width)
            self.base_scale_y = canvas.get_height() / max(1, map_height)
        else:
            self.base_layer = self._build_base_layer(footholds, ropes)
            self.base_scale_x = self.base_layer.get_width() / max(1, map_width)
            self.base_scale_y = self.base_layer.get_height() / max(1, map_height)

        self._portals_world = [(float(p["x"]), float(p["y"]))
                               for p in portals if p.get("type") == 2]

    def _build_base_layer(self, footholds: List[Dict],
                          ropes: List[Dict]) -> pygame.Surface:
        """线条回退：把整张地图的平台/绳梯按 1/mag 画成一张底图。"""
        w = max(1, math.ceil(self.map_width / self.mag))
        h = max(1, math.ceil(self.map_height / self.mag))
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((8, 10, 16, settings.MINIMAP_BG_ALPHA))
        for f in footholds:
            x1 = (f["x1"] - self.bounds["left"]) * w / self.map_width
            y1 = (f["y1"] - self.bounds["top"]) * h / self.map_height
            x2 = (f["x2"] - self.bounds["left"]) * w / self.map_width
            y2 = (f["y2"] - self.bounds["top"]) * h / self.map_height
            pygame.draw.line(surf, settings.MINIMAP_PLATFORM_COLOR,
                             (x1, y1), (x2, y2), 1)
        for r in ropes:
            tx = (r["x"] - self.bounds["left"]) * w / self.map_width
            ty1 = (r["y1"] - self.bounds["top"]) * h / self.map_height
            ty2 = (r["y2"] - self.bounds["top"]) * h / self.map_height
            pygame.draw.line(surf, settings.MINIMAP_ROPE_COLOR,
                             (tx, ty1), (tx, ty2), 1)
        return surf

    # ── 坐标换算 ─────────────────────────────────────────────────────
    def view_world_rect(self, player_x: float,
                        player_y: float) -> Tuple[float, float, float, float]:
        """可见世界窗口 (left, top, w, h)，以玩家为中心并夹紧到地图。"""
        vw = settings.MINIMAP_W * self.mag
        vh = settings.MINIMAP_H * self.mag
        left = max(self.bounds["left"],
                   min(player_x - vw / 2, self.bounds["right"] - vw))
        top = max(self.bounds["top"],
                  min(player_y - vh / 2, self.bounds["bottom"] - vh))
        return left, top, vw, vh

    def src_rect(self, player_x: float, player_y: float) -> pygame.Rect:
        """基础层上需截取的矩形（对应可见世界窗口）。"""
        left, top, vw, vh = self.view_world_rect(player_x, player_y)
        sx = int((left - self.bounds["left"]) * self.base_scale_x)
        sy = int((top - self.bounds["top"]) * self.base_scale_y)
        sw = max(1, int(vw * self.base_scale_x))
        sh = max(1, int(vh * self.base_scale_y))
        return pygame.Rect(sx, sy, sw, sh)

    def world_to_panel(self, wx: float, wy: float,
                       view_left: float, view_top: float) -> Tuple[float, float]:
        """世界坐标 → 面板内像素（1 面板像素 = mag 世界像素）。"""
        return ((wx - view_left) / self.mag,
                (wy - view_top) / self.mag)

    @property
    def panel_rect(self) -> pygame.Rect:
        """画布右上角的面板矩形（名牌下移到它下方避让）。"""
        return pygame.Rect(
            settings.VIEW_W - settings.MINIMAP_W - settings.MINIMAP_MARGIN,
            settings.MINIMAP_MARGIN,
            settings.MINIMAP_W, settings.MINIMAP_H)

    # ── 开关 ─────────────────────────────────────────────────────────
    def toggle(self) -> None:
        self.visible = not self.visible

    # ── 绘制 ─────────────────────────────────────────────────────────
    def draw(self, surface, player_x: float, player_y: float,
             facing_right: bool, monsters: List, npcs: List) -> None:
        if not self.visible:
            return
        panel = self.panel_rect
        left, top, _, _ = self.view_world_rect(player_x, player_y)

        # 面板底 + 缩放的小地图
        pygame.draw.rect(surface, (8, 10, 16, settings.MINIMAP_BG_ALPHA), panel)
        src = self.src_rect(player_x, player_y)
        view = self.base_layer.subsurface(src)
        scaled = pygame.transform.smoothscale(
            view, (settings.MINIMAP_W, settings.MINIMAP_H))
        surface.blit(scaled, panel.topleft)

        # 标记（裁剪在面板内）
        self._draw_entities(surface, left, top, panel, monsters, npcs)
        # 玩家箭头（边缘夹紧时偏离中心）
        px, py = self.world_to_panel(player_x, player_y, left, top)
        self._draw_arrow(surface, panel.x + px, panel.y + py,
                         settings.MINIMAP_PLAYER_COLOR, down=False,
                         flip=facing_right)
        pygame.draw.rect(surface, (200, 205, 215), panel, 1)

    def _draw_entities(self, surface, view_left: float, view_top: float,
                       panel: pygame.Rect, monsters: List, npcs: List) -> None:
        for mob in monsters:
            px, py = self.world_to_panel(mob.x, mob.cy, view_left, view_top)
            if self._inside(px, py):
                pygame.draw.circle(surface, settings.MINIMAP_MOB_COLOR,
                                   (int(panel.x + px), int(panel.y + py)), 2)
        for npc in npcs:
            px, py = self.world_to_panel(npc.x, npc.cy, view_left, view_top)
            if self._inside(px, py):
                pygame.draw.circle(surface, settings.MINIMAP_NPC_COLOR,
                                   (int(panel.x + px), int(panel.y + py)), 2)
        for wx, wy in self._portals_world:
            px, py = self.world_to_panel(wx, wy, view_left, view_top)
            if self._inside(px, py):
                self._draw_arrow(surface, panel.x + px, panel.y + py,
                                 settings.MINIMAP_PORTAL_COLOR, down=False)

    def _inside(self, px: float, py: float) -> bool:
        return (0 <= px <= settings.MINIMAP_W and 0 <= py <= settings.MINIMAP_H)

    def _draw_arrow(self, surface, x: float, y: float, color,
                    down: bool = False, flip: bool = False) -> None:
        r = 5
        if down:
            pts = [(x, y + r), (x - r, y - r), (x + r, y - r)]
        else:
            pts = [(x, y - r), (x - r, y + r), (x + r, y + r)]
        if flip:
            pts = [(2 * x - px, py) for px, py in pts]
        pygame.draw.polygon(surface, color, [(int(px), int(py)) for px, py in pts])