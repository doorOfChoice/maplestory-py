"""商店窗口组件：左货架右背包 + 买/卖/离开按钮 + 数量输入弹框（自旧 shop_panel 迁移）。

底板优先 UIWindow.img/Shop/backgrnd（463×339 两栏），缺失走深色 fallback。
交互（同原版）：行点击选中（原版 select 高亮）；对可堆叠物品点「购买 /
出售」（背包行选中后按 Delete 亦等同「出售」）或**双击该行**弹出白底
数量输入框（卖出预填拥有量、数字键录入、Enter/确认成交、Esc/取消放弃），
买入按输入数量整单结算，卖出从整堆里拆卖 N 个
（超存量按全堆封顶）；装备不弹框按 1 件成交；双栏各自滚动条（拇指可拖）、
页签切换重置滚动。
toast 归 WindowManager 全局；关闭钮/热区走基类公开 rect。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.render.conv import ui_image
from game.render.windows.core.widgets import ellipsize, draw_menu_bg
from game.render.windows.core.window import DOUBLE_CLICK_TIME, Window
from game.systems import shop as shop_mod
from game.systems.inventory import Item, item_kind, make_item
from game.systems.scrolls import SCROLLS, is_scroll_id

# ── 原版 Shop/backgrnd 几何（由 UI.wz 底图逐像素实测）────────────────
BG_PANEL_W, BG_PANEL_H = 463, 339
BG_ROW_Y0 = 124
BG_ROW_H = 40
BG_NROWS = 5
BG_LCOL_X, BG_LCOL_W = 32, 196
BG_RCOL_X, BG_RCOL_W = 260, 198
BG_LCOL_SLOT_CX = 24
BG_LCOL_NAME_X = 45
BG_RCOL_SLOT_CX = 253
BG_RCOL_NAME_X = 273
BG_MESO_X, BG_MESO_Y = 365, 65
BTN_W, BTN_H = 70, 19
BG_BTN_Y = 88

# ── 滚动条几何（两栏各自独立，叠在行区右缘）────────────────────────
SCROLLBAR_W = 9
SCROLLBAR_MIN_THUMB = 18

# ── 数量输入弹框（原版白底输入框）──────────────────────────────────
QTY_MAX_DIGITS = 4             # 最多录入 9999

# ── 旧式深色回退面板几何（素材缺失时用）────────────────────────────
PANEL_W, PANEL_H = 620, 340
TITLE_H = 26
TAB_H = 22
ROW_H = 30
SHELF_W = 286
COL_GAP = 14
BOTTOM_H = 54
BTN_W_FB, BTN_H_FB = 60, 26


class ShopWindow(Window):
    """买卖面板：货架 / 背包两栏 + 购买 / 出售按钮。"""

    key = "shop"
    escape_closes = True
    closes_on_map_change = True

    def __init__(self, svc) -> None:
        super().__init__(svc)
        self.shop_ids: List[str] = []
        self.tab = 0
        self.sel_shelf: Optional[int] = None
        self.sel_bag: Optional[int] = None
        self._scroll = 0
        self._scroll_shelf = 0
        self.tab_rects: List[Tuple[pygame.Rect, str]] = []
        self.shelf_rects: List[Tuple[pygame.Rect, int]] = []
        self.bag_rects: List[Tuple[pygame.Rect, int]] = []
        self.buy_rect = pygame.Rect(0, 0, 0, 0)
        self.sell_rect = pygame.Rect(0, 0, 0, 0)
        # 数量输入弹框：None / "buy" / "sell"
        self.qty_mode: Optional[str] = None
        self.qty_text: str = ""
        self._qty_prefilled: bool = False
        self.qty_box_rect = pygame.Rect(0, 0, 0, 0)
        self.qty_ok_rect = pygame.Rect(0, 0, 0, 0)
        self.qty_cancel_rect = pygame.Rect(0, 0, 0, 0)
        # 双击快捷入口：(栏别, 行号, 时刻)
        self._last_row_click: Optional[Tuple[str, int, float]] = None
        self._shelf_bar = pygame.Rect(0, 0, 0, 0)
        self._bag_bar = pygame.Rect(0, 0, 0, 0)
        self._shelf_bar_thumb = pygame.Rect(0, 0, 0, 0)
        self._bag_bar_thumb = pygame.Rect(0, 0, 0, 0)
        self._drag_bar: Optional[str] = None
        self._scroll_icon: Optional[pygame.Surface] = None
        self._exit_rect = pygame.Rect(0, 0, 0, 0)   # fallback 底部关闭钮

    # ── 素材取值 ───────────────────────────────────────────────────
    def _wz(self, path: str) -> Optional[pygame.Surface]:
        """Shop/<path> → Surface：转发 render.conv.ui_image 单源（assets 层已缓存）。"""
        return ui_image(self.svc.assets, "UIWindow.img", "Shop/" + path)

    # ── 开关 ───────────────────────────────────────────────────────
    def open(self, npc_id: str) -> None:      # type: ignore[override]
        self.shop_ids = shop_mod.shops_of(npc_id)
        if not self.shop_ids:
            return
        self.visible = True
        self.tab = 0
        self.sel_shelf = None
        self.sel_bag = None
        self._scroll = 0
        self._scroll_shelf = 0
        self._qty_cancel()
        self._last_row_click = None

    def on_close(self) -> None:
        self._drag_bar = None
        self._qty_cancel()
        self._last_row_click = None

    # ── 数据 ───────────────────────────────────────────────────────
    @property
    def _player(self):
        return self.svc.player()

    @property
    def _combat(self):
        return self.svc.combat

    def _shop_id(self) -> str:
        return self.shop_ids[self.tab % len(self.shop_ids)]

    def _shelf_items(self) -> List[str]:
        return list(shop_mod.SHOPS.get(self._shop_id(), []))

    def _shop_price(self, item_id: str) -> int:
        """该店该物品买价（脚本价 > WZ 价 > 兜底表）。"""
        return shop_mod.buy_price(self._shop_id(), item_id, self.svc.assets) or 0

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
        return self.svc.assets.item_name(item_id) or f"物品 {item_id}"

    def _icon(self, item_id: str) -> Optional[pygame.Surface]:
        if is_scroll_id(item_id):
            return self._scroll_surf()
        if item_kind(item_id) == "equip":
            return self.svc.assets.equip_icon(item_id)
        return self.svc.assets.item_icon(item_id)

    def _scroll_surf(self) -> pygame.Surface:
        if self._scroll_icon is None:
            surf = pygame.Surface((26, 26), pygame.SRCALPHA)
            pygame.draw.rect(surf, (216, 198, 156), (3, 3, 20, 20), border_radius=2)
            for dx in (7, 12, 17):
                pygame.draw.line(surf, (120, 90, 40), (dx, 5), (dx, 21), 1)
            self._scroll_icon = surf
        return self._scroll_icon

    # ── 交互 ───────────────────────────────────────────────────────
    def _rows(self) -> int:
        """当前布局可视行数。"""
        return BG_NROWS if self._wz("backgrnd") is not None else self._vis_rows()

    def _bar_thumb(self, track: pygame.Rect, scroll: int, total: int) -> pygame.Rect:
        """按滚动比例计算拇指矩形；无可滚内容返回空矩形。"""
        if total <= self._rows():
            return pygame.Rect(0, 0, 0, 0)
        span = track.h - SCROLLBAR_MIN_THUMB
        frac = scroll / max(1, total - self._rows())
        h = SCROLLBAR_MIN_THUMB
        if total > 0:
            h = max(SCROLLBAR_MIN_THUMB, int(track.h * self._rows() / total))
        y = track.y + int(frac * max(0, track.h - h))
        return pygame.Rect(track.x, y, track.w, h)

    def _update_bars(self, player) -> None:
        """根据两组列表长度刷新滚轮钳制与拇指矩形。"""
        rows = self._rows()
        n_shelf = len(self._shelf_items())
        self._scroll_shelf = max(0, min(self._scroll_shelf, max(0, n_shelf - rows)))
        self._shelf_bar_thumb = self._bar_thumb(self._shelf_bar, self._scroll_shelf, n_shelf)
        n_bag = len(self._bag_entries(player))
        self._scroll = max(0, min(self._scroll, max(0, n_bag - rows)))
        self._bag_bar_thumb = self._bar_thumb(self._bag_bar, self._scroll, n_bag)

    def _bar_from_pos(self, pos: Tuple[int, int]) -> Tuple[bool, str]:
        """命中滚动条：返回 (命中, 'shelf'|'bag')。"""
        if self._shelf_bar_thumb.collidepoint(pos):
            return True, "shelf"
        if self._bag_bar_thumb.collidepoint(pos):
            return True, "bag"
        return False, ""

    def _jump_bar(self, key: str, pos_y: int, player) -> None:
        """点轨道空白：让拇指中心平移到光标处（跳页）。"""
        track = self._shelf_bar if key == "shelf" else self._bag_bar
        total = (len(self._shelf_items()) if key == "shelf"
                 else len(self._bag_entries(player)))
        rows = self._rows()
        thumb = self._bar_thumb(track, 0, total)
        span = max(1, track.h - thumb.h)
        frac = (pos_y - track.y - thumb.h / 2) / span
        frac = max(0.0, min(1.0, frac))
        scroll = int(frac * max(0, total - rows))
        if key == "shelf":
            self._scroll_shelf = scroll
        else:
            self._scroll = scroll

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        player, combat = self._player, self._combat
        # 数量弹框打开时模态：只认确认/取消，其余点击一律吞掉
        if self.qty_mode is not None:
            if self.qty_ok_rect.collidepoint(pos):
                self._qty_confirm(player, combat)
            elif self.qty_cancel_rect.collidepoint(pos):
                self._qty_cancel()
            return True
        if self._exit_rect.collidepoint(pos):     # fallback 底部「关闭」钮
            self.close()
            return True
        for rect, shop_id in self.tab_rects:
            if rect.collidepoint(pos):
                self.tab = self.shop_ids.index(shop_id)
                self.sel_shelf = None
                self._scroll = self._scroll_shelf = 0
                self._last_row_click = None
                return True
        # 滚动条优先（覆盖行区右缘，避免误选中物品行）
        hit, key = self._bar_from_pos(pos)
        if hit:
            self._drag_bar = key
            return True
        if self._shelf_bar.collidepoint(pos) and self._shelf_bar_thumb.width:
            self._jump_bar("shelf", pos[1], player)
            return True
        if self._bag_bar.collidepoint(pos) and self._bag_bar_thumb.width:
            self._jump_bar("bag", pos[1], player)
            return True
        for rect, idx in self.shelf_rects:
            if rect.collidepoint(pos):
                self.sel_shelf, self.sel_bag = idx, None
                if (self._is_double_click("shelf", idx)
                        and item_kind(self._shelf_items()[idx]) != "equip"):
                    self._open_qty("buy")
                return True
        if self.buy_rect.collidepoint(pos) and combat is not None:
            self._do_buy(player, combat)
            return True
        if self.sell_rect.collidepoint(pos) and combat is not None:
            self._do_sell(player, combat)
            return True
        for rect, idx in self.bag_rects:
            if rect.collidepoint(pos):
                self.sel_bag, self.sel_shelf = idx, None
                if (self._is_double_click("bag", idx)
                        and self._bag_entries(player)[idx][0][0] == "stack"):
                    self._open_qty("sell", self._bag_entries(player)[idx][1].count)
                return True
        return True

    def _is_double_click(self, kind: str, idx: int) -> bool:
        """同一行短间隔再点 = 双击（消费掉本次，避免连点第三次再触发）。"""
        now = pygame.time.get_ticks() / 1000.0
        last = self._last_row_click
        self._last_row_click = (kind, idx, now)
        return (last is not None and last[0] == kind and last[1] == idx
                and now - last[2] <= DOUBLE_CLICK_TIME)

    # ── 数量输入弹框 ───────────────────────────────────────────────
    def handle_keydown(self, key: int) -> bool:
        """弹框打开期间模态吃键：数字录入 / 退格 / Enter 确认 / Esc 取消；
        平时选中背包行按 Delete / Backspace（Mac  delete 即退格）= 点「出售」。"""
        if self.qty_mode is None:
            if (key in (pygame.K_DELETE, pygame.K_BACKSPACE)
                    and self.sel_bag is not None and self._combat is not None):
                self._do_sell(self._player, self._combat)
                return True
            return False
        if pygame.K_0 <= key <= pygame.K_9:
            self._qty_type(str(key - pygame.K_0))
        elif pygame.K_KP0 <= key <= pygame.K_KP9:
            self._qty_type(str(key - pygame.K_KP0))
        elif key == pygame.K_BACKSPACE:
            self._qty_prefilled = False
            self.qty_text = self.qty_text[:-1]
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._qty_confirm(self._player, self._combat)
        elif key == pygame.K_ESCAPE:
            self._qty_cancel()
        return True

    def _open_qty(self, mode: str, default: int = 0) -> None:
        """打开数量框；default>0 时预填（如卖出=拥有量），首个数字键会替换预填值。"""
        self.qty_mode = mode
        self.qty_text = str(min(default, 10 ** QTY_MAX_DIGITS - 1)) if default else ""
        self._qty_prefilled = bool(self.qty_text)

    def _qty_type(self, digit: str) -> None:
        if self._qty_prefilled:        # 预填视作整串选中：打字即替换，改数免退格
            self._qty_prefilled = False
            self.qty_text = ""
        if len(self.qty_text) < QTY_MAX_DIGITS:
            self.qty_text += digit

    def _qty_cancel(self) -> None:
        self.qty_mode = None
        self.qty_text = ""
        self._qty_prefilled = False

    def _qty_confirm(self, player, combat) -> None:
        """确认成交：买入按输入数量整单结算；卖出按存量封顶拆堆。"""
        if combat is None:
            self._qty_cancel()
            return
        try:
            n = int(self.qty_text)
        except ValueError:
            n = 0
        if n < 1:
            self.svc.flash("请输入数量")
            return
        if self.qty_mode == "buy":
            items = self._shelf_items()
            if self.sel_shelf is not None and self.sel_shelf < len(items):
                item_id = items[self.sel_shelf]
                self._buy_n(player, combat, item_id, self._shop_price(item_id), n)
            self._qty_cancel()
            return
        entries = self._bag_entries(player)
        if self.sel_bag is not None and self.sel_bag < len(entries):
            src, item = entries[self.sel_bag]
            got = player.inventory.take_units(src[1], min(n, item.count))
            self._sell_got(combat, got)
        self._qty_cancel()

    def handle_mouse_motion(self, pos: Tuple[int, int]) -> bool:
        """拖动拇指时连续滚动（按下拇指起拖，松开结束）。"""
        if self._drag_bar is None:
            return False
        if self._drag_bar == "shelf":
            track, total = self._shelf_bar, len(self._shelf_items())
        else:
            track = self._bag_bar
            total = len(self._bag_entries(self._player))
        thumb = self._bar_thumb(track, 0, total)
        span = max(1, track.h - thumb.h)
        frac = (pos[1] - track.y - thumb.h / 2) / span
        frac = max(0.0, min(1.0, frac))
        scroll = int(frac * max(0, total - self._rows()))
        if self._drag_bar == "shelf":
            self._scroll_shelf = scroll
        else:
            self._scroll = scroll
        return True

    def handle_mouse_up(self, pos: Tuple[int, int]) -> bool:
        if self._drag_bar is None:
            return False
        self._drag_bar = None
        return True

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        player = self._player
        rows = self._rows()
        # 光标在左半 → 滚货架；右半 → 滚背包
        if pos[0] - self.rect.x < self.rect.w // 2:
            items = self._shelf_items()
            max_scroll = max(0, len(items) - rows)
            self._scroll_shelf = max(0, min(max_scroll, self._scroll_shelf + amount))
        else:
            entries = self._bag_entries(player)
            max_scroll = max(0, len(entries) - rows)
            self._scroll = max(0, min(max_scroll, self._scroll + amount))
        return True

    def _do_buy(self, player, combat) -> None:
        if self.sel_shelf is None:
            self.svc.flash("请先点选要购买的物品")
            return
        items = self._shelf_items()
        if self.sel_shelf >= len(items):
            return
        item_id = items[self.sel_shelf]
        if item_kind(item_id) == "equip":     # 不可堆叠：直接按 1 件成交
            self._buy_n(player, combat, item_id, self._shop_price(item_id), 1)
        else:
            self._open_qty("buy")

    def _buy_n(self, player, combat, item_id: str, price: int, count: int) -> None:
        def make_fn(iid: str, n: int) -> Item:
            name = SCROLLS.get(iid, {}).get("name") if is_scroll_id(iid) else None
            return make_item(iid, self.svc.assets, n, name=name)

        ok, meso = shop_mod.buy(self._shop_id(), item_id, combat.meso,
                                player.inventory, price=price, count=count,
                                make_fn=make_fn)
        if ok:
            combat.meso = meso
            suffix = f" ×{count}" if count > 1 else ""
            self.svc.flash(f"购入 {self._item_name(item_id)}{suffix}")
        else:
            self.svc.flash("金币不足或背包已满")

    def _do_sell(self, player, combat) -> None:
        if self.sel_bag is None:
            self.svc.flash("请先点选要出售的物品")
            return
        entries = self._bag_entries(player)
        if self.sel_bag >= len(entries):
            return
        src, item = entries[self.sel_bag]
        if src[0] == "equip":                 # 散件装备：整件直接卖
            self._sell_got(combat, player.inventory.pop_equip(src[1]))
        else:
            self._open_qty("sell", item.count)   # 预填拥有量，直接确认即全卖

    def _sell_got(self, combat, got: Optional[Item]) -> None:
        if got is None:
            return
        price = shop_mod.buy_price(self._shop_id(), got.id, self.svc.assets) or 0
        gain = shop_mod.sell_price(price) * max(1, got.count)
        combat.meso = shop_mod.sell(got, combat.meso, price)
        self.sel_bag = None
        suffix = f" ×{got.count}" if got.count > 1 else ""
        self.svc.flash(f"卖出 {got.name}{suffix} 获得 {gain} 金币")

    # ── 绘制 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        """官方 / fallback 两布局各自居中偏上，尺寸随底图有无切换。"""
        if self._wz("backgrnd") is not None:
            return (vw - BG_PANEL_W) // 2, (vh - BG_PANEL_H) // 2 - 10
        return (vw - PANEL_W) // 2, (vh - PANEL_H) // 2 - 10

    def draw(self, surface) -> None:
        player, combat = self._player, self._combat
        self.tab_rects.clear()
        self.shelf_rects.clear()
        self.bag_rects.clear()
        bg = self._wz("backgrnd")
        if bg is not None:
            self._draw_official(surface, bg, player, combat)
        else:
            self._draw_fallback(surface, player, combat)
        if self.qty_mode is not None:
            self._draw_qty_dialog(surface, self.svc.ui.font, self.svc.ui.font_small)

    def _row_rect(self, col_x: int, col_w: int, y0: int, pitch: int,
                  index: int) -> pygame.Rect:
        """第 index 行格子的显示矩形（含 2px 内缩避让分隔线）。"""
        return pygame.Rect(col_x, y0 + index * pitch, col_w, pitch - 6)

    def _draw_official(self, surface, bg, player, combat) -> None:
        """原版 Shop/backgrnd 独立两栏商店窗（素材齐全时调用）。"""
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        x, y = self.place(surface, (BG_PANEL_W, BG_PANEL_H))
        surface.blit(bg, (x, y))

        # ── 头区左框：标题 + 商店页签 ─────────────────────────────
        surface.blit(f.render("商店", True, (90, 84, 74)), (x + 18, y + 8))
        tab_y = y + 28
        tab_x = x + 18
        for shop_id in self.shop_ids:
            on = shop_id == self._shop_id()
            label = shop_mod.shop_name(shop_id)
            tr = pygame.Rect(tab_x, tab_y, max(48, fs.size(label)[0] + 12), 18)
            pygame.draw.rect(surface, (252, 200, 60) if on else (222, 214, 196),
                             tr, border_radius=3)
            pygame.draw.rect(surface, (150, 120, 60) if on else (170, 160, 140),
                             tr, 1, border_radius=3)
            surface.blit(fs.render(label, True, (90, 60, 20) if on else (110, 100, 86)),
                         (tr.x + 6, tr.y + 3))
            self.tab_rects.append((tr, shop_id))
            tab_x += tr.w + 5

        surface.blit(fs.render("单击选中 · 双击可堆叠物品直接填数量买卖", True,
                               (130, 118, 100)),
                     (x + 18, y + 54))

        # ── 头区右框：离开商店按钮 + 关闭 ─────────────────────────
        exit_img = self._wz("BtExit/normal/0")
        if exit_img is not None:
            ex = x + BG_PANEL_W - 20 - exit_img.get_width()
            surface.blit(exit_img, (ex, y + 14))
            self.close_rect = pygame.Rect(ex, y + 14, exit_img.get_width(),
                                          exit_img.get_height())
        else:
            self.close_rect = pygame.Rect(x + BG_PANEL_W - 34, y + 10, 20, 18)
            surface.blit(fs.render("×", True, (110, 100, 88)), self.close_rect.topleft)

        # ── 头区右框顶部：金币金额（紧随底图金币图标）───────────────
        meso = combat.meso if combat is not None else 0
        meso_s = self.svc.ui.font_tiny.render(f"{meso:,}", True, (120, 96, 40))
        surface.blit(meso_s, (x + BG_MESO_X, y + BG_MESO_Y))

        # ── 左栏：货架物品（买，可滚动）─────────────────────────────
        items = self._shelf_items()
        self._scroll_shelf = max(0, min(self._scroll_shelf,
                                        max(0, len(items) - BG_NROWS)))
        row_x = x + BG_LCOL_X
        row_w = BG_LCOL_W
        self._shelf_bar = pygame.Rect(row_x + row_w - SCROLLBAR_W - 2,
                                      y + BG_ROW_Y0, SCROLLBAR_W,
                                      BG_NROWS * BG_ROW_H - 6)
        for j in range(BG_NROWS):
            i = self._scroll_shelf + j
            if i >= len(items):
                break
            rect = self._row_rect(row_x, row_w, y + BG_ROW_Y0, BG_ROW_H, j)
            self._draw_buy_row(surface, rect, items[i], fs,
                               i == self.sel_shelf)
            self.shelf_rects.append((rect, i))

        # ── 右栏：背包物品（卖，可滚动）────────────────────────────
        entries = self._bag_entries(player)
        self._scroll = max(0, min(self._scroll, max(0, len(entries) - BG_NROWS)))
        bag_x = x + BG_RCOL_X
        bag_w = BG_RCOL_W
        self._bag_bar = pygame.Rect(bag_x + bag_w - SCROLLBAR_W - 2,
                                    y + BG_ROW_Y0, SCROLLBAR_W,
                                    BG_NROWS * BG_ROW_H - 6)
        for j in range(BG_NROWS):
            i = self._scroll + j
            if i >= len(entries):
                break
            rect = self._row_rect(bag_x, bag_w, y + BG_ROW_Y0, BG_ROW_H, j)
            self._draw_sell_row(surface, rect, entries[i], fs,
                                i == self.sel_bag)
            self.bag_rects.append((rect, i))

        # ── 两栏滚动条（叠在行区右缘，内容左对齐不冲突）──────────────
        self._update_bars(player)
        self._draw_scrollbar(surface, self._shelf_bar, self._shelf_bar_thumb)
        self._draw_scrollbar(surface, self._bag_bar, self._bag_bar_thumb)

        # ── 头区右框：买/卖按钮放在金币金额下方空隙，不叠物品行 ───────
        by = y + BG_BTN_Y
        buy_img = self._wz("BtBuy/normal/0")
        sell_img = self._wz("BtSell/normal/0")
        bx = x + BG_PANEL_W - 18 - (BTN_W * 2 + 8)
        if buy_img is not None and sell_img is not None:
            surface.blit(sell_img, (bx, by))
            surface.blit(buy_img, (bx + BTN_W + 8, by))
        self.buy_rect = pygame.Rect(bx + BTN_W + 8, by, BTN_W, BTN_H)
        self.sell_rect = pygame.Rect(bx, by, BTN_W, BTN_H)
        if buy_img is None or sell_img is None:
            for rect, label, color in ((self.buy_rect, "购买", (52, 110, 78)),
                                       (self.sell_rect, "出售", (110, 84, 52))):
                pygame.draw.rect(surface, color, rect, border_radius=4)
                surface.blit(fs.render(label, True, (240, 240, 245)),
                             (rect.x + (rect.w - fs.size(label)[0]) // 2, rect.y + 4))

    def _draw_scrollbar(self, surface, track: pygame.Rect,
                        thumb: pygame.Rect) -> None:
        """画一条竖向滚动条：无可滚内容时不画淡轨，仅画可拖拇指。"""
        if track.width <= 0 or thumb.width <= 0:
            return
        pygame.draw.rect(surface, (176, 186, 198), track, border_radius=3)
        pygame.draw.rect(surface, (205, 214, 224), thumb, border_radius=3)
        pygame.draw.rect(surface, (120, 132, 148), thumb, 1, border_radius=3)

    def _draw_qty_dialog(self, surface, f, fs) -> None:
        """白底数量输入框：居中模态叠在商店面板上（确认/取消）。"""
        title = "购买数量" if self.qty_mode == "buy" else "出售数量"
        hint = ""
        if self.qty_mode == "buy":
            items = self._shelf_items()
            if self.sel_shelf is not None and self.sel_shelf < len(items):
                item_id = items[self.sel_shelf]
                hint = f"{self._item_name(item_id)} · 单价 {self._shop_price(item_id)}"
        else:
            entries = self._bag_entries(self._player)
            if self.sel_bag is not None and self.sel_bag < len(entries):
                _src, item = entries[self.sel_bag]
                base = shop_mod.buy_price(self._shop_id(), item.id,
                                          self.svc.assets) or 0
                hint = (f"{item.name} · 单件卖价 {shop_mod.sell_price(base)}"
                        f" · 拥有 {item.count}")
        w, h = 250, 112
        x = max(self.rect.x, min(self.rect.right - w, self.rect.centerx - w // 2))
        y = max(self.rect.y, min(self.rect.bottom - h, self.rect.centery - h // 2))
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((24, 28, 38, 242))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (150, 158, 175), (x, y, w, h), 1, border_radius=4)
        surface.blit(f.render(title, True, (255, 216, 96)), (x + 14, y + 8))
        if hint:
            surface.blit(fs.render(ellipsize(hint, fs, w - 28), True,
                                   (205, 210, 220)), (x + 14, y + 30))
        box = pygame.Rect(x + 14, y + 50, w - 140, 24)
        pygame.draw.rect(surface, (252, 252, 250), box, border_radius=3)
        pygame.draw.rect(surface, (110, 118, 134), box, 1, border_radius=3)
        caret = "▌" if int(pygame.time.get_ticks() / 500) % 2 == 0 else ""
        surface.blit(fs.render(self.qty_text + caret, True, (30, 32, 38)),
                     (box.x + 6, box.y + 4))
        self.qty_box_rect = box
        ok = pygame.Rect(x + w - 116, y + 50, 52, 24)
        cancel = pygame.Rect(x + w - 58, y + 50, 52, 24)
        for rect, label, color in ((ok, "确认", (52, 110, 78)),
                                   (cancel, "取消", (84, 70, 66))):
            pygame.draw.rect(surface, color, rect, border_radius=4)
            surface.blit(fs.render(label, True, (240, 240, 245)),
                         (rect.centerx - fs.size(label)[0] // 2, rect.y + 4))
        self.qty_ok_rect, self.qty_cancel_rect = ok, cancel
        surface.blit(fs.render("数字键输入数量 · Enter 确认 · Esc 取消", True,
                               (140, 146, 160)), (x + 14, y + h - 20))

    def _blit_row_content(self, surface, rect: pygame.Rect, icon, fs,
                          name_txt: str, name_c, price_txt, price_c,
                          price_max_w: int) -> None:
        """把图标 + 名称 + 价格垂直居中绘制到 rect：名称紧随图标实际宽度。"""
        if icon is not None:
            surface.blit(icon, (rect.x + 6,
                                rect.centery - icon.get_height() // 2))
        name_s = fs.render(name_txt, True, name_c)
        name_x = rect.x + 6 + (icon.get_width() + 7 if icon is not None else 0)
        surface.blit(name_s, (name_x, rect.centery - name_s.get_height() // 2))
        if price_txt is not None:
            p_s = fs.render(price_txt, True, price_c)
            surface.blit(p_s, (rect.right - 6 - p_s.get_width(),
                               rect.centery - p_s.get_height() // 2))

    @staticmethod
    def _sel_rect(rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(rect.x, rect.y - 3, rect.w, rect.h + 4)

    def _draw_buy_row(self, surface, rect: pygame.Rect, item_id: str, fs,
                      selected: bool) -> None:
        """左栏单行：图标 + 名称 + 买价；选中叠原版 orange select。"""
        if selected:
            sel = self._wz("select")
            if sel is not None:
                fit = pygame.transform.smoothscale(sel, (rect.w, rect.h + 4))
                surface.blit(fit, (rect.x, rect.y - 3))
        icon = self._icon(item_id)
        name_c = (60, 52, 44) if selected else (80, 72, 62)
        icon_x = rect.x - BG_LCOL_X + BG_LCOL_SLOT_CX
        name_x = rect.x - BG_LCOL_X + BG_LCOL_NAME_X
        price_w = 58
        max_w = (rect.right - 6 - price_w) - name_x
        name_txt = ellipsize(self._item_name(item_id), fs, max_w)
        name_s = fs.render(name_txt, True, name_c)
        if icon is not None:
            surface.blit(icon, (icon_x - icon.get_width() // 2,
                                rect.centery - icon.get_height() // 2))
        surface.blit(name_s, (name_x, rect.centery - name_s.get_height()))
        price = self._shop_price(item_id)
        price_s = fs.render(f"{price:,}", True, (170, 60, 30))
        surface.blit(price_s, (name_x, rect.centery + 8))

    def _draw_sell_row(self, surface, rect: pygame.Rect, entry, fs,
                       selected: bool) -> None:
        """右栏单行：图标 + 名称×数量 + 卖价；选中叠原版 orange select。"""
        if selected:
            sel = self._wz("select")
            if sel is not None:
                fit = pygame.transform.smoothscale(sel, (rect.w, rect.h + 4))
                surface.blit(fit, (rect.x, rect.y - 3))
        _src, item = entry
        icon = self._icon(item.id)
        count = f" ×{item.count}" if item.count > 1 else ""
        name_c = (60, 52, 44) if selected else (80, 72, 62)
        icon_x = rect.x - BG_RCOL_X + BG_RCOL_SLOT_CX
        name_x = rect.x - BG_RCOL_X + BG_RCOL_NAME_X
        price_w = 50
        max_w = (rect.right - 6 - price_w) - name_x
        name_txt = ellipsize(item.name + count, fs, max_w)
        name_s = fs.render(name_txt, True, name_c)
        if icon is not None:
            surface.blit(icon, (icon_x - icon.get_width() // 2,
                                rect.centery - icon.get_height() // 2))
        surface.blit(name_s, (name_x, rect.centery - name_s.get_height()))
        price = shop_mod.buy_price(self._shop_id(), item.id, self.svc.assets) or 0
        gain = shop_mod.sell_price(price) * max(1, item.count)
        gain_s = fs.render(str(gain), True, (30, 110, 60))
        surface.blit(gain_s, (name_x, rect.centery + 8))

    def _draw_fallback(self, surface, player, combat) -> None:
        """旧式深色面板：素材缺失（测试 fake assets）时兜底。"""
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        x, y = self.place(surface, (PANEL_W, PANEL_H))
        self.rect = pygame.Rect(x, y, PANEL_W, PANEL_H)
        if not draw_menu_bg(surface, self.svc, self.rect):
            pygame.draw.rect(surface, (18, 22, 30, 216), self.rect, border_radius=8)
            pygame.draw.rect(surface, (90, 96, 110), self.rect, 1, border_radius=8)

        # 标题 + 关闭
        surface.blit(f.render("商店", True, (255, 216, 96)), (x + 14, y + 5))
        self.close_rect = pygame.Rect(x + PANEL_W - 40, y + 4, 32, 18)
        surface.blit(fs.render("×", True, (235, 235, 240)), self.close_rect.topleft)

        # 页签
        tx = x + 14
        for shop_id in self.shop_ids:
            label = shop_mod.shop_name(shop_id)
            tr = pygame.Rect(tx, y + TITLE_H + 2, max(46, fs.size(label)[0] + 14), 18)
            on = shop_id == self._shop_id()
            pygame.draw.rect(surface, (60, 70, 88) if on else (34, 40, 52), tr,
                             border_radius=4)
            surface.blit(fs.render(label, True, (255, 255, 255)), (tr.x + 7, tr.y + 2))
            self.tab_rects.append((tr, shop_id))
            tx += tr.w + 6

        # 货架（左栏，可滚动）
        shelf_x = x + 14
        shelf_y = y + TITLE_H + TAB_H + 4
        items = self._shelf_items()
        shelf_rows = self._vis_rows()
        self._scroll_shelf = max(0, min(self._scroll_shelf,
                                        max(0, len(items) - shelf_rows)))
        for j in range(shelf_rows):
            i = self._scroll_shelf + j
            if i >= len(items):
                break
            item_id = items[i]
            ry = shelf_y + j * ROW_H
            rect = pygame.Rect(shelf_x, ry, SHELF_W, ROW_H - 4)
            pygame.draw.rect(surface, (60, 78, 96) if i == self.sel_shelf
                             else (36, 42, 54), rect, border_radius=4)
            icon = self._icon(item_id)
            if icon is not None:
                surface.blit(icon, (rect.x + 3, rect.y + 2))
            surface.blit(fs.render(ellipsize(self._item_name(item_id), fs, rect.w - 108),
                                   True, (230, 230, 235)), (rect.x + 32, rect.y + 5))
            price = shop_mod.buy_price(self._shop_id(), item_id, self.svc.assets) or 0
            surface.blit(fs.render(f"{price:,}", True, (255, 216, 96)),
                         (rect.right - 46, rect.y + 5))
            surface.blit(fs.render("金币", True, (210, 210, 215)),
                         (rect.right - 46, rect.y + 17))
            self.shelf_rects.append((rect, i))

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
            surface.blit(fs.render(ellipsize(item.name + count, fs, rect.w - 96),
                                   True, (230, 230, 235)), (rect.x + 32, rect.y + 5))
            price = shop_mod.buy_price(self._shop_id(), item.id, self.svc.assets) or 0
            gain = shop_mod.sell_price(price) * max(1, item.count)
            surface.blit(fs.render(str(gain), True, (140, 200, 160)),
                         (rect.right - 40, rect.y + 5))
            self.bag_rects.append((rect, i))

        # 底部：金币 + 选中价格 + 按钮
        by = self.rect.bottom - BOTTOM_H
        pygame.draw.line(surface, (70, 76, 90), (x + 12, by), (x + PANEL_W - 12, by))
        meso = combat.meso if combat is not None else 0
        surface.blit(fs.render(f"金币 {meso:,}", True, (255, 216, 96)),
                     (x + 14, by + 28))
        sel_desc = ""
        if self.sel_shelf is not None and self.sel_shelf < len(items):
            price = shop_mod.buy_price(self._shop_id(), items[self.sel_shelf],
                                       self.svc.assets) or 0
            sel_desc = f"选中 {self._item_name(items[self.sel_shelf])} · 买价 {price}"
        elif self.sel_bag is not None and self.sel_bag < len(entries):
            _src, item = entries[self.sel_bag]
            base = shop_mod.buy_price(self._shop_id(), item.id, self.svc.assets) or 0
            sel_desc = f"选中 {item.name} · 单件卖价 {shop_mod.sell_price(base)}"
        if sel_desc:
            surface.blit(fs.render(ellipsize(sel_desc, fs, 260), True, (210, 215, 225)),
                         (x + 160, by + 14))

        self.buy_rect = pygame.Rect(x + PANEL_W - 14 - BTN_W_FB, by + 14,
                                    BTN_W_FB, BTN_H_FB)
        self.sell_rect = pygame.Rect(self.buy_rect.x - BTN_W_FB - 8, by + 14,
                                     BTN_W_FB, BTN_H_FB)
        close_btn = pygame.Rect(self.sell_rect.x - 50, by + 14, 42, BTN_H_FB)
        for rect, label, color in ((self.buy_rect, "购买", (52, 110, 78)),
                                   (self.sell_rect, "出售", (110, 84, 52)),
                                   (close_btn, "关闭", (74, 78, 92))):
            pygame.draw.rect(surface, color, rect, border_radius=4)
            surface.blit(fs.render(label, True, (240, 240, 245)),
                         (rect.x + (rect.w - fs.size(label)[0]) // 2, rect.y + 5))
        self._exit_rect = close_btn
