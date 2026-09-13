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

from game.core import consumables
from game.core import item_tip
from game.core.item_tip import SLOT_NAMES, build_item_tip, tip_with_note
from game.core.stats import wear_block
from game.render.windows.core import widgets
from game.render.windows.core.manager import WindowManager
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DragPickup, Window
from game.systems.inventory import Inventory, Item, SLOT_ORDER
from game.systems.scrolls import apply_scroll, is_scroll_id, scroll_info_of, \
    scroll_of, scroll_stats

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

# 装备：175×304 纸娃娃底板，5 列 × 7 行凹槽，对齐底图烘焙的中文栏位标签
EQP_BG = "Equip/backgrnd"
EQP_W, EQP_H = 175, 304
EQP_CELL_X = [4, 38, 71, 104, 137]
EQP_CELL_Y = [34, 68, 101, 134, 167, 200, 233]
EQP_CELL_W, EQP_CELL_H = 33, 33
# slot → (col, row)，逐一对照 Equip/backgrnd 的标签：帽子/额饰/耳饰/上衣/裤裙/
# 鞋子/手套/披风/指环/盾牌/武器；套服与上衣互斥（见 Inventory.equip），同格显示。
EQP_SLOT_POS = {
    "cap": (1, 0),
    "face": (1, 1),
    "earr": (3, 2),
    "top": (1, 3), "overall": (1, 3),
    "pants": (1, 4), "shoes": (2, 5),
    "glove": (0, 4), "cape": (0, 3),
    "ring": (3, 0),
    "shield": (4, 3), "weapon": (3, 3),
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
        icon = svc.assets.equip_icon(item.id)
    else:
        icon = svc.assets.item_icon(item.id)
    if icon is None and is_scroll_id(item.id):    # WZ 无图兜底：自绘卷轴
        icon = widgets.scroll_icon()
    return icon


def _blit_icon(surface, icon: pygame.Surface, cell: pygame.Rect,
               size: int) -> None:
    """图标等比缩进 size 框并居中于格子。"""
    icon = widgets.fit_icon(icon, size)
    surface.blit(icon, (cell.x + (cell.width - icon.get_width()) // 2,
                        cell.y + (cell.height - icon.get_height()) // 2))


def _asset_desc(svc: WindowServices, item_id: str) -> str:
    """String.wz 物品描述（assets 无 item_desc 或无 desc 时为空串）。"""
    getter = getattr(svc.assets, "item_desc", None)
    if getter is None:
        return ""
    try:
        return getter(item_id) or ""
    except Exception:
        return ""


_ELIXIR_LABELS = {"pad": "物攻", "mad": "魔攻", "pdd": "物防", "mdd": "魔防",
                  "acc": "命中", "eva": "回避", "speed": "移速", "jump": "跳跃"}


def _elixir_tip(spec: dict) -> str:
    """特效药效果行：各词条百分比 + 持续时长（如「命中+5% 持续5分」）。"""
    parts = [f"{_ELIXIR_LABELS[k]}{v:+d}%"
             for k, v in consumables.elixir_mods(spec).items()]
    secs = consumables.spec_int(spec, "time") // 1000
    span = f" 持续{secs // 60}分" if secs >= 60 and secs % 60 == 0 \
        else f" 持续{secs}秒"
    return " ".join(parts) + span


def _item_tip(item: Item, desc: str = "",
              scroll_rate: Optional[int] = None) -> str:
    """消耗品 / 其他物品悬停提示文本；desc 为 String.wz 介绍。"""
    lines = [item.name]
    if item.kind == "consume":
        spec = item.info.get("spec") or {}
        if spec.get("hp"):
            lines.append(f"恢复 HP {spec['hp']}")
        elif spec.get("hpR"):
            lines.append(f"恢复 HP {spec['hpR']}%")
        if spec.get("mp"):
            lines.append(f"恢复 MP {spec['mp']}")
        elif spec.get("mpR"):
            lines.append(f"恢复 MP {spec['mpR']}%")
        if is_scroll_id(item.id):
            if scroll_rate is not None:
                lines.append(f"成功率 {scroll_rate}%")
            lines.append("双击强化已穿装备 / 拖到目标装备上")
        elif consumables.is_return_scroll(spec):
            lines.append("双击返回城镇")
        elif consumables.is_elixir(spec):
            lines.append(_elixir_tip(spec))
            lines.append("双击使用")
        elif consumables.is_healing(spec):
            lines.append("双击使用")
    if desc:
        lines.append(desc)
    return "\n".join(lines)


_EQUIP_COMPARE_LABELS = {
    "incPAD": "物攻", "incMAD": "魔攻", "incPDD": "物防", "incMDD": "魔防",
    "incSTR": "力量", "incDEX": "敏捷", "incINT": "智力", "incLUK": "运气",
    "incMHP": "HP", "incMMP": "MP", "incACC": "命中", "incEVA": "回避",
    "incSpeed": "速度", "incJump": "跳跃",
}


def _equip_diff_note(svc: WindowServices, item: Item) -> str:
    """背包装备与身上同槽位装备的词条差摘要（换装不靠记忆）。"""
    player = svc.player()
    old = player.inventory.equipped.get(item.slot) if item.slot else None
    if old is None:
        return ""
    diffs = []
    for key, label in _EQUIP_COMPARE_LABELS.items():
        delta = item.stat(key) - old.stat(key)
        if delta:
            diffs.append(f"{label}{delta:+d}")
    if not diffs:
        return f"与身上「{old.name}」持平"
    return f"对比[{old.name}]：" + "  ".join(diffs[:8])


def _tip_payload(svc: WindowServices, item: Item):
    """悬停内容：装备走原版结构化行，其余保持纯文本 tip。"""
    desc = _asset_desc(svc, item.id)
    if item.kind == "equip":
        player = svc.player()
        tip = build_item_tip(item, player.level, player.total_stats(),
                             player.job, desc=desc)
        lines = ["双击穿上 / 拖到装备窗穿上" if item.slot
                 else "（此 WZ 资源缺少外观，无法穿戴）"]
        diff = _equip_diff_note(svc, item)
        if diff:
            lines.append(diff)
        return tip_with_note(tip, "\n".join(lines))
    scroll_rate = None
    if is_scroll_id(item.id):
        scroll_rate, _ = scroll_stats(scroll_info_of(svc.assets, item.id))
    return _item_tip(item, desc, scroll_rate=scroll_rate)


def _meso_of(svc: WindowServices) -> int:
    """金币页脚读数：combat 或其 meso 缺失时按 0（None 安全）。"""
    combat = svc.combat
    if combat is None or combat.meso is None:
        return 0
    return int(combat.meso)


def _cast_scroll(svc: WindowServices, player, scroll_item: Item,
                 target: Optional[Item]) -> None:
    """对目标装备施放一张卷轴：校验 → 扣费 → roll → 扣卷轴 → 刷新属性。

    双击（目标 = 当前已穿对应栏位）与拖拽（目标 = 落点装备）共用；
    target 为 None 时只提示、不扣任何东西。
    """
    scroll = scroll_of(scroll_item.id)
    if scroll is None:
        svc.flash("无法使用的卷轴")
        return
    if target is None:
        svc.flash("请把卷轴拖到要强化的装备上")
        return
    combat = svc.combat
    meso = combat.meso if combat is not None and combat.meso is not None else 0
    info = scroll_info_of(svc.assets, scroll_item.id)
    result = apply_scroll(scroll, target, random.Random(),
                          level=player.level, meso=meso, info=info)
    if result is None:
        svc.flash("无法强化：栏位/武器不符或强化次数已用完")
        return
    if not result["charged"]:
        svc.flash(result["msg"])
        return
    if combat is not None:
        combat.meso = result["meso"]
    player.inventory.use_consume(scroll_item.id)
    player.refresh_equips()
    svc.flash(result["msg"])


# ═══════════════════════════════════════════════════════════════════
# 背包窗口
# ═══════════════════════════════════════════════════════════════════
class InventoryWindow(Window):
    """道具栏：页签 + 24 格物品 + 滚动 + 拖扔 / 双击使用（manager 驱动）。"""

    key = "inv"
    also_close = "equip"       # × 关背包联动纸娃娃（与 I 键同开同关对称）

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self.tab = "consume"                              # consume | equip | etc
        self._scrolls: Dict[str, widgets.ScrollList] = {}
        self._cell_rects: List[Tuple[pygame.Rect, str, int]] = []
        self._tab_rects: List[Tuple[pygame.Rect, str]] = []
        self._sort_rect: Optional[pygame.Rect] = None     # 「整理」按钮热区
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

    # ── 事件：页签切换 + 整理 + 窗内点击吞掉；滚轮按行 ──────────────
    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        for rect, key in self._tab_rects:
            if rect.collidepoint(pos):
                self.tab = key
                return True
        if self._sort_rect is not None and self._sort_rect.collidepoint(pos):
            moved = self.svc.player().inventory.sort_tab(self.tab)
            self.svc.flash("已整理背包" if moved else "背包已是整齐状态")
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

    def take_for_drop(self, pk: DragPickup,
                      qty: Optional[int] = None) -> Optional[Item]:
        src, item = pk.source, pk.item
        inv = self.svc.player().inventory
        if src[1] == "equip":
            # 确认框弹出期间索引可能已失效：仍是同一件才取出
            if 0 <= src[2] < len(inv.equips) and inv.equips[src[2]] is item:
                return inv.pop_equip(src[2])
            return None
        if qty is not None and qty < item.count:
            return inv.take_units(item.id, qty)
        return inv.take_stack(item.id)

    def handle_drop(self, pk: DragPickup, pos) -> bool:
        """从纸娃娃拖装备到背包 = 脱下回包（免双击，扔错窗口的安全出口）。"""
        if pk.kind != "item" or not self.rect.collidepoint(pos):
            return False
        if is_scroll_id(pk.item.id):        # 卷轴落到背包：强化落点上的背包装备
            self._drop_scroll(pk.item, pos)
            return True
        src = pk.source
        if src and src[0] == "slot":
            player = self.svc.player()
            if player.inventory.unequip(src[1]):
                player.refresh_equips()
                self.svc.flash(f"已脱下 {pk.item.name}")
            else:
                self.svc.flash("装备栏已满，脱下失败（装备仍在身上）")
            return True
        if self._sort_rect is not None and self._sort_rect.collidepoint(pos):
            return True
        return False

    def handle_drag_motion(self, pk: DragPickup, pos) -> bool:
        """拖拽卷轴悬停页签自动切页：可从消耗页拖到装备页强化背包装备。"""
        if pk.kind != "item" or not is_scroll_id(pk.item.id):
            return False
        for rect, key in self._tab_rects:
            if rect.collidepoint(pos) and key != self.tab:
                self.tab = key
                return True
        return False

    def _drop_scroll(self, scroll_item: Item, pos) -> None:
        """落点上的背包装备（仅装备页格）作为卷轴目标。"""
        inv = self.svc.player().inventory
        target: Optional[Item] = None
        for cell, tab, idx in self._cell_rects:
            if cell.collidepoint(pos):
                if tab == "equip" and 0 <= idx < len(inv.equips):
                    target = inv.equips[idx]
                break
        _cast_scroll(self.svc, self.svc.player(), scroll_item, target)

    # ── 双击：使用消耗品 / 穿戴装备（含门控与卷轴流程）─────────────
    def _click_cell(self, tab: str, idx: int) -> None:
        player = self.svc.player()
        inv = player.inventory
        if tab == "consume":
            items = list(inv.consumes.values())
            if idx < len(items):
                item = items[idx]
                if is_scroll_id(item.id):    # 官方 204 段强化卷轴：走强化流程
                    self._apply_scroll(item, player)
                    return
                err = consumables.use(player, item.id)
                if err is not None:
                    self.svc.flash(f"{item.name}：{err}")
        elif tab == "equip":
            items = list(inv.equips)
            if idx < len(items) and items[idx].slot is None:
                self.svc.flash(f"无法穿戴 {items[idx].name}")
            elif idx < len(items):
                block = wear_block(items[idx].info, player.level,
                                   player.total_stats(), job=player.job)
                if block is not None:
                    self.svc.flash(f"无法穿戴：{block}")
                elif inv.equip(idx):
                    player.refresh_equips()
                else:
                    self.svc.flash("装备栏已满")

    def _apply_scroll(self, scroll_item: Item, player) -> None:
        """双击卷轴：对当前已穿的对应栏位装备施放（拖拽路径见 handle_drop）。"""
        scroll = scroll_of(scroll_item.id)
        if scroll is None:
            self.svc.flash("无法使用的卷轴")
            return
        target = player.inventory.equipped.get(scroll["slot"])
        if target is None:
            self.svc.flash("请先装备目标装备")
            return
        _cast_scroll(self.svc, player, scroll_item, target)

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

        # 物品格（底图已含格子，只叠图标 + 数量 + 悬停 tooltip）
        sl = self._scroll_for(self.tab)
        sl.clamp(len(items), INV_SLOTS)
        base = sl.offset
        mouse = self.svc.mouse()
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
                    self.svc.tooltip(_tip_payload(self.svc, item))
            self._cell_rects.append((cell, self.tab, idx))

        # 右侧缘滚动指示（内容超一屏才画）
        widgets.draw_page_indicator(
            surface, pygame.Rect(x + INV_W - 6, y + 50, 4, 204),
            base, len(items), INV_SLOTS)

        # 底部页脚：金币图标 + 持有数 + 「整理」钮（白底板 → 深棕字）
        coin = widgets.wz_surface(self.svc, "Item/BtCoin/normal/0")
        if coin is not None:
            surface.blit(coin, (x + 10, y + 266))
        surface.blit(fs.render(f"{_meso_of(self.svc):,}", True, (110, 68, 18)),
                     (x + 28, y + 268))
        self._sort_rect = pygame.Rect(x + INV_W - 52, y + 266, 44, 18)
        self._draw_sort_button(surface, self._sort_rect)

    def _draw_sort_button(self, surface, rect: pygame.Rect) -> None:
        fs = self.svc.ui.font_small
        hover = rect.collidepoint(self.svc.mouse())
        pygame.draw.rect(surface, (232, 222, 200) if hover else (214, 204, 182),
                         rect, border_radius=3)
        pygame.draw.rect(surface, (140, 120, 80), rect, 1, border_radius=3)
        label = "整理"
        surface.blit(fs.render(label, True, (80, 60, 30)),
                     (rect.centerx - fs.size(label)[0] // 2,
                      rect.centery - fs.size(label)[1] // 2))

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
        self._sort_rect = pygame.Rect(x + w - 56, y + 28, 44, 18)
        self._draw_sort_button(surface, self._sort_rect)
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
        mouse = self.svc.mouse()
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
                    self.svc.tooltip(_tip_payload(self.svc, item))
            self._cell_rects.append((cell, self.tab, idx))


# ═══════════════════════════════════════════════════════════════════
# 纸娃娃装备窗
# ═══════════════════════════════════════════════════════════════════
class EquipWindow(Window):
    """装备栏：21 格凹槽纸娃娃；拖出 / 双击 = 脱下（回背包或扔出）。"""

    key = "equip"
    also_close = "inv"         # × 关纸娃娃联动背包（与 I 键语义对称）

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

    def take_for_drop(self, pk: DragPickup,
                      qty: Optional[int] = None) -> Optional[Item]:
        """拖出扔地（经确认框）：从装备栏取下（不占背包），并刷新外观。"""
        player = self.svc.player()
        slot = pk.source[1]
        if player.inventory.equipped.get(slot) is not pk.item:
            return None                    # 确认期间已换位 → 放弃
        got = player.inventory.pop_equipped(slot)
        if got is not None:
            player.refresh_equips()
        return got

    def handle_drop(self, pk: DragPickup, pos) -> bool:
        """把背包散件装备拖到纸娃娃 = 穿戴（门控与双击一致，含属性对比提示）。"""
        if pk.kind != "item" or not self.rect.collidepoint(pos):
            return False
        item = pk.item
        if is_scroll_id(item.id):          # 卷轴落到纸娃娃：强化落点槽位的已穿装备
            target: Optional[Item] = None
            for cell, slot in self._slot_rects:
                if cell.collidepoint(pos):
                    target = self.svc.player().inventory.equipped.get(slot)
                    break
            _cast_scroll(self.svc, self.svc.player(), item, target)
            return True
        if getattr(item, "kind", "") != "equip":
            self.svc.flash("只有装备能拖到装备栏")
            return True
        src = pk.source
        if not (src and src[0] == "cell" and src[1] == "equip"):
            self.svc.flash("只能从背包的装备页签拖入")
            return True
        player = self.svc.player()
        inv = player.inventory
        idx = src[2]
        if not (0 <= idx < len(inv.equips)) or inv.equips[idx] is not item:
            return True                    # 拖拽期间列表已变 → 保守放弃
        block = wear_block(item.info, player.level, player.total_stats(),
                           job=player.job)
        if item.slot is None:
            self.svc.flash(f"无法穿戴 {item.name}")
        elif block is not None:
            self.svc.flash(f"无法穿戴：{block}")
        elif inv.equip(idx):
            player.refresh_equips()
            self.svc.flash(f"已穿上 {item.name}")
        else:
            self.svc.flash("装备栏已满")
        return True

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        inv = self.svc.player().inventory
        bg = widgets.wz_surface(self.svc, EQP_BG)
        self._fallback = bg is None
        self._size = (158, _inv_last_rect.height) if self._fallback else (EQP_W, EQP_H)
        self._slot_rects.clear()
        x, y = self.place(surface, self._size)
        mouse = self.svc.mouse()
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
                    self.svc.tooltip(_tip_payload(self.svc, item))
            self._slot_rects.append((cell, slot))


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
                    self.svc.tooltip(_tip_payload(self.svc, item))
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
