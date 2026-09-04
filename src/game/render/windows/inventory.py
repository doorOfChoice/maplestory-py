"""组件化背包 / 纸娃娃装备窗：拖出扔地、双击使用/穿戴/脱下（状态机归 WindowManager）。

几何与文案 1:1 迁移自 panels.py 的 _draw_inventory / _draw_equip 系：
· InventoryWindow（key="inv"）：页签 消耗/装备/其他 + 24 格物品格 + 数量描边
  + 金币页脚（meso 读 svc.combat，缺失按 0）；每页签独立滚动（步长一行）。
· EquipWindow（key="equip"）：SLOT_ORDER 凹槽纸娃娃，拖出 / 双击 = 脱下。
· 拖拽三态契约：pickup 给出 DragPickup（source ("cell", tab, idx) /
  ("slot", name)，home = 来源窗口外框），manager 负责 6px 阈值、0.35s 双击
  与「拖出 home 松手 → take_for_drop」判定；本模块只做取出 / 使用 / 穿戴。

fallback（素材缺失自绘）与官方底板两路径布局与旧实现保持一致；fallback 的
装备窗锚点沿用「紧贴背包右侧、等高」的旧行为（经模块级 _inv_last_rect 传递，
两窗口在本模块内配对，manager 保证背包先绘）。
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

import pygame

from game.core.jobs import JOBS
from game.core.stats import wear_block
from game.render.windows.core import widgets
from game.render.windows.core.manager import WindowManager
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DragPickup, Window
from game.systems.inventory import Inventory, Item, SLOT_ORDER, islot_to_slot
from game.systems.scrolls import SCROLLS, apply_scroll, is_scroll_id

SLOT_NAMES = {
    "cap": "帽子", "face": "脸饰", "earr": "耳环", "top": "上衣",
    "overall": "连身衣", "pants": "裤子", "shoes": "鞋子",
    "glove": "手套", "cape": "披风", "ring": "戒指",
    "shield": "盾牌", "weapon": "武器",
}

CELL = 38          # 旧自绘面板用（fallback）
PAD = 10

# ── 原版窗口几何（由 wz/UI.wz 底图逐像素实测，同 panels.py）────────
# 背包：175×307，4 列 × 6 行 = 24 格（原版老式背包），格 36×34
INV_BG = "Item/backgrnd"
INV_W, INV_H = 175, 307
INV_CELL_X = [4, 40, 76, 112]
INV_CELL_Y = [50, 84, 118, 152, 186, 220]
INV_CELL_W, INV_CELL_H = 36, 34
INV_COLS = len(INV_CELL_X)
INV_SLOTS = INV_COLS * len(INV_CELL_Y)          # 24

# 装备：175×304 纸娃娃底板，5 列 × 7 行凹槽（仅 21 格有效）
EQP_BG = "Equip/backgrnd"
EQP_W, EQP_H = 175, 304
EQP_CELL_X = [4, 38, 71, 104, 137]
EQP_CELL_Y = [34, 68, 101, 134, 167, 200, 233]
EQP_CELL_W, EQP_CELL_H = 33, 33
EQP_SLOT_POS = {                                 # slot → (col, row)
    "cap": (1, 0), "face": (2, 0),
    "earr": (0, 1), "weapon": (1, 1), "cape": (3, 1), "ring": (4, 1),
    "top": (2, 2), "shield": (3, 2),
    "glove": (0, 3), "overall": (2, 3),
    "pants": (2, 4), "shoes": (1, 4),
}

# 页签（带原版汉字，宽 26~27 高 16）：游戏内 3 页 → 原版 装备/消耗/其他
TAB_INDEX = {"equip": 0, "consume": 1, "etc": 3}
TAB_LABEL = {"consume": "消耗", "equip": "装备", "etc": "其他"}

BAR_RESERVE = 58     # 底部状态栏预留高度（无 StatusBar 素材时同值）

# fallback 装备窗需贴背包右缘（旧 Panels 同帧持有 _inv_rect，此处模块级配对传递）
_inv_last_rect = pygame.Rect(0, 0, 0, 0)


# ── 共享小工具 ─────────────────────────────────────────────────────
def _tab_items(inv: Inventory, tab: str) -> List[Item]:
    """页签对应的物品列表（与绘制 / 拖拽 / 使用同一顺序）。"""
    if tab == "consume":
        return list(inv.consumes.values())
    if tab == "etc":
        return list(inv.etcs.values())
    return list(inv.equips)


def _icon_of(svc: WindowServices, item: Item) -> Optional[pygame.Surface]:
    if item.kind == "equip":
        return svc.assets.equip_icon(item.id)
    return svc.assets.item_icon(item.id)


def _blit_icon(surface, icon: pygame.Surface, cell: pygame.Rect,
               size: int) -> None:
    """图标等比缩进 size 框并居中于格子。"""
    icon = widgets.fit_icon(icon, size)
    surface.blit(icon, (cell.x + (cell.width - icon.get_width()) // 2,
                        cell.y + (cell.height - icon.get_height()) // 2))


def _item_tip(item: Item) -> str:
    """物品悬停提示文本（同 panels._item_tip）。"""
    lines = [item.name]
    if item.kind == "equip":
        parts = []
        for key, label in (("incPAD", "攻"), ("incPDD", "防"),
                           ("incSTR", "力"), ("incDEX", "敏"),
                           ("incHP", "HP"), ("incMP", "MP")):
            v = item.stat(key)
            if v:
                parts.append(f"{label}+{v}")
        if parts:
            lines.append(" ".join(parts))
        slot = islot_to_slot(item.info.get("islot") or "")
        if slot:
            lines.append(SLOT_NAMES.get(slot, slot) + " · 点击穿上")
        else:
            lines.append("（此 WZ 资源缺少外观，无法穿戴）")
    elif item.kind == "consume":
        spec = item.info.get("spec") or {}
        if spec.get("hp"):
            lines.append(f"恢复 HP {spec['hp']}")
        if spec.get("mp"):
            lines.append(f"恢复 MP {spec['mp']}")
        if is_scroll_id(item.id):
            sc = SCROLLS.get(item.id)
            if sc:
                lines.append(f"{sc['name']} 成功率 {sc['rate']}%")
            lines.append("双击对当前武器强化")
        else:
            lines.append("点击使用")
    return "\n".join(lines)


def _meso_of(svc: WindowServices) -> int:
    """金币页脚读数：combat 或其 meso 缺失时按 0（None 安全）。"""
    combat = svc.combat
    if combat is None or combat.meso is None:
        return 0
    return int(combat.meso)


# ═══════════════════════════════════════════════════════════════════
# 背包窗口
# ═══════════════════════════════════════════════════════════════════
class InventoryWindow(Window):
    """道具栏：页签 + 24 格物品 + 滚动 + 拖扔 / 双击使用（manager 驱动）。"""

    key = "inv"

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self.tab = "consume"                              # consume | equip | etc
        self._scrolls: Dict[str, widgets.ScrollList] = {}
        self._cell_rects: List[Tuple[pygame.Rect, str, int]] = []
        self._tab_rects: List[Tuple[pygame.Rect, str]] = []
        self._fallback = False
        self._size: Tuple[int, int] = (INV_W, INV_H)

    # ── 定位：官方左下锚点；fallback 同旧（12, vh−150−h）───────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        if self._fallback:
            return (12, vh - 150 - self._size[1])
        return (4, vh - INV_H - BAR_RESERVE - 2)

    def _scroll_for(self, tab: str) -> widgets.ScrollList:
        sl = self._scrolls.get(tab)
        if sl is None:
            sl = widgets.ScrollList(INV_COLS)
            self._scrolls[tab] = sl
        return sl

    # ── 事件：页签切换 + 窗内点击吞掉；滚轮按行 ────────────────────
    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        for rect, key in self._tab_rects:
            if rect.collidepoint(pos):
                self.tab = key
                return True
        return self.rect.collidepoint(pos)

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        if not self.rect.collidepoint(pos):
            return False
        items = _tab_items(self.svc.player().inventory, self.tab)
        self._scroll_for(self.tab).scroll(amount, len(items), INV_SLOTS)
        return True

    # ── 拖拽三态：source = ("cell", tab, idx)（idx 为整表绝对序号）──
    def pickup(self, pos: Tuple[int, int]) -> Optional[DragPickup]:
        inv = self.svc.player().inventory
        for cell, tab, idx in self._cell_rects:
            if cell.collidepoint(pos):
                items = _tab_items(inv, tab)
                if idx < len(items):
                    return DragPickup(source=("cell", tab, idx),
                                      item=items[idx], home=self.rect)
                return None
        return None

    def activate(self, pk: DragPickup) -> None:
        src = pk.source
        if src[0] == "cell":
            self._click_cell(src[1], src[2])

    def take_for_drop(self, pk: DragPickup) -> Optional[Item]:
        src, item = pk.source, pk.item
        inv = self.svc.player().inventory
        if src[1] == "equip":
            return inv.pop_equip(src[2])
        return inv.take_stack(item.id)

    # ── 双击：使用消耗品 / 穿戴装备（含门控与卷轴流程）─────────────
    def _click_cell(self, tab: str, idx: int) -> None:
        player = self.svc.player()
        inv = player.inventory
        if tab == "consume":
            items = list(inv.consumes.values())
            if idx < len(items):
                item = items[idx]
                if is_scroll_id(item.id):
                    self._apply_scroll(item, player)
                    return
                spec = inv.use_consume(item.id)
                if spec:
                    hp = int(spec.get("hp") or 0)
                    mp = int(spec.get("mp") or 0)
                    if hp:
                        player.hp = min(player.max_hp, player.hp + hp)
                    if mp:
                        player.mp = min(player.max_mp, player.mp + mp)
        elif tab == "equip":
            items = list(inv.equips)
            if idx < len(items) and items[idx].slot is None:
                self.svc.flash(f"无法穿戴 {items[idx].name}")
            elif idx < len(items):
                block = wear_block(items[idx].info, player.level,
                                   player.total_stats())
                if block is not None:
                    self.svc.flash(f"无法穿戴：{block}")
                elif inv.equip(idx):
                    player.refresh_equips()
                else:
                    self.svc.flash("装备栏已满")

    def _apply_scroll(self, scroll_item: Item, player) -> None:
        """双击卷轴：对当前武器使用（扣强化费，成功/失败各耗一次次数）。"""
        scroll = SCROLLS.get(scroll_item.id)
        if scroll is None:
            self.svc.flash("无法使用的卷轴")
            return
        target = player.inventory.equipped.get(scroll["slot"])
        if target is None:
            self.svc.flash("请先装备目标装备")
            return
        combat = self.svc.combat
        meso = combat.meso if combat is not None else 0
        result = apply_scroll(scroll, target, random.Random(),
                              level=player.level, meso=meso)
        if result is None:
            self.svc.flash("无法强化：栏位不符或强化次数已用完")
            return
        if not result["charged"]:
            self.svc.flash(result["msg"])
            return
        if combat is not None:
            combat.meso = result["meso"]
        player.inventory.use_consume(scroll_item.id)
        player.refresh_equips()
        self.svc.flash(result["msg"])

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        global _inv_last_rect
        player = self.svc.player()
        items = _tab_items(player.inventory, self.tab)
        bg = widgets.wz_surface(self.svc, INV_BG)
        self._fallback = bg is None
        if self._fallback:
            cols = 6
            rows = max(2, (max(len(items), 8) + cols - 1) // cols)
            self._size = (PAD * 2 + cols * CELL, 58 + rows * CELL)
        else:
            self._size = (INV_W, INV_H)
        self._cell_rects.clear()
        self._tab_rects.clear()
        x, y = self.place(surface, self._size)
        _inv_last_rect = self.rect
        if self._fallback:
            self._draw_fallback(surface, items)
            return

        fs = self.svc.ui.font_small
        surface.blit(bg, (x, y))
        self.add_chrome(surface, x, y, INV_W, 23)

        # 页签条（底图 y23~42 空带；原版汉字烤死在图内）：选中=enabled
        tx = x + 4
        for key in ("consume", "equip", "etc"):
            ti = TAB_INDEX[key]
            state = "enabled" if key == self.tab else "disabled"
            img = widgets.wz_surface(self.svc, f"Item/Tab/{state}/{ti}")
            if img is not None:
                surface.blit(img, (tx, y + 25))
                self._tab_rects.append(
                    (pygame.Rect(tx, y + 25, img.get_width(), img.get_height()), key))
                tx += img.get_width() + 1
            else:
                tr = pygame.Rect(tx, y + 25, 30, 16)
                pygame.draw.rect(surface, (60, 70, 88) if key == self.tab
                                 else (34, 40, 52), tr, border_radius=4)
                surface.blit(fs.render(TAB_LABEL[key], True, (255, 255, 255)),
                             (tr.x + 2, tr.y + 2))
                self._tab_rects.append((tr, key))
                tx += 31

        # 标题行右侧：当前页数量（浅色标题条 → 深字）
        cap_txt = fs.render(str(len(items)) + "项", True, (70, 72, 86))
        surface.blit(cap_txt, (x + INV_W - cap_txt.get_width() - 40, y + 6))

        # 物品格（底图已含格子，只叠图标 + 数量 + 悬停 tooltip）
        sl = self._scroll_for(self.tab)
        sl.clamp(len(items), INV_SLOTS)
        base = sl.offset
        mouse = pygame.mouse.get_pos()
        for i in range(INV_SLOTS):
            idx = base + i
            cx = x + INV_CELL_X[i % INV_COLS]
            cy = y + INV_CELL_Y[i // INV_COLS]
            cell = pygame.Rect(cx, cy, INV_CELL_W, INV_CELL_H)
            if idx < len(items):
                item = items[idx]
                icon = _icon_of(self.svc, item)
                if icon is not None:
                    _blit_icon(surface, icon, cell, 32)
                if item.count > 1:
                    cnt = fs.render(str(item.count), True, (255, 255, 255))
                    shadow = fs.render(str(item.count), True, (0, 0, 0))
                    surface.blit(shadow, (cell.right - cnt.get_width() - 1,
                                          cell.bottom - cnt.get_height() + 1))
                    surface.blit(cnt, (cell.right - cnt.get_width() - 2,
                                       cell.bottom - cnt.get_height()))
                if cell.collidepoint(mouse):
                    self.svc.tooltip(_item_tip(item))
            self._cell_rects.append((cell, self.tab, idx))

        # 底部页脚：金币图标 + 持有数（白底板 → 深棕字）
        coin = widgets.wz_surface(self.svc, "Item/BtCoin/normal/0")
        if coin is not None:
            surface.blit(coin, (x + 10, y + 266))
        surface.blit(fs.render(f"金币 {_meso_of(self.svc):,}", True, (110, 68, 18)),
                     (x + 28, y + 265))

    def _draw_fallback(self, surface, items: List[Item]) -> None:
        """素材缺失 → 旧自绘背包（布局逐行对齐 panels._draw_inventory_fallback）。"""
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        x, y = self.rect.x, self.rect.y
        w, h = self.rect.size
        widgets.panel_frame(surface, self.rect)
        surface.blit(f.render("道具栏 (I)", True, (235, 235, 240)), (x + PAD, y + 8))
        meso_txt = f.render(f"{_meso_of(self.svc)} 枫币", True, (255, 220, 90))
        surface.blit(meso_txt, (x + w - PAD - 34 - meso_txt.get_width(), y + 8))
        self.add_chrome(surface, x, y, w, 24)
        for i, key in enumerate(("consume", "equip", "etc")):
            tr = pygame.Rect(x + PAD + i * 58, y + 28, 54, 18)
            on = key == self.tab
            pygame.draw.rect(surface, (60, 70, 88) if on else (34, 40, 52),
                             tr, border_radius=4)
            label = TAB_LABEL[key]
            surface.blit(fs.render(label, True, (255, 255, 255)),
                         (tr.x + (tr.w - fs.size(label)[0]) // 2, tr.y + 3))
            self._tab_rects.append((tr, key))
        # 超 24 种时滚动：scroll 为首格索引（沿用 INV_SLOTS 一屏容量）
        sl = self._scroll_for(self.tab)
        sl.clamp(len(items), INV_SLOTS)
        cols = 6
        rows = (h - 58) // CELL
        mouse = pygame.mouse.get_pos()
        for i in range(cols * rows):
            idx = sl.offset + i
            cx = x + PAD + (i % cols) * CELL
            cy = y + 52 + (i // cols) * CELL
            cell = pygame.Rect(cx, cy, CELL - 4, CELL - 4)
            pygame.draw.rect(surface, (40, 46, 60), cell, border_radius=4)
            if idx < len(items):
                item = items[idx]
                icon = _icon_of(self.svc, item)
                if icon is not None:
                    _blit_icon(surface, icon, cell, 32)
                if item.count > 1:
                    cnt = fs.render(str(item.count), True, (255, 255, 255))
                    surface.blit(cnt, (cell.right - cnt.get_width() - 2,
                                       cell.bottom - cnt.get_height() + 1))
                if cell.collidepoint(mouse):
                    self.svc.tooltip(_item_tip(item))
            self._cell_rects.append((cell, self.tab, idx))


# ═══════════════════════════════════════════════════════════════════
# 纸娃娃装备窗
# ═══════════════════════════════════════════════════════════════════
class EquipWindow(Window):
    """装备栏：21 格凹槽纸娃娃；拖出 / 双击 = 脱下（回背包或扔出）。"""

    key = "equip"

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self._slot_rects: List[Tuple[pygame.Rect, str]] = []
        self._fallback = False
        self._size: Tuple[int, int] = (EQP_W, EQP_H)

    # ── 定位：默认锚在背包默认位置右侧（两窗各自独立可拖）──────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        if self._fallback:
            return (_inv_last_rect.right + 10, _inv_last_rect.y)
        return (4 + INV_W + 2,
                vh - INV_H - BAR_RESERVE - 2 + (INV_H - EQP_H) // 2)

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    # ── 拖拽三态：source = ("slot", name) ──────────────────────────
    def pickup(self, pos: Tuple[int, int]) -> Optional[DragPickup]:
        inv = self.svc.player().inventory
        for cell, slot in self._slot_rects:
            if cell.collidepoint(pos):
                item = inv.equipped.get(slot)
                if item is not None:
                    return DragPickup(source=("slot", slot),
                                      item=item, home=self.rect)
                return None
        return None

    def activate(self, pk: DragPickup) -> None:
        """双击纸娃娃格：脱下回背包；背包装备栏位不足则提示。"""
        player = self.svc.player()
        if player.inventory.unequip(pk.source[1]):
            player.refresh_equips()
        else:
            self.svc.flash("装备栏已满")

    def take_for_drop(self, pk: DragPickup) -> Optional[Item]:
        """拖出扔地：直接从装备栏取下（不占背包），并刷新外观。"""
        player = self.svc.player()
        got = player.inventory.pop_equipped(pk.source[1])
        if got is not None:
            player.refresh_equips()
        return got

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        inv = self.svc.player().inventory
        fs = self.svc.ui.font_small
        bg = widgets.wz_surface(self.svc, EQP_BG)
        self._fallback = bg is None
        self._size = (158, _inv_last_rect.height) if self._fallback else (EQP_W, EQP_H)
        self._slot_rects.clear()
        x, y = self.place(surface, self._size)
        mouse = pygame.mouse.get_pos()
        if self._fallback:
            self._draw_fallback(surface, inv, mouse)
            return

        surface.blit(bg, (x, y))
        self.add_chrome(surface, x, y, EQP_W, 30)
        for slot in SLOT_ORDER:
            pos = EQP_SLOT_POS.get(slot)
            if pos is None:
                continue
            cx = x + EQP_CELL_X[pos[0]]
            cy = y + EQP_CELL_Y[pos[1]]
            cell = pygame.Rect(cx, cy, EQP_CELL_W, EQP_CELL_H)
            item = inv.equipped.get(slot)
            if item is not None:
                icon = _icon_of(self.svc, item)
                if icon is not None:
                    _blit_icon(surface, icon, cell, 32)
                if cell.collidepoint(mouse):
                    self.svc.tooltip(_item_tip(item))
            self._slot_rects.append((cell, slot))

        # 标题条右侧：职业 + 攻/防摘要（浅色条 → 深字）
        player = self.svc.player()
        job_name = JOBS.get(player.job).name if player.job in JOBS else ""
        stat = fs.render(
            f"{job_name}  攻 {player.attack_value()} 防 {player.defense_value()}",
            True, (70, 72, 86))
        surface.blit(stat, (x + EQP_W - stat.get_width() - 40, y + 6))

    def _draw_fallback(self, surface, inv: Inventory,
                       mouse: Tuple[int, int]) -> None:
        """素材缺失 → 旧自绘装备栏（对齐 panels._draw_equip_fallback）。"""
        player = self.svc.player()
        f, fs = self.svc.ui.font, self.svc.ui.font_small
        x, y = self.rect.x, self.rect.y
        w, h = self.rect.size
        widgets.panel_frame(surface, self.rect)
        surface.blit(f.render("装备栏", True, (235, 235, 240)), (x + PAD, y + 8))
        stat = fs.render(
            f"攻 {player.attack_value()} 防 {player.defense_value()} "
            f"SP {player.skills.total_sp}", True, (150, 210, 160))
        surface.blit(stat, (x + w - PAD - 34 - stat.get_width(), y + 9))
        self.add_chrome(surface, x, y, w, 24)
        for i, slot in enumerate(SLOT_ORDER):
            cx = x + PAD + (i % 2) * 70
            cy = y + 32 + (i // 2) * (CELL + 2)
            if cy + CELL > self.rect.bottom - 6:
                break
            cell = pygame.Rect(cx, cy, 64, CELL - 4)
            pygame.draw.rect(surface, (40, 46, 60), cell, border_radius=4)
            label = fs.render(SLOT_NAMES.get(slot, slot), True, (130, 138, 152))
            surface.blit(label, (cx + 4, cy + 2))
            item = inv.equipped.get(slot)
            if item is not None:
                icon = _icon_of(self.svc, item)
                if icon is not None:
                    icon = widgets.fit_icon(icon, 22)
                    surface.blit(icon, (cx + cell.w - icon.get_width() - 3,
                                        cy + cell.h - icon.get_height() - 3))
                if cell.collidepoint(mouse):
                    self.svc.tooltip(_item_tip(item))
            self._slot_rects.append((cell, slot))


# ── I 键语义：背包与纸娃娃同开同关（Task7 由 game.py 调用）─────────
def toggle_inventory_pair(mgr: WindowManager) -> None:
    """等价旧 Panels.toggle_inventory：关闭时清掉进行中的拖拽。"""
    inv = mgr.get("inv")
    equip = mgr.get("equip")
    if inv.visible:
        inv.close()
        equip.close()
        mgr.cancel_interactions()
    else:
        inv.open()
        equip.open()
