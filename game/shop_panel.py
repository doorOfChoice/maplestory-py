"""NPC 商店面板：左货架右背包，买/卖按钮 + 价格显示（官方素材风格）。

交互：点货架物品选中（高亮），点「购买」买入一件；点背包物品选中，点
「出售」把整堆/整件卖出（消耗品/其他按 SELL_RATE×数量，装备按单件）。
自制卷轴（234xxxxx 段）无 WZ 图标，用自绘卷轴贴图兜底。点右上角 × 或
按 Esc 关闭；背包列表超长可用滚轮滚动。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from . import shop as shop_mod
from .inventory import item_kind, make_item
from .panels import _ellipsize, draw_menu_bg
from .scrolls import SCROLLS, is_scroll_id

PANEL_W, PANEL_H = 620, 340
TITLE_H = 26
TAB_H = 22
ROW_H = 30
SHELF_W = 286
COL_GAP = 14
BOTTOM_H = 54
BTN_W, BTN_H = 60, 26


class ShopPanel:
    """买卖面板：货架 / 背包两栏 + 购买 / 出售按钮。"""

    def __init__(self, ui, assets):
        self.ui = ui
        self.assets = assets
        self.visible = False
        self.shop_ids: List[str] = []
        self.tab = 0
        self.sel_shelf: Optional[int] = None
        self.sel_bag: Optional[int] = None
        self._scroll = 0
        self.rect = pygame.Rect(0, 0, PANEL_W, PANEL_H)
        self._close_rect = pygame.Rect(0, 0, 0, 0)
        self._tab_rects: List[Tuple[pygame.Rect, str]] = []
        self._shelf_rects: List[Tuple[pygame.Rect, int]] = []
        self._bag_rects: List[Tuple[pygame.Rect, int]] = []
        self._buy_rect = pygame.Rect(0, 0, 0, 0)
        self._sell_rect = pygame.Rect(0, 0, 0, 0)
        self._scroll_icon: Optional[pygame.Surface] = None
        self._toast: Optional[Tuple[str, float]] = None

    # ── 开关 ───────────────────────────────────────────────────────
    def open(self, npc_id: str) -> None:
        self.shop_ids = shop_mod.shops_of(npc_id)
        if not self.shop_ids:
            return
        self.visible = True
        self.tab = 0
        self.sel_shelf = None
        self.sel_bag = None
        self._scroll = 0

    def close(self) -> None:
        self.visible = False

    def flash(self, text: str, duration: float = 1.4) -> None:
        self._toast = (text, duration)

    # ── 数据 ───────────────────────────────────────────────────────
    def _shop_id(self) -> str:
        return self.shop_ids[self.tab % len(self.shop_ids)]

    def _shelf_items(self) -> List[str]:
        return list(shop_mod.SHOPS.get(self._shop_id(), []))

    def _bag_entries(self, player) -> List[Tuple[Tuple, Item]]:
        inv = player.inventory
        entries = [(("stack", it.id), it) for it in inv.consumes.values()]
        entries += [(("stack", it.id), it) for it in inv.etcs.values()]
        entries += [(("equip", i), it) for i, it in enumerate(inv.equips)]
        return entries

    def _vis_rows(self) -> int:
        return max(1, (PANEL_H - TITLE_H - TAB_H - 22 - BOTTOM_H) // ROW_H)

    def _item_name(self, item_id: str) -> str:
        if is_scroll_id(item_id):
            sc = SCROLLS.get(item_id)
            if sc:
                return sc["name"]
        return self.assets.item_name(item_id) or f"物品 {item_id}"

    def _icon(self, item_id: str) -> Optional[pygame.Surface]:
        if is_scroll_id(item_id):
            return self._scroll_surf()
        if item_kind(item_id) == "equip":
            return self.assets.equip_icon(item_id)
        return self.assets.item_icon(item_id)

    def _scroll_surf(self) -> pygame.Surface:
        if self._scroll_icon is None:
            surf = pygame.Surface((26, 26), pygame.SRCALPHA)
            pygame.draw.rect(surf, (216, 198, 156), (3, 3, 20, 20), border_radius=2)
            for dx in (7, 12, 17):
                pygame.draw.line(surf, (120, 90, 40), (dx, 5), (dx, 21), 1)
            self._scroll_icon = surf
        return self._scroll_icon

    # ── 交互 ───────────────────────────────────────────────────────
    def handle_click(self, pos: Tuple[int, int], player, combat) -> bool:
        if not self.visible:
            return False
        if self._close_rect.collidepoint(pos):
            self.close()
            return True
        for rect, shop_id in self._tab_rects:
            if rect.collidepoint(pos):
                self.tab = self.shop_ids.index(shop_id)
                self.sel_shelf = None
                return True
        for rect, idx in self._shelf_rects:
            if rect.collidepoint(pos):
                self.sel_shelf, self.sel_bag = idx, None
                return True
        for rect, idx in self._bag_rects:
            if rect.collidepoint(pos):
                self.sel_bag, self.sel_shelf = idx, None
                return True
        if self._buy_rect.collidepoint(pos):
            self._do_buy(player, combat)
            return True
        if self._sell_rect.collidepoint(pos):
            self._do_sell(player, combat)
            return True
        return bool(self.rect.collidepoint(pos))

    def handle_wheel(self, pos: Tuple[int, int], amount: int, player) -> bool:
        if not self.visible or not self.rect.collidepoint(pos):
            return False
        entries = self._bag_entries(player)
        max_scroll = max(0, len(entries) - self._vis_rows())
        self._scroll = max(0, min(max_scroll, self._scroll + amount))
        return True

    def _do_buy(self, player, combat) -> None:
        if self.sel_shelf is None:
            self.flash("请先点选要购买的物品")
            return
        items = self._shelf_items()
        if self.sel_shelf >= len(items):
            return
        item_id = items[self.sel_shelf]
        price = shop_mod.item_price(item_id, self.assets) or 0

        def make_fn(iid: str, count: int) -> Item:
            name = SCROLLS.get(iid, {}).get("name") if is_scroll_id(iid) else None
            return make_item(iid, self.assets, count, name=name)

        ok, meso = shop_mod.buy(self._shop_id(), item_id, combat.meso,
                                player.inventory, price=price, make_fn=make_fn)
        if ok:
            combat.meso = meso
            self.flash(f"购入 {self._item_name(item_id)}")
        else:
            self.flash("金币不足或背包已满")

    def _do_sell(self, player, combat) -> None:
        if self.sel_bag is None:
            self.flash("请先点选要出售的物品")
            return
        entries = self._bag_entries(player)
        if self.sel_bag >= len(entries):
            return
        src, item = entries[self.sel_bag]
        inv = player.inventory
        if src[0] == "equip":
            got = inv.pop_equip(src[1])
        else:
            got = inv.take_stack(src[1])
        if got is None:
            return
        price = shop_mod.item_price(got.id, self.assets) or 0
        gain = shop_mod.sell_price(price) * max(1, got.count)
        combat.meso = shop_mod.sell(got, combat.meso, price)
        self.sel_bag = None
        self.flash(f"卖出 {got.name} 获得 {gain} 金币")

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface, player, combat) -> None:
        if not self.visible:
            return
        f, fs = self.ui.font, self.ui.font_small
        self._tab_rects.clear()
        self._shelf_rects.clear()
        self._bag_rects.clear()
        vw, vh = surface.get_width(), surface.get_height()
        x = (vw - PANEL_W) // 2
        y = (vh - PANEL_H) // 2 - 10
        self.rect = pygame.Rect(x, y, PANEL_W, PANEL_H)
        if not draw_menu_bg(surface, self.assets, self.rect):
            pygame.draw.rect(surface, (18, 22, 30, 216), self.rect, border_radius=8)
            pygame.draw.rect(surface, (90, 96, 110), self.rect, 1, border_radius=8)

        # 标题 + 关闭
        surface.blit(f.render("商店", True, (255, 216, 96)), (x + 14, y + 5))
        self._close_rect = pygame.Rect(x + PANEL_W - 40, y + 4, 32, 18)
        surface.blit(fs.render("×", True, (235, 235, 240)), self._close_rect.topleft)

        # 页签
        tx = x + 14
        for shop_id in self.shop_ids:
            label = shop_mod.SHOP_NAMES.get(shop_id, shop_id)
            tr = pygame.Rect(tx, y + TITLE_H + 2, max(46, fs.size(label)[0] + 14), 18)
            on = shop_id == self._shop_id()
            pygame.draw.rect(surface, (60, 70, 88) if on else (34, 40, 52), tr,
                             border_radius=4)
            surface.blit(fs.render(label, True, (255, 255, 255)), (tr.x + 7, tr.y + 2))
            self._tab_rects.append((tr, shop_id))
            tx += tr.w + 6

        # 货架（左栏）
        shelf_x = x + 14
        shelf_y = y + TITLE_H + TAB_H + 4
        items = self._shelf_items()
        for i, item_id in enumerate(items):
            ry = shelf_y + i * ROW_H
            rect = pygame.Rect(shelf_x, ry, SHELF_W, ROW_H - 4)
            pygame.draw.rect(surface, (60, 78, 96) if i == self.sel_shelf
                             else (36, 42, 54), rect, border_radius=4)
            icon = self._icon(item_id)
            if icon is not None:
                surface.blit(icon, (rect.x + 3, rect.y + 2))
            surface.blit(fs.render(_ellipsize(self._item_name(item_id), fs, rect.w - 108),
                                   True, (230, 230, 235)), (rect.x + 32, rect.y + 5))
            price = shop_mod.item_price(item_id, self.assets) or 0
            surface.blit(fs.render(f"{price:,}", True, (255, 216, 96)),
                         (rect.right - 46, rect.y + 5))
            surface.blit(fs.render("金币", True, (210, 210, 215)),
                         (rect.right - 46, rect.y + 17))
            self._shelf_rects.append((rect, i))

        # 背包（右栏，可滚动）
        bag_x = x + 14 + SHELF_W + COL_GAP
        entries = self._bag_entries(player)
        surface.blit(fs.render("我的背包", True, (230, 230, 235)),
                     (bag_x, shelf_y - 2))
        rows = self._vis_rows()
        for j in range(rows):
            i = self._scroll + j
            if i >= len(entries):
                break
            _src, item = entries[i]
            ry = shelf_y + 18 + j * ROW_H
            rect = pygame.Rect(bag_x, ry, PANEL_W - 28 - SHELF_W - COL_GAP, ROW_H - 4)
            pygame.draw.rect(surface, (60, 78, 96) if i == self.sel_bag
                             else (36, 42, 54), rect, border_radius=4)
            icon = self._icon(item.id)
            if icon is not None:
                surface.blit(icon, (rect.x + 3, rect.y + 2))
            count = f" ×{item.count}" if item.count > 1 else ""
            surface.blit(fs.render(_ellipsize(item.name + count, fs, rect.w - 96),
                                   True, (230, 230, 235)), (rect.x + 32, rect.y + 5))
            price = shop_mod.item_price(item.id, self.assets) or 0
            gain = shop_mod.sell_price(price) * max(1, item.count)
            surface.blit(fs.render(str(gain), True, (140, 200, 160)),
                         (rect.right - 40, rect.y + 5))
            self._bag_rects.append((rect, i))

        # 底部：金币 + 选中价格 + 按钮
        by = self.rect.bottom - BOTTOM_H
        pygame.draw.line(surface, (70, 76, 90), (x + 12, by), (x + PANEL_W - 12, by))
        surface.blit(fs.render(f"金币 {combat.meso:,}", True, (255, 216, 96)),
                     (x + 14, by + 14))
        sel_desc = ""
        if self.sel_shelf is not None and self.sel_shelf < len(items):
            price = shop_mod.item_price(items[self.sel_shelf], self.assets) or 0
            sel_desc = f"选中 {self._item_name(items[self.sel_shelf])} · 买价 {price}"
        elif self.sel_bag is not None and self.sel_bag < len(entries):
            _src, item = entries[self.sel_bag]
            sel_desc = f"选中 {item.name} · 单件卖价 {shop_mod.sell_price(shop_mod.item_price(item.id, self.assets) or 0)}"
        if sel_desc:
            surface.blit(fs.render(_ellipsize(sel_desc, fs, 260), True, (210, 215, 225)),
                         (x + 160, by + 14))

        self._buy_rect = pygame.Rect(x + PANEL_W - 14 - BTN_W, by + 14, BTN_W, BTN_H)
        self._sell_rect = pygame.Rect(self._buy_rect.x - BTN_W - 8, by + 14, BTN_W, BTN_H)
        close_btn = pygame.Rect(self._sell_rect.x - 50, by + 14, 42, BTN_H)
        for rect, label, color in ((self._buy_rect, "购买", (52, 110, 78)),
                                   (self._sell_rect, "出售", (110, 84, 52)),
                                   (close_btn, "关闭", (74, 78, 92))):
            pygame.draw.rect(surface, color, rect, border_radius=4)
            surface.blit(fs.render(label, True, (240, 240, 245)),
                         (rect.x + (rect.w - fs.size(label)[0]) // 2, rect.y + 5))

        # 提示
        if self._toast is not None:
            text, remain = self._toast
            remain -= 1 / 60
            if remain <= 0:
                self._toast = None
            else:
                self._toast = (text, remain)
                self._draw_toast(surface, text)

    def _draw_toast(self, surface, text: str) -> None:
        fs = self.ui.font_small
        txt = fs.render(text, True, (255, 230, 150))
        w, h = txt.get_width() + 18, 22
        x = (surface.get_width() - w) // 2
        plate = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(plate, (20, 16, 10, 210), (0, 0, w, h), border_radius=6)
        pygame.draw.rect(plate, (150, 130, 90), (0, 0, w, h), 1, border_radius=6)
        plate.blit(txt, (9, (h - txt.get_height()) // 2))
        surface.blit(plate, (x, 34))
