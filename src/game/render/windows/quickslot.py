"""快捷栏组件：UIWindow/ShortCut 竖条，技能图标 + 冷却遮罩 + 键位角标。

常驻装饰层（interactive=False）：不置顶、不拦截事件，点击穿透给下层。
自旧 panels.draw_quickslots 迁移，布局/素材路径等价。
"""

from __future__ import annotations

from typing import Tuple

import pygame

from game import settings
from game.core.keybindings import display_key
from game.render.windows.core.widgets import wz_surface
from game.render.windows.core.window import Window

SHT_BG = "ShortCut/backgrnd"
SHT_W, SHT_H = 93, 244
SHT_CELL_X = [4, 48]
SHT_CELL_Y = [24, 58, 93, 127, 162, 196]
SHT_CELL_W, SHT_CELL_H = 41, 34
BAR_RESERVE = 58     # 底部状态栏预留高度（无 StatusBar 素材时同值）


class QuickSlotBar(Window):
    """技能快捷栏：读玩家 hotkeys 画 2 列 × 6 行。"""

    key = "quickslot"
    interactive = False

    def __init__(self, svc) -> None:
        super().__init__(svc)
        self.visible = True

    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return vw - SHT_W - 4, vh - SHT_H - BAR_RESERVE - 2

    def _slot_label(self, slot: int) -> str:
        """角标键名：改绑后显示新键（如 Q/F5），未绑回退槽号。"""
        if self.svc.bindings is not None:
            kc = self.svc.bindings.slot_key(slot)
            if kc is not None and kc > 0:
                return display_key(kc)
        return str(slot)

    def draw(self, surface) -> None:
        player = self.svc.player()
        if player is None:
            return
        fs = self.svc.ui.font_small
        bg = wz_surface(self.svc, SHT_BG)
        if bg is None:
            self._draw_fallback(surface, player, fs)
            return
        x, y = self.place(surface, (SHT_W, SHT_H))
        surface.blit(bg, (x, y))
        hotkeys = sorted(player.skills.hotkeys)
        for n, hk in enumerate(hotkeys):
            sid = player.skills.hotkeys[hk]
            d = player.skills.defs.get(sid)
            if d is None or player.skills.levels.get(sid, 0) <= 0:
                continue
            col, row_idx = n % len(SHT_CELL_X), n // len(SHT_CELL_X)
            if row_idx >= len(SHT_CELL_Y):
                break
            cx = x + SHT_CELL_X[col]
            cy = y + SHT_CELL_Y[row_idx]
            cell = pygame.Rect(cx, cy, SHT_CELL_W, SHT_CELL_H)
            icon = self.svc.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (30, 30)),
                             (cx + (cell.w - 30) // 2, cy + (cell.h - 30) // 2))
            self._draw_cooldown(surface, player, cell, sid)
            kb = fs.render(self._slot_label(hk), True, (255, 220, 90))
            surface.blit(kb, (cell.x + 3, cell.y + 1))
            lv = player.skills.levels[sid]
            mp = fs.render(f"{d.stat(lv, 'mpCon', 0)}", True, (140, 180, 240))
            surface.blit(mp, (cell.right - mp.get_width() - 2,
                              cell.bottom - mp.get_height() - 1))

    def _draw_cooldown(self, surface, player, cell: pygame.Rect,
                       sid: str) -> None:
        cd = player.skills.cooldowns.get(sid, 0.0)
        total = settings.SKILL_COOLDOWN.get(sid, 0.8)
        if cd <= 0:
            return
        frac = max(0.0, min(1.0, cd / total))
        cover_h = max(1, int(cell.h * frac))
        shade = pygame.Surface((cell.w, cover_h), pygame.SRCALPHA)
        shade.fill((10, 10, 14, 150))
        surface.blit(shade, (cell.x, cell.bottom - cover_h))

    def _draw_fallback(self, surface, player, fs) -> None:
        vw, vh = surface.get_width(), surface.get_height()
        y = vh - 146
        for key in sorted(player.skills.hotkeys):
            sid = player.skills.hotkeys[key]
            d = player.skills.defs.get(sid)
            if d is None or player.skills.levels.get(sid, 0) <= 0:
                continue
            lv = player.skills.levels[sid]
            slot = pygame.Rect(0, 0, 46, 46)
            slot.right = vw - 14
            slot.y = y
            pygame.draw.rect(surface, (18, 22, 30, 216), slot, border_radius=8)
            pygame.draw.rect(surface, (70, 76, 90), slot, 1, border_radius=8)
            icon = self.svc.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (34, 34)),
                             (slot.x + 6, slot.y + 6))
            self._draw_cooldown(surface, player, slot, sid)
            kb = fs.render(self._slot_label(key), True, (255, 220, 90))
            surface.blit(kb, (slot.x + 3, slot.y + 2))
            mp = fs.render(f"{d.stat(lv, 'mpCon', 0)}", True, (120, 170, 230))
            surface.blit(mp, (slot.right - mp.get_width() - 3,
                              slot.bottom - mp.get_height() - 2))
            y -= slot.h + 8
