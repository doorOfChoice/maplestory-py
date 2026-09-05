"""战斗明细渲染：右下角击杀/拾取浮动条目（原版布局的自制替身）。

条目自下向上堆叠（最新在底部贴状态栏），一次事件一条，到期淡出。
拾取条目带官方图标（金币 0900 金袋 / 物品图标），击杀条目纯文本；
素材缺失退化为纯文本。纯逻辑在 core/combat_log.py，这里只读不写。
"""

from __future__ import annotations

from typing import Optional, Tuple

import pygame

from game.core.combat_log import CombatLog, CombatLogEntry
from game.core.fonts import load_cjk_font, render_text

ROW_W = 210               # 单行最大宽度（含图标）
ICON_BOX = 30             # 图标盒边长（超尺寸等比缩入）
LINE_H = 22               # 行高
ROW_MARGIN = 10           # 距屏右与状态栏的间距

# 统一白色字 + 黑色投影（原版的描边替身），保证压在地图上仍可读
TEXT_COLOR = (245, 245, 245)
SHADOW_COLOR = (0, 0, 0)


class CombatLogView:
    def __init__(self) -> None:
        # 浮动明细压在地图上：13px + 黑体中粗字重，避免细笔画抗锯齿发糊
        self.font = load_cjk_font(13, ("stheitimedium",))
        self._icon_cache: dict = {}

    # ── 图标 ─────────────────────────────────────────────────────────
    def entry_icon(self, entry: CombatLogEntry, assets) -> Optional[pygame.Surface]:
        """按条目类型解析图标（等比缩进 ICON_BOX 盒）；缺素材返回 None。"""
        key = (entry.kind, entry.key, entry.amount)
        hit = self._icon_cache.get(key)
        if hit is not None or key in self._icon_cache:
            return hit
        raw = self._raw_icon(entry, assets)
        icon = self._fit(raw) if raw is not None else None
        if len(self._icon_cache) > 64:      # 简单防膨胀（图标种类有限，几乎不触发）
            self._icon_cache.clear()
        self._icon_cache[key] = icon
        return icon

    def _raw_icon(self, entry: CombatLogEntry, assets) -> Optional[pygame.Surface]:
        if assets is None or entry.kind == "exp":   # 击杀条目纯文本，不带怪图标
            return None
        try:
            if entry.kind == "meso":
                frames = assets.meso_frames(entry.amount)
                return frames[0][0] if frames else None
            icon = assets.item_icon(entry.key) or assets.equip_icon(entry.key)
            return icon
        except Exception:
            return None

    @staticmethod
    def _fit(surf: Optional[pygame.Surface]) -> Optional[pygame.Surface]:
        if surf is None or max(surf.get_size()) <= ICON_BOX:
            return surf
        scale = ICON_BOX / max(surf.get_size())
        w = max(1, int(surf.get_width() * scale))
        h = max(1, int(surf.get_height() * scale))
        return pygame.transform.smoothscale(surf, (w, h))

    # ── 文本 ─────────────────────────────────────────────────────────
    def entry_text(self, entry: CombatLogEntry) -> str:
        """条目文案：金币/经验显增量，物品显名称×件数。"""
        if entry.kind == "meso":
            return f"拾取金币 +{entry.amount:,}"
        if entry.kind == "exp":
            return f"击败 {entry.name} +{entry.amount:,} 经验"
        return f"获得 {entry.name} ×{entry.amount}"

    # ── 绘制 ─────────────────────────────────────────────────────────
    def draw(self, surface, log: CombatLog, assets, bar_h: int) -> None:
        """右下角自下向上堆叠绘制；每条按剩余寿命整体淡出。"""
        if not log.entries:
            return
        vw, vh = surface.get_width(), surface.get_height()
        y = vh - bar_h - ROW_MARGIN - LINE_H
        for entry in reversed(log.entries):
            row = self._render_row(entry, assets)
            fade = entry.alpha
            if fade < 1.0:
                row = self._fade(row, fade)
            surface.blit(row, (vw - ROW_MARGIN - row.get_width(), y))
            y -= LINE_H + 2

    @staticmethod
    def _fade(row: pygame.Surface, fade: float) -> pygame.Surface:
        """逐像素乘 alpha 淡出。不用 set_alpha：它对逐像素 alpha 面走 SDL
        通用路径，小字号抗锯齿文字在低透明度下会出噪点（字面"花掉"）。"""
        faded = row.copy()
        mod = pygame.Surface(faded.get_size(), pygame.SRCALPHA)
        mod.fill((255, 255, 255, max(0, min(255, int(255 * fade)))))
        faded.blit(mod, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return faded

    def _render_row(self, entry: CombatLogEntry, assets) -> pygame.Surface:
        text_str = self.entry_text(entry)
        text = render_text(self.font, text_str, TEXT_COLOR)
        shadow = render_text(self.font, text_str, SHADOW_COLOR)
        icon = self.entry_icon(entry, assets)
        h = LINE_H
        tx = ICON_BOX + 6 if icon is not None else 4
        ty = (h - text.get_height()) // 2
        row = pygame.Surface((min(tx + text.get_width() + 6, ROW_W), h),
                             pygame.SRCALPHA)
        if icon is not None:
            row.blit(icon, (3, (h - icon.get_height()) // 2))
        # 1px 斜投影：够垫底可读又不糊字
        row.blit(shadow, (tx + 1, ty + 1))
        row.blit(text, (tx, ty))
        return row
