"""开屏动画：首次进入 / 地图切换时在资源后台加载期间绘制的启动画面。

纯 pygame 绘制，不依赖任何 WZ 资产（保证在资源加载前就能立刻出画面）。
设计：深色渐变底 + 居中标题 + 旋转弧线 + 「正在进入冒险岛…」+ 底部进度条。
进度条与提示由外部在后台加载阶段边界更新，逐帧实时反馈。

坐标约定：绘制目标为内部视口 VIEW_W × VIEW_H 的 canvas 平面。
"""

from __future__ import annotations

import math
from typing import Tuple

import pygame

from game import settings
from game.core.fonts import load_cjk_font

# 配色
_BG_TOP = (18, 22, 34)
_BG_BOTTOM = (8, 10, 16)
_ACCENT = (120, 190, 255)
_TITLE = (240, 244, 252)
_SUBTITLE = (150, 165, 190)
_BAR_BG = (34, 42, 60)
_BAR_TRACK = (200, 214, 235)


class Splash:
    """一次性开屏渲染器：首屏/切图加载时驱动，进度由外部 push。"""

    def __init__(self, width: int = settings.VIEW_W, height: int = settings.VIEW_H):
        self.width = width
        self.height = height
        self._t = 0.0
        # 预渲染竖排渐变底（缓存，避免每帧生成）
        self._bg = self._build_background()

    def update(self, dt: float) -> None:
        self._t += dt

    def draw(self, surface, progress: float = 0.0, status: str = "") -> None:
        surface.blit(self._bg, (0, 0))
        cx = self.width // 2
        cy = self.height // 2

        # 旋转弧线（转圈光标），中心在标题下方
        spinner_r = 62
        self._draw_spinner(surface, cx, cy - 70, spinner_r)

        # 标题 + 副标题
        title_font = load_cjk_font(64)
        sub_font = load_cjk_font(26)
        title = title_font.render("MapleStory 113", True, _TITLE)
        sub = sub_font.render("弓箭手村东部小山 · pygame", True, _SUBTITLE)
        surface.blit(title, title.get_rect(center=(cx, cy + 20)))
        surface.blit(sub, sub.get_rect(center=(cx, cy + 58)))

        # 提示文字
        hint = status or "正在进入冒险岛"
        hint_surf = sub_font.render(f"{hint}…", True, _SUBTITLE)
        surface.blit(hint_surf, hint_surf.get_rect(center=(cx, cy + 110)))

        # 底部进度条
        self._draw_progress(surface, cx, cy + 160, progress)

    # ── 组件 ───────────────────────────────────────────────────────
    def _build_background(self) -> pygame.Surface:
        bg = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        steps = self.height
        for i in range(steps):
            t = i / max(steps - 1, 1)
            color = tuple(
                int(a + (b - a) * t) for a, b in zip(_BG_TOP, _BG_BOTTOM)
            )
            pygame.draw.line(bg, color, (0, i), (self.width, i))
        return bg

    def _draw_spinner(self, surface, cx, cy, r) -> None:
        # 一圈细弧 + 一个高亮小段（指示旋转方向）
        for i in range(48):
            ang = self._t * 3.0 + i / 48.0 * math.tau
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            color = _ACCENT if i % 12 == 0 else (30, 42, 64)
            pygame.draw.circle(surface, color, (int(x), int(y)), 3)

    def _draw_progress(self, surface, cx, y, progress) -> None:
        bar_w = 460
        bar_h = 14
        left = cx - bar_w // 2
        top = y
        # 底槽
        pygame.draw.rect(surface, _BAR_BG,
                         (left, top, bar_w, bar_h), border_radius=7)
        # 填充
        fill = int(bar_w * max(0.0, min(1.0, progress)))
        if fill > 0:
            pygame.draw.rect(surface, _BAR_TRACK, (left, top, fill, bar_h),
                             border_radius=7)
        # 外框
        pygame.draw.rect(surface, (70, 86, 116),
                         (left, top, bar_w, bar_h), width=1, border_radius=7)
        # 百分比
        font = load_cjk_font(20)
        pct = font.render(f"{int(progress * 100)}%", True, _SUBTITLE)
        surface.blit(pct, pct.get_rect(center=(cx, top + bar_h + 14)))
