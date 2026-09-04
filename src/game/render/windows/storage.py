"""仓库窗口组件：背包 ↔ 仓库双向存取（自旧 storage_panel 迁移）。

左侧 6×8=48 格仓库（STORAGE_CAP），右侧背包列表；点仓库格取出到背包，
点背包物品存入仓库，复用 Inventory.storage_add / storage_take。
toast 归 WindowManager 全局；Esc / 切图 / × 关闭。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game import settings
from game.render.windows.widgets import draw_menu_bg, ellipsize
from game.render.windows.window import Window
from game.systems.inventory import Item, item_kind

PANEL_W, PANEL_H = 600, 330
TITLE_H = 26
CELL = 32
STORAGE_COLS = 6
STORAGE_ROWS = 8
ROW_H = 30


class StorageWindow(Window):
    """仓库存取面板：点左格取出、点右格存入。"""

    key = "storage"
    escape_closes = True
    closes_on_map_change = True

    def __init__(self, svc) -> None:
        super().__init__(svc)
        self.storage_rects: List[Tuple[pygame.Rect, int]] = []
        self.bag_rects: List[Tuple[pygame.Rect, int]] = []
        self._scroll = 0

    # ── 开关 ───────────────────────────────────────────────────────
    def open(self) -> None:
        self.visible = True
        self._scroll = 0

    # ── 数据 ───────────────────────────────────────────────────────
    def _bag_entries(self, player) -> List[Tuple[Tuple, "Item"]]:
        inv = player.inventory
        entries = [(("stack", it.id), it) for it in inv.consumes.values()]
        entries += [(("stack", it.id), it) for it in inv.etcs.values()]
        entries += [(("equip", i), it) for i, it in enumerate(inv.equips)]
        return entries

    def _vis_rows(self) -> int:
        return max(1, (PANEL_H - TITLE_H - 20 - 56) // ROW_H)

    def _icon(self, item_id: str) -> Optional[pygame.Surface]:
        if item_kind(item_id) == "equip":
            return self.svc.assets.equip_icon(item_id)
        return self.svc.assets.item_icon(item_id)

    # ── 交互 ───────────────────────────────────────────────────────
    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        player = self.svc.player()
        for rect, idx in self.storage_rects:
            if rect.collidepoint(pos):
                self._take_to_bag(player, idx)
                return True
        for rect, idx in self.bag_rects:
            if rect.collidepoint(pos):
                self._store_to_storage(player, idx)
                return True
        return True

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        entries = self._bag_entries(self.svc.player())
        max_scroll = max(0, len(entries) - self._vis_rows())
        self._scroll = max(0, min(max_scroll, self._scroll + amount))
        return True

    def _take_to_bag(self, player, index: int) -> None:
        inv = player.inventory
        item = inv.storage_take(index)
        if item is None:
            return
        if not inv.add(item):
            inv.storage.insert(index, item)
            self.svc.flash("背包已满")

    def _store_to_storage(self, player, index: int) -> None:
        inv = player.inventory
        entries = self._bag_entries(player)
        if index >= len(entries):
            return
        src, _item = entries[index]
        if src[0] == "equip":
            got = inv.pop_equip(src[1])
            if got is None:
                return
            if not inv.storage_add(got):
                inv.equips.insert(src[1], got)
                self.svc.flash("仓库已满")
        else:
            got = inv.take_stack(src[1])
            if got is None:
                return
            if not inv.storage_add(got):
                inv.add(got)
                self.svc.flash("仓库已满")

    # ── 绘制 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (vw - PANEL_W) // 2, (vh - PANEL_H) // 2 - 10

    def draw(self, surface) -> None:
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        self.storage_rects.clear()
        self.bag_rects.clear()
        x, y = self.place(surface, (PANEL_W, PANEL_H))
        if not draw_menu_bg(surface, self.svc, self.rect):
            pygame.draw.rect(surface, (18, 22, 30, 216), self.rect, border_radius=8)
            pygame.draw.rect(surface, (90, 96, 110), self.rect, 1, border_radius=8)

        surface.blit(f.render("仓库", True, (255, 216, 96)), (x + 14, y + 5))
        self.close_rect = pygame.Rect(x + PANEL_W - 40, y + 4, 32, 18)
        surface.blit(fs.render("×", True, (235, 235, 240)), self.close_rect.topleft)

        # 仓库格（左栏）
        grid_x = x + 14
        grid_y = y + TITLE_H + 18
        surface.blit(fs.render("仓库 (点击取出)", True, (230, 230, 235)),
                     (x + 14, y + TITLE_H + 2))
        inv = self.svc.player().inventory
        for idx in range(settings.STORAGE_CAP):
            col, row = idx % STORAGE_COLS, idx // STORAGE_COLS
            rect = pygame.Rect(grid_x + col * CELL, grid_y + row * CELL,
                               CELL - 2, CELL - 2)
            pygame.draw.rect(surface, (36, 42, 54), rect, border_radius=3)
            if idx < len(inv.storage):
                item = inv.storage[idx]
                icon = self._icon(item.id)
                if icon is not None:
                    icon = (icon if icon.get_width() <= 26
                            else pygame.transform.scale(icon, (24, 24)))
                    surface.blit(icon, (rect.x + (rect.w - icon.get_width()) // 2,
                                        rect.y + (rect.h - icon.get_height()) // 2))
                if item.count > 1:
                    cnt = fs.render(str(item.count), True, (255, 255, 255))
                    surface.blit(cnt, (rect.right - cnt.get_width() - 1,
                                       rect.bottom - cnt.get_height() - 1))
            self.storage_rects.append((rect, idx))

        # 背包（右栏，可滚动）
        bag_x = x + 14 + STORAGE_COLS * CELL + 16
        entries = self._bag_entries(self.svc.player())
        surface.blit(fs.render("背包 (点击存入)", True, (230, 230, 235)),
                     (bag_x, y + TITLE_H + 2))
        rows = self._vis_rows()
        for j in range(rows):
            i = self._scroll + j
            if i >= len(entries):
                break
            _src, item = entries[i]
            ry = grid_y + 16 + j * ROW_H
            rect = pygame.Rect(bag_x, ry,
                               PANEL_W - 28 - STORAGE_COLS * CELL - 16, ROW_H - 4)
            pygame.draw.rect(surface, (36, 42, 54), rect, border_radius=4)
            icon = self._icon(item.id)
            if icon is not None:
                surface.blit(icon, (rect.x + 3, rect.y + 2))
            count = f" ×{item.count}" if item.count > 1 else ""
            surface.blit(fs.render(ellipsize(item.name + count, fs, rect.w - 40),
                                   True, (230, 230, 235)), (rect.x + 30, rect.y + 5))
            self.bag_rects.append((rect, i))

        # 底部提示
        surface.blit(fs.render(f"仓库 {len(inv.storage)}/{settings.STORAGE_CAP}",
                               True, (210, 215, 225)),
                     (x + 14, self.rect.bottom - 24))
