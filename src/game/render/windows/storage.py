"""仓库窗口组件：背包 ↔ 仓库双向存取（自旧 storage_panel 迁移）。

左侧 6×8=48 格仓库（STORAGE_CAP），右侧背包列表；点仓库格取出到背包，
点背包物品存入仓库，复用 Inventory.storage_add / storage_take。
toast 归 WindowManager 全局；Esc / 切图 / × 关闭。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game import settings
from game.core.item_tip import build_item_tip, tip_with_note
from game.render.windows.inventory import _asset_desc, _item_tip
from game.render.windows.core import widgets
from game.render.windows.core.dialogs import Modal
from game.render.windows.core.transfer import take_from_source
from game.render.windows.core.widgets import draw_menu_bg, ellipsize, scroll_icon
from game.render.windows.core.window import DragPickup, Window
from game.systems.inventory import Item, item_kind
from game.systems.scrolls import is_scroll_id

# ── 官方仓库窗（UIWindow/Trunk）几何：463×318，左右两栏列表式 ────────
# 左栏 = 仓库、右栏 = 背包；逐行 = 行首图标格 + 名称 + 数量，行高 35 的
# Trunk/select 作悬停高亮。素材缺失回退旧自绘面板（PANEL_FB_*）。
TRUNK_BG = "Trunk/backgrnd"
TRUNK_SELECT = "Trunk/select"
PANEL_W, PANEL_H = 463, 318
LIST_X = (9, 238)          # 左右栏内容左缘（相对窗口）
LIST_W = 208               # 每栏行宽
ROW_TOP = 84               # 首行顶（相对窗口）
ROW_PITCH = 39
ROW_H = 35
VISIBLE_ROWS = 5
SLOT_CX = 20               # 行首图标格中心（相对栏左缘）
NAME_X = 40                # 名称文字左缘（相对栏左缘）

# ── 旧自绘回退面板（素材缺失时用）──────────────────────────────────
PANEL_FB_W, PANEL_FB_H = 600, 330
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
        self._scroll_storage = 0
        self._fallback = False

    # ── 开关 ───────────────────────────────────────────────────────
    def open(self) -> None:
        super().open()          # 基类 open：可见 + 置顶
        self._scroll = 0

    # ── 数据 ───────────────────────────────────────────────────────
    def _bag_entries(self, player) -> List[Tuple[Tuple, "Item"]]:
        inv = player.inventory
        entries = [(("stack", it.id), it) for it in inv.consumes.values()]
        entries += [(("stack", it.id), it) for it in inv.etcs.values()]
        entries += [(("equip", i), it) for i, it in enumerate(inv.equips)]
        return entries

    def _vis_rows(self) -> int:
        return max(1, (PANEL_FB_H - TITLE_H - 20 - 56) // ROW_H)

    def _icon(self, item_id: str) -> Optional[pygame.Surface]:
        if is_scroll_id(item_id):    # 234 段自制卷轴：统一用自绘图标
            return scroll_icon()
        if item_kind(item_id) == "equip":
            return self.svc.assets.equip_icon(item_id)
        return self.svc.assets.item_icon(item_id)

    def _tip_payload(self, item: Item):
        """仓库 / 背包行悬停内容：装备结构化、其余纯文本（盲认图标有据可依）。"""
        desc = _asset_desc(self.svc, item.id)
        if item.kind == "equip":
            player = self.svc.player()
            tip = build_item_tip(item, player.level, player.total_stats(),
                                 player.job, desc=desc)
            return tip_with_note(tip, f"共 {item.count} 件 · 点击取出")
        return _item_tip(item, desc) + (f"\n数量 {item.count} · 点击取出"
                                        if item in self._storage_items()
                                        else "")

    def _storage_items(self) -> List[Item]:
        return self.svc.player().inventory.storage

    # ── 交互 ───────────────────────────────────────────────────────
    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        player = self.svc.player()
        for rect, idx in self.storage_rects:
            if rect.collidepoint(pos):
                self._take_to_bag(player, idx)
                return True
        for rect, idx in self.bag_rects:
            if rect.collidepoint(pos):
                self._ask_store_by_index(idx)
                return True
        return True

    def handle_drop(self, pk: DragPickup, pos) -> bool:
        """物品拖进仓库窗 = 存入（堆叠先问数量）。"""
        if pk.kind != "item" or not self.rect.collidepoint(pos):
            return False
        item = pk.item
        if item is None:
            return True
        if getattr(item, "kind", "") in ("consume", "etc") and item.count > 1:
            def store_qty(qty):
                self._store_dropped(pk, qty)
            self.svc.modal(Modal(
                title=f"存入「{item.name}」", numeric=True,
                max_value=item.count,
                hint=f"拥有 {item.count} 个，存入多少？",
                ok_label="存入", on_ok=store_qty))
            return True
        self._store_dropped(pk, None)
        return True

    def _store_dropped(self, pk: DragPickup, qty) -> None:
        player = self.svc.player()
        inv = player.inventory
        got = take_from_source(player, pk, qty)
        if got is None:
            self.svc.flash("该物品已不在背包，存入取消")
            return
        if not inv.storage_add(got):
            inv.add(got) if got.kind != "equip" else inv.equips.append(got)
            self.svc.flash("仓库已满")
        else:
            if got.kind == "equip":
                player.refresh_equips()
            self.svc.flash(f"存入 {got.name} ×{got.count}" if got.count > 1
                           else f"存入 {got.name}")

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        """官方列表式：光标在哪一栏就滚哪一栏；回退面板只滚背包栏。"""
        player = self.svc.player()
        if not self._fallback and pos[0] < self.rect.centerx:
            rows = VISIBLE_ROWS
            max_scroll = max(0, len(player.inventory.storage) - rows)
            self._scroll_storage = max(0, min(max_scroll,
                                              self._scroll_storage + amount))
            return True
        entries = self._bag_entries(player)
        rows = VISIBLE_ROWS if not self._fallback else self._vis_rows()
        max_scroll = max(0, len(entries) - rows)
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

    def _ask_store_by_index(self, index: int) -> None:
        """点背包行存入：可堆叠 >1 时先问数量（可拆存），其余整件/整堆直存。"""
        player = self.svc.player()
        entries = self._bag_entries(player)
        if index >= len(entries):
            return
        src, item = entries[index]
        if src[0] != "equip" and item.count > 1:
            def store_qty(qty):
                self._store_by_index(index, qty)
            self.svc.modal(Modal(
                title=f"存入「{item.name}」", numeric=True,
                max_value=item.count,
                hint=f"拥有 {item.count} 个，存入多少？",
                ok_label="存入", on_ok=store_qty))
            return
        self._store_by_index(index, None)

    def _store_by_index(self, index: int, qty) -> None:
        inv = self.svc.player().inventory
        entries = self._bag_entries(self.svc.player())
        if index >= len(entries):
            self.svc.flash("该物品已不在背包，存入取消")
            return
        src, item = entries[index]
        got = (inv.take_units(src[1], qty if qty is not None else item.count)
               if src[0] != "equip" else inv.pop_equip(src[1]))
        if got is None:
            return
        if not inv.storage_add(got):
            inv.add(got)
            self.svc.flash("仓库已满")
        else:
            self.svc.flash(f"存入 {got.name} ×{got.count}" if got.count > 1
                           else f"存入 {got.name}")

    # ── 绘制 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        w, h = ((PANEL_FB_W, PANEL_FB_H) if self._fallback
                else (PANEL_W, PANEL_H))
        return (vw - w) // 2, (vh - h) // 2 - 10

    def draw(self, surface) -> None:
        """优先用官方 Trunk 底图；素材缺失回退旧自绘面板。"""
        self.storage_rects.clear()
        self.bag_rects.clear()
        bg = widgets.wz_surface(self.svc, TRUNK_BG)
        self._fallback = bg is None
        if self._fallback:
            x, y = self.place(surface, (PANEL_FB_W, PANEL_FB_H))
            self._draw_fallback(surface, x, y)
            return
        x, y = self.place(surface, (PANEL_W, PANEL_H))
        surface.blit(bg, (x, y))
        self.add_chrome(surface, x, y, PANEL_W, 20)
        mouse = self.svc.mouse()
        inv = self.svc.player().inventory
        self._draw_list(surface, x, y, 0, list(inv.storage), self._scroll_storage,
                        self.storage_rects, inv=inv)
        entries = [it for _src, it in self._bag_entries(self.svc.player())]
        self._draw_list(surface, x, y, 1, entries, self._scroll,
                        self.bag_rects, inv=None)

    def _draw_list(self, surface, x: int, y: int, col: int, items: List[Item],
                   scroll: int, rects: List[Tuple[pygame.Rect, int]],
                   inv) -> None:
        """画一栏官方列表行：悬停高亮 + 图标 + 名称 + 数量。"""
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        mouse = self.svc.mouse()
        lx = x + LIST_X[col]
        sel = widgets.wz_surface(self.svc, TRUNK_SELECT)
        for j in range(VISIBLE_ROWS):
            idx = scroll + j
            rect = pygame.Rect(lx, y + ROW_TOP + j * ROW_PITCH, LIST_W, ROW_H)
            if idx >= len(items):
                if col == 1:
                    break
                rects.append((rect, idx))
                continue
            item = items[idx]
            if rect.collidepoint(mouse) and sel is not None:
                surface.blit(pygame.transform.scale(sel, (LIST_W, ROW_H)),
                             rect.topleft)
            elif rect.collidepoint(mouse):
                pygame.draw.rect(surface, (120, 150, 190), rect, 1)
            slot = pygame.Rect(lx + SLOT_CX - 13, rect.y + 3, 26, 26)
            icon = self._icon(item.id)
            if icon is not None:
                if icon.get_width() > 24 or icon.get_height() > 24:
                    icon = pygame.transform.scale(
                        icon, (min(24, icon.get_width()),
                               min(24, icon.get_height())))
                surface.blit(icon, (slot.centerx - icon.get_width() // 2,
                                    slot.centery - icon.get_height() // 2))
            name_c = (46, 38, 32)
            txt = ellipsize(item.name, fs, LIST_W - NAME_X - 30)
            surface.blit(fs.render(txt, True, name_c),
                         (lx + NAME_X, rect.centery - fs.get_height() // 2))
            if item.count > 1:
                cnt = fs.render(f"×{item.count}", True, (60, 60, 70))
                surface.blit(cnt, (lx + LIST_W - cnt.get_width() - 2,
                                   rect.centery - cnt.get_height() // 2))
            if rect.collidepoint(mouse):
                self.svc.tooltip(self._tip_payload(item))
            rects.append((rect, idx))
        # 栏头计数（贴官方空头区，避开底部金币栏）
        total = len(items)
        label = (f"仓库 {total}/{settings.STORAGE_CAP}" if col == 0
                 else f"背包 {total}")
        surface.blit(f.render(label, True, (70, 66, 58)),
                     (lx + 6, y + 22))

    def _draw_fallback(self, surface, x: int, y: int) -> None:
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        w, h = PANEL_FB_W, PANEL_FB_H
        if not draw_menu_bg(surface, self.svc, pygame.Rect(x, y, w, h)):
            pygame.draw.rect(surface, (18, 22, 30, 216), (x, y, w, h), border_radius=8)
            pygame.draw.rect(surface, (90, 96, 110), (x, y, w, h), 1, border_radius=8)

        surface.blit(f.render("仓库", True, (255, 216, 96)), (x + 14, y + 5))
        self.close_rect = pygame.Rect(x + w - 40, y + 4, 32, 18)
        surface.blit(fs.render("×", True, (235, 235, 240)), self.close_rect.topleft)
        self.title_rect = pygame.Rect(x, y, w - 46, TITLE_H)
        mouse = self.svc.mouse()

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
                if rect.collidepoint(mouse):
                    self.svc.tooltip(self._tip_payload(item))
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
                               self.rect.width - 28 - STORAGE_COLS * CELL - 16,
                               ROW_H - 4)
            pygame.draw.rect(surface, (36, 42, 54), rect, border_radius=4)
            icon = self._icon(item.id)
            if icon is not None:
                surface.blit(icon, (rect.x + 3, rect.y + 2))
            count = f" ×{item.count}" if item.count > 1 else ""
            surface.blit(fs.render(ellipsize(item.name + count, fs, rect.w - 40),
                                   True, (230, 230, 235)), (rect.x + 30, rect.y + 5))
            if rect.collidepoint(mouse):
                self.svc.tooltip(self._tip_payload(item))
            self.bag_rects.append((rect, i))

        # 底部提示
        surface.blit(fs.render(f"仓库 {len(inv.storage)}/{settings.STORAGE_CAP}",
                               True, (210, 215, 225)),
                     (x + 14, self.rect.bottom - 24))
