"""可接任务列表（QuestAlarm）分页模型与面板视图（纯几何可测，绘制用原版素材）。

原版「可接任务」弹窗（UIWindow.img/QuestAlarm）：一列任务条目（名称 / Lv 需求 /
类型标签），条目超出一屏时按页翻页。本模块分两部分：
· 纯逻辑：QuestAlarm 分页状态（可见条目切片、翻页边界），不依赖 pygame/WZ。
· 视图：QuestAlarmView 用原版 backgrnd 九宫 tile 竖拼成容器、BtQ 作条目图标，
  只负责「画出来」与「命中哪一行」；几何（panel_height/row_rects）为纯函数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from game.core.fonts import load_cjk_font, render_text

# ── 原版 QuestAlarm tile 实测几何 ─────────────────────────────────────────
TILE_TOP_H = 25          # backgrndmax 高
TILE_MID_H = 18          # backgrndcenter 高
TILE_BOT_H = 5           # backgrndbottom 高
PANEL_W = 200            # 面板宽（tile 为 200 宽画布，不拉伸保持原版清晰）
ROW_H = 24               # 单条任务行高
PAD_TOP = 4              # 顶帽下方留白


@dataclass(frozen=True)
class QuestEntry:
    """单条可接任务。"""
    title: str
    level: int = 0
    tag: str = ""          # 类型标签（推荐/技能/剧情…），可为空
    subtitle: str = ""     # 附加说明行，可为空


@dataclass
class QuestAlarm:
    """可接任务列表的分页状态机。"""
    entries: List[QuestEntry] = field(default_factory=list)
    per_page: int = 7
    _page: int = field(default=0, init=False, repr=False)

    @property
    def page(self) -> int:
        return self._page

    @property
    def page_count(self) -> int:
        n = len(self.entries)
        return max(1, (n + self.per_page - 1) // self.per_page)

    def visible(self) -> List[QuestEntry]:
        start = self._page * self.per_page
        return self.entries[start:start + self.per_page]

    @property
    def can_next(self) -> bool:
        return self._page < self.page_count - 1

    @property
    def can_prev(self) -> bool:
        return self._page > 0

    def next_page(self) -> bool:
        """下一页；已在末页返回 False。"""
        if not self.can_next:
            return False
        self._page += 1
        return True

    def prev_page(self) -> bool:
        """上一页；已在首页返回 False。"""
        if not self.can_prev:
            return False
        self._page -= 1
        return True


class QuestAlarmView:
    """可接任务列表面板：画原版容器 + 条目 + 翻页提示，并支持命中选行。"""

    def __init__(self, model: QuestAlarm):
        self.model = model
        self.font = load_cjk_font(13)
        self.font_small = load_cjk_font(11)

    # ── 纯几何（供测试）──────────────────────────────────────────────
    @classmethod
    def panel_height(cls, n_rows: int) -> int:
        """面板总高 = 顶帽 + 留白 + 行数×行高 + 底帽。"""
        return TILE_TOP_H + PAD_TOP + n_rows * ROW_H + TILE_BOT_H

    @classmethod
    def row_rects(cls, x: int, y: int, w: int, n_rows: int,
                  ) -> List[Tuple[int, int, int, int]]:
        """各条目行的 (x, y, w, h)；从顶帽下方起、逐行等距。"""
        top = y + TILE_TOP_H + PAD_TOP
        return [(x, top + i * ROW_H, w, ROW_H) for i in range(n_rows)]

    # ── 绘制 ─────────────────────────────────────────────────────────
    def _tile(self, assets, name: str):
        return assets.ui_surface("UIWindow.img", f"QuestAlarm/{name}")

    def draw(self, surface, assets, x: int, y: int) -> None:
        n = len(self.model.visible())
        h = self.panel_height(n)
        body_h = h - TILE_TOP_H - TILE_BOT_H

        top = self._tile(assets, "backgrndmax")
        ctr = self._tile(assets, "backgrndcenter")
        bot = self._tile(assets, "backgrndbottom")
        if top is not None:
            surface.blit(top[0], (x, y))
        mid_y = y + TILE_TOP_H
        span = math.ceil(body_h / TILE_MID_H)
        for i in range(span):
            if ctr is not None:
                surface.blit(ctr[0], (x, mid_y + i * TILE_MID_H))
        if bot is not None:
            surface.blit(bot[0], (x, y + h - TILE_BOT_H))

        icon = self._tile(assets, "BtQ/normal/0")
        for i, entry in enumerate(self.model.visible()):
            rx, ry, rw, rh = self.row_rects(x, y, PANEL_W, n)[i]
            if icon is not None:
                surface.blit(icon[0], (rx + 4, ry + (rh - icon[0].get_height()) // 2))
            title_color = (70, 62, 52) if entry.tag else (90, 82, 70)
            t = render_text(self.font, entry.title, title_color)
            surface.blit(t, (rx + 22, ry + (rh - t.get_height()) // 2))
            if entry.level:
                lv = render_text(self.font_small, f"Lv {entry.level}", (150, 140, 128))
                surface.blit(lv, (rx + rw - lv.get_width() - 8,
                                  ry + (rh - lv.get_height()) // 2))

        # 翻页提示（右下角）
        hint = ""
        if self.model.can_next:
            hint = "▼ 下一页"
        elif self.model.can_prev:
            hint = "▲ 上一页"
        if hint:
            ht = render_text(self.font_small, hint, (250, 244, 230))
            surface.blit(ht, (x + PANEL_W - ht.get_width() - 6,
                              y + h - ht.get_height() - 4))

    def draw_panel_width(self, assets) -> int:
        """面板宽（供调用方定位）。"""
        if self._tile(assets, "backgrndmax") is not None:
            return PANEL_W
        return PANEL_W

    def hit_index(self, assets, x: int, y: int, pos: Tuple[int, int]) -> Optional[int]:
        """命中某条目行 → 返回其在当前页的序号；未命中返回 None。"""
        n = len(self.model.visible())
        if n == 0:
            return None
        h = self.panel_height(n)
        if not (x <= pos[0] < x + PANEL_W and y <= pos[1] < y + h):
            return None
        for i, (rx, ry, rw, rh) in enumerate(self.row_rects(x, y, PANEL_W, n)):
            if rx <= pos[0] < rx + rw and ry <= pos[1] < ry + rh:
                return i
        return None
