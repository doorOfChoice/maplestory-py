"""交互面板：背包 / 装备栏 / 状态窗 / 技能窗口 / 快捷栏 —— 全部使用 UI.wz 原版素材。

· 背包窗口：UIWindow/Item/backgrnd（标题/格子底纹已烤死在图内），
  页签用 Item/Tab/enabled|disabled 0..4（0=装备 1=消耗 3=其他，带原版汉字），
  底部页脚画 Item/BtCoin + 金币数。
· 装备栏窗口：UIWindow/Equip/backgrnd 纸娃娃底板，按原版凹槽位置放装备图标。
· 状态窗（B 键）：UIWindow/Stat/backgrnd，四维行右端嵌 BtApUp「+」按钮，
  底部 BtAuto 一键分配；穿戴需求（reqLevel/四维）在点击装备时门控。
· 技能窗口：UIWindow/Skill/backgrnd，升级按钮用 Skill/BtSpUp。
· 按键设置窗（O）：动作列表 + 单击录入改绑（冲突互换）、右键恢复默认。
· 快捷栏：UIWindow/ShortCut/backgrnd 竖条，技能图标嵌在格内。
· Tooltip：UIWindow/ContextMenu 三段（t/c/s）官方深色底。

任何素材缺失时自动退回旧版自绘面板，保证不闪退。
交互：物品**双击**使用/穿戴/脱下（0.35s 内两次点击），**拖出来源窗口**扔在地上
（冒险岛同款，堆叠整扔、已穿装备可从纸娃娃拖出）；页签/加点/技能升级仍为单击。
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import pygame

from game import settings
from game.systems.inventory import SLOT_ORDER, Item, islot_to_slot
from game.core.jobs import JOBS, job_chain, job_sp_group
from game.core.keybindings import ACTION_BY_ID, ACTIONS, display_key
from game.systems.quests import render_markup
from game.systems.scrolls import SCROLLS, apply_scroll, is_scroll_id
from game.core.stats import STAT_LABELS, wear_block

SLOT_NAMES = {
    "cap": "帽子", "face": "脸饰", "earr": "耳环", "top": "上衣",
    "overall": "连身衣", "pants": "裤子", "shoes": "鞋子",
    "glove": "手套", "cape": "披风", "ring": "戒指",
    "shield": "盾牌", "weapon": "武器",
}

CELL = 38          # 旧自绘面板用（fallback）
PAD = 10
DRAG_THRESHOLD = 6.0     # 按下后移动超过该像素才判定为「拖出扔东西」
DOUBLE_CLICK_TIME = 0.35  # 双击使用/穿戴的两次点击最大间隔（秒）

# ── 原版窗口几何（由 wz/UI.wz 底图逐像素实测）─────────────────────
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

# 技能：175×289；快捷栏：93×244（2 列 × 6 行）
SKL_BG = "Skill/backgrnd"
SKL_W, SKL_H = 175, 289
SKL_ROW_H = 40           # 技能列表每行高度
SKL_ROWS = 6             # 技能窗一屏可见行数（(SKL_H-49)//SKL_ROW_H）
SKL_ROWS_TAB = 5         # 带转数页签条时的一屏可见行数（页签占 header 下方一条）
SKL_TAB_H = 22           # 转数页签条高度
_SKL_ORD = ("一", "二", "三", "四", "五", "六")   # 转数中文序数
SHT_BG = "ShortCut/backgrnd"
SHT_W, SHT_H = 93, 244
SHT_CELL_X = [4, 48]
SHT_CELL_Y = [24, 58, 93, 127, 162, 196]
SHT_CELL_W, SHT_CELL_H = 41, 34

# 任务日志：UIWindow/Quest/backgrnd2（305×396）
QST_BG = "Quest/backgrnd2"
QST_W, QST_H = 305, 396
QST_HEAD_Y = 24          # 标题条下沿（可拖拽区）
QST_ROW_H = 26           # 每行任务条目高度

# 状态窗：UIWindow/Stat/backgrnd（175×337），标签全部烤死在底图内，
# 数值槽 x∈[58,170]；四维绿行右侧 12×12 为 BtApUp「+」按钮位。
STAT_BG = "Stat/backgrnd"
STAT_W, STAT_H = 175, 337
STAT_TEXT_X = 60                     # 数值文字左缘
STAT_ROW_Y = {"name": 33, "job": 52, "level": 69, "guild": 87,
              "hp": 105, "mp": 123, "exp": 141, "honor": 163}
STAT_AP_BOX = (63, 206, 25, 13)      # 「升级点数」白框
STAT_ROW = {"str": 235, "dex": 253, "int": 271, "luk": 289}
STAT_BT_X = 158                      # BtApUp x
STAT_AUTO_POS = (96, 300)            # BtAuto（73×35）左上角

# 页签（带原版汉字，宽 26~27 高 16）：游戏内 3 页 → 原版 装备/消耗/其他
TAB_INDEX = {"equip": 0, "consume": 1, "etc": 3}
TAB_LABEL = {"consume": "消耗", "equip": "装备", "etc": "其他"}

BAR_RESERVE = 58     # 底部状态栏预留高度（无 StatusBar 素材时同值）

# 按键设置窗（无专属原版素材，自绘风格与其它 fallback 一致）
KC_W = 240           # 窗宽
KC_ROW_H = 18        # 行高
KC_ROWS = 15         # 一屏可见条目数（含分组标题行）


def _panel(surface: pygame.Surface, rect: pygame.Rect,
           border=(90, 96, 110)) -> None:
    """fallback 自绘面板（素材缺失时用）。"""
    pygame.draw.rect(surface, (18, 22, 30, 216), rect, border_radius=8)
    pygame.draw.rect(surface, border, rect, 1, border_radius=8)


def _fit_icon(icon: pygame.Surface, size: int) -> pygame.Surface:
    if icon.get_width() > size or icon.get_height() > size:
        return pygame.transform.scale(icon, (size, size))
    return icon


class Panels:
    def __init__(self, ui, assets):
        self.ui = ui
        self.assets = assets
        self.inv_visible = False
        self.equip_visible = False
        self.skill_visible = False
        self.questlog_visible = False
        self.stat_visible = False
        self.keyconfig_visible = False
        self.bindings = None              # Game 注入：KeyBindings
        self._capture: Optional[str] = None   # 正在录入绑定的动作 id
        self.inv_tab = "consume"          # consume | equip | etc
        self._tooltip: Optional[str] = None
        self._toast: Optional[Tuple[str, float]] = None   # (文本, 剩余秒)
        self._inv_rect = pygame.Rect(0, 0, 0, 0)
        self._equip_rect = pygame.Rect(0, 0, 0, 0)
        self._skill_rect = pygame.Rect(0, 0, 0, 0)
        self._questlog_rect = pygame.Rect(0, 0, 0, 0)
        self._stat_rect = pygame.Rect(0, 0, 0, 0)
        self._kc_rect = pygame.Rect(0, 0, 0, 0)
        self._kc_rows: List[tuple] = []   # (Rect, action_id) 按键设置行热区
        self._kc_scroll = 0               # 按键设置首条目偏移
        self._ap_rects: List[tuple] = []     # (Rect, stat)
        self._auto_rect: Optional[pygame.Rect] = None
        self._num_cache: dict = {}           # (ch, color) → 染色后的像素数字
        self._quest_goal_lines = None    # Game 注入：qid → 目标行列表
        self.combat = None               # Game 注入：卷轴强化费 / 金币结算用
        self._cell_rects: List[tuple] = []   # (Rect, tab, index)
        self._slot_rects: List[tuple] = []   # (Rect, slot)
        self._skill_rows: List[tuple] = []   # (Rect, skill_id)
        self._tab_rects: List[tuple] = []    # (Rect, tab)
        self._inv_scroll: dict = {}          # tab → 背包当前页首格索引（滚轮滚动）
        self._skill_scroll = 0               # 技能窗当前首行索引（滚轮滚动）
        self._skill_tab: Optional[int] = None  # 技能窗当前 SP 职业组（None=最新一转）
        self._skill_tab_rects: List[tuple] = []  # (Rect, group) 技能窗转数页签
        self._skill_visible_rows = SKL_ROWS    # 技能窗当前一屏可见行数（绘制时定）
        # ── 拖拽 / 关闭 ─────────────────────────────────────────────
        self._win_pos: dict = {}             # key → (x, y) 用户拖动后的绝对位置
        self._win_size: dict = {}            # key → (w, h) 当前帧窗口尺寸
        self._view_size = (settings.VIEW_W, settings.VIEW_H)
        self._drag: Optional[Tuple[str, Tuple[int, int]]] = None  # (key, 抓取偏移)
        self._item_drag: Optional[dict] = None   # 拖出扔东西 {source, item, start, pos, active}
        self._last_click: Optional[Tuple[tuple, float]] = None   # (来源, 时刻) 双击检测
        self._close_rects: List[tuple] = []  # (Rect, key)
        self._title_rects: List[tuple] = []  # (Rect, key) 标题条=拖拽热区

    # ── 素材取值 ───────────────────────────────────────────────────
    def _wz(self, path: str, img: str = "UIWindow.img") -> Optional[pygame.Surface]:
        hit = self.assets.ui_surface(img, path)
        return hit[0] if hit else None

    # ── 开关 ───────────────────────────────────────────────────────
    def toggle_inventory(self) -> None:
        self.inv_visible = not self.inv_visible
        self.equip_visible = self.inv_visible
        if not self.inv_visible:
            self._drag = None
            self._item_drag = None

    def toggle_skill(self) -> None:
        self.skill_visible = not self.skill_visible
        if not self.skill_visible and self._drag and self._drag[0] == "skill":
            self._drag = None

    def toggle_quest_log(self) -> None:
        self.questlog_visible = not self.questlog_visible
        if not self.questlog_visible and self._drag and self._drag[0] == "questlog":
            self._drag = None

    def toggle_stat(self) -> None:
        self.stat_visible = not self.stat_visible
        if not self.stat_visible and self._drag and self._drag[0] == "stat":
            self._drag = None

    def attach_bindings(self, bindings) -> None:
        """Game 注入全局按键绑定表（改动经其实例路径即时写回文件）。"""
        self.bindings = bindings

    def toggle_keyconfig(self) -> None:
        self.keyconfig_visible = not self.keyconfig_visible
        self._capture = None
        self._kc_scroll = 0
        if not self.keyconfig_visible and self._drag and self._drag[0] == "keyconfig":
            self._drag = None

    @property
    def capturing_action(self) -> Optional[str]:
        """当前正在录入改绑的动作 id（None = 未录入）。"""
        return self._capture

    def consume_binding_key(self, key: int) -> bool:
        """录入态吞掉按键完成改绑（冲突自动互换）；Esc 取消。返回是否消费。"""
        if not self.keyconfig_visible or self._capture is None or self.bindings is None:
            return False
        if key != pygame.K_ESCAPE:
            self.bindings.set(self._capture, key)
            self.bindings.save()
        self._capture = None
        return True

    def _close_window(self, key: str) -> None:
        """关闭按钮：只关对应窗口（背包/装备栏互不牵连）。"""
        if key == "inv":
            self.inv_visible = False
        elif key == "equip":
            self.equip_visible = False
        elif key == "skill":
            self.skill_visible = False
        elif key == "questlog":
            self.questlog_visible = False
        elif key == "stat":
            self.stat_visible = False
        elif key == "keyconfig":
            self.keyconfig_visible = False
            self._capture = None
        if self._drag and self._drag[0] == key:
            self._drag = None
        if key in ("inv", "equip"):
            self._item_drag = None

    # ── 窗口定位（默认锚点 + 用户拖拽偏移）─────────────────────────
    def _resolve_pos(self, key: str, base: Tuple[int, int],
                     size: Tuple[int, int],
                     vw: int, vh: int) -> Tuple[int, int]:
        self._view_size = (vw, vh)
        self._win_size[key] = size
        x, y = self._win_pos.get(key, base)
        x = max(0, min(vw - size[0], int(x)))
        y = max(0, min(vh - size[1], int(y)))
        return x, y

    def _add_chrome(self, surface, key: str, x: int, y: int,
                    w: int, title_h: int) -> None:
        """登记标题拖拽热区并画右上角原版关闭按钮（BtUIClose 32×15）。"""
        self._title_rects.append((pygame.Rect(x, y, w, title_h), key))
        rect = pygame.Rect(x + w - 34, y + 3, 32, 15)
        img = None
        if self._drag and self._drag[0] == key:
            img = self._wz("BtUIClose/pressed/0")
        elif rect.collidepoint(pygame.mouse.get_pos()):
            img = self._wz("BtUIClose/mouseOver/0")
        if img is None:
            img = self._wz("BtUIClose/normal/0")
        if img is not None:
            surface.blit(img, rect.topleft)
        else:                       # 素材缺失 → 自绘红 × 小钮
            pygame.draw.rect(surface, (150, 52, 46), rect, border_radius=3)
            pygame.draw.line(surface, (255, 235, 235),
                             (rect.x + 11, rect.y + 4), (rect.x + 21, rect.y + 11), 2)
            pygame.draw.line(surface, (255, 235, 235),
                             (rect.x + 21, rect.y + 4), (rect.x + 11, rect.y + 11), 2)
        self._close_rects.append((rect, key))

    # ── 鼠标：按下 / 拖动 / 松开 ───────────────────────────────────
    def is_dragging(self) -> bool:
        return self._drag is not None or self._item_drag is not None

    def _item_at(self, pos: Tuple[int, int], player) -> Optional[Tuple[tuple, Item]]:
        """命中检测：返回 ((来源, ...), Item)；空格子 / 空栏位返回 None。"""
        inv = player.inventory
        if self.inv_visible:
            for rect, tab, idx in self._cell_rects:
                if rect.collidepoint(pos):
                    items = (list(inv.consumes.values()) if tab == "consume"
                             else list(inv.etcs.values()) if tab == "etc"
                             else list(inv.equips))
                    if idx < len(items):
                        return (("cell", tab, idx), items[idx])
                    return None
        if self.equip_visible:
            for rect, slot in self._slot_rects:
                if rect.collidepoint(pos):
                    item = inv.equipped.get(slot)
                    if item is not None:
                        return (("slot", slot), item)
                    return None
        return None

    def handle_mouse_down(self, pos: Tuple[int, int], player) -> bool:
        for rect, key in self._close_rects:
            if rect.collidepoint(pos):
                self._close_window(key)
                return True
        if self._drag is not None or self._item_drag is not None:
            return True
        for rect, key in self._title_rects:
            if rect.collidepoint(pos):
                self._drag = (key, (pos[0] - rect.x, pos[1] - rect.y))
                return True
        hit = self._item_at(pos, player)
        if hit is not None:
            self._item_drag = {"source": hit[0], "item": hit[1],
                               "start": pos, "pos": pos, "active": False}
            return True
        return self.handle_click(pos, player)

    def handle_mouse_motion(self, pos: Tuple[int, int]) -> None:
        if self._drag is not None:
            key, (gx, gy) = self._drag
            w, h = self._win_size.get(key, (60, 40))
            vw, vh = self._view_size
            x = max(0, min(vw - w, pos[0] - gx))
            y = max(0, min(vh - h, pos[1] - gy))
            self._win_pos[key] = (x, y)
        elif self._item_drag is not None:
            d = self._item_drag
            d["pos"] = pos
            if not d["active"]:
                dx = pos[0] - d["start"][0]
                dy = pos[1] - d["start"][1]
                if dx * dx + dy * dy > DRAG_THRESHOLD * DRAG_THRESHOLD:
                    d["active"] = True

    def handle_mouse_up(self, pos: Optional[Tuple[int, int]] = None,
                        player=None) -> Optional[Item]:
        """松开鼠标：拖出来源窗口 → 取出物品回传（扔出）；
        未拖动时同一格 0.35s 内两次点击 → 使用/穿戴/脱下。"""
        drag = self._item_drag
        self._item_drag = None
        self._drag = None
        if drag is None or player is None or pos is None:
            return None
        home = self._inv_rect if drag["source"][0] == "cell" else self._equip_rect
        if drag["active"]:
            if home.collidepoint(pos):
                return None      # 拖出去又放回来源窗口：取消
            return self._take_for_drop(drag, player)
        key = drag["source"]
        now = pygame.time.get_ticks() / 1000.0
        last = self._last_click
        is_double = (last is not None and last[0] == key
                     and now - last[1] <= DOUBLE_CLICK_TIME)
        self._last_click = None if is_double else (key, now)
        if is_double:
            self._use_or_equip(drag, player)
        return None

    def _use_or_equip(self, drag: dict, player) -> None:
        """双击行为：背包格 → 喝药/穿戴；纸娃娃栏位 → 脱下。"""
        src = drag["source"]
        if src[0] == "cell":
            self._click_cell(player, src[1], src[2])
        else:
            if player.inventory.unequip(src[1]):
                player.refresh_equips()
            else:
                self.flash("装备栏已满")

    def _take_for_drop(self, drag: dict, player) -> Optional[Item]:
        """确认扔出：从背包/装备栏取出该物品（堆叠整堆取出）。"""
        src, item = drag["source"], drag["item"]
        inv = player.inventory
        if src[0] == "cell":
            if src[1] == "equip":
                return inv.pop_equip(src[2])
            return inv.take_stack(item.id)
        got = inv.pop_equipped(src[1])
        if got is not None:
            player.refresh_equips()
        return got

    # ── 图标 ───────────────────────────────────────────────────────
    def _icon(self, item_id: str, kind: str) -> Optional[pygame.Surface]:
        if kind == "equip":
            return self.assets.equip_icon(item_id)
        return self.assets.item_icon(item_id)

    def handle_right_click(self, pos: Tuple[int, int], player) -> bool:
        """右键按键设置行 → 该动作恢复默认绑法（被顶用的动作链式归位）。"""
        if not self.keyconfig_visible or self.bindings is None:
            return False
        for rect, action in self._kc_rows:
            if rect.collidepoint(pos):
                self.bindings.reset(action)
                self.bindings.save()
                return True
        return False

    # ── 鼠标点击（返回 True 表示事件已消费）────────────────────────
    def handle_click(self, pos: Tuple[int, int], player) -> bool:
        if self.keyconfig_visible:
            for rect, action in self._kc_rows:
                if rect.collidepoint(pos):
                    if self.bindings is not None:
                        self._capture = None if self._capture == action else action
                    return True
            if self._kc_rect.collidepoint(pos):
                return True
        if self.inv_visible or self.equip_visible:
            for rect, key in self._tab_rects:
                if rect.collidepoint(pos):
                    self.inv_tab = key
                    return True
            # 物品格/栏位的点击与拖拽由 _item_drag 状态机处理（双击使用/穿戴）
            if self._inv_rect.collidepoint(pos) or self._equip_rect.collidepoint(pos):
                return True
        if self.skill_visible:
            for rect, grp in self._skill_tab_rects:
                if rect.collidepoint(pos):
                    self._skill_tab = grp
                    self._skill_scroll = 0
                    return True
            for rect, sid in self._skill_rows:
                if rect.collidepoint(pos):
                    player.skills.learn(sid, player.level)
                    return True
            if self._skill_rect.collidepoint(pos):
                return True
        if self.questlog_visible:
            if self._questlog_rect.collidepoint(pos):
                return True
        if self.stat_visible:
            for rect, st in self._ap_rects:
                if rect.collidepoint(pos):
                    if not player.allocate_ap(st):
                        self.flash("没有可分配的属性点")
                    return True
            if self._auto_rect is not None and self._auto_rect.collidepoint(pos):
                if not player.auto_allocate_ap():
                    self.flash("没有可分配的属性点")
                return True
            if self._stat_rect.collidepoint(pos):
                return True
        return False

    def handle_wheel(self, pos: Tuple[int, int], amount: int, player) -> bool:
        """滚轮滚动背包 / 技能窗口（仓库/商店各自处理，不在此列）。

        每格 amount 为 ±1（按钮 4=上滚，5=下滚）。滚动限幅到首末可见范围，
        背包按一整行（INV_COLS 格）移动，技能窗按一行移动。
        返回 True 表示事件已消费（避免穿透到下层窗口）。
        """
        if self.inv_visible and self._inv_rect.collidepoint(pos):
            tab = self.inv_tab
            items = self._inv_items(player)
            max_scroll = max(0, len(items) - INV_SLOTS)
            cur = self._inv_scroll.get(tab, 0)
            self._inv_scroll[tab] = max(0, min(max_scroll, cur + amount * INV_COLS))
            return True
        if self.skill_visible and self._skill_rect.collidepoint(pos):
            n = len(self._skill_view(player.skills)[2])
            vis = self._skill_visible_rows
            max_scroll = max(0, n - vis)
            self._skill_scroll = max(0, min(max_scroll,
                                            self._skill_scroll + amount))
            return True
        if self.keyconfig_visible and self._kc_rect.collidepoint(pos):
            n = len(self._kc_entries())
            max_scroll = max(0, n - KC_ROWS)
            self._kc_scroll = max(0, min(max_scroll, self._kc_scroll + amount))
            return True
        return False

    def _inv_items(self, player) -> list:
        """当前页签对应的背包物品列表（与绘制/点击使用同一顺序）。"""
        inv = player.inventory
        tab = self.inv_tab
        if tab == "consume":
            return list(inv.consumes.values())
        if tab == "etc":
            return list(inv.etcs.values())
        return list(inv.equips)

    def _click_cell(self, player, tab: str, idx: int) -> None:
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
                self.flash(f"无法穿戴 {items[idx].name}")
            elif idx < len(items):
                block = wear_block(items[idx].info, player.level,
                                   player.total_stats())
                if block is not None:
                    self.flash(f"无法穿戴：{block}")
                elif inv.equip(idx):
                    player.refresh_equips()
                else:
                    self.flash("装备栏已满")

    def _apply_scroll(self, scroll_item: Item, player) -> None:
        """双击卷轴：对当前武器使用（扣强化费，成功/失败各耗一次次数）。"""
        scroll = SCROLLS.get(scroll_item.id)
        if scroll is None:
            self.flash("无法使用的卷轴")
            return
        target = player.inventory.equipped.get(scroll["slot"])
        if target is None:
            self.flash("请先装备目标装备")
            return
        combat = self.combat
        meso = combat.meso if combat is not None else 0
        result = apply_scroll(scroll, target, random.Random(),
                              level=player.level, meso=meso)
        if result is None:
            self.flash("无法强化：栏位不符或强化次数已用完")
            return
        if not result["charged"]:
            self.flash(result["msg"])
            return
        if combat is not None:
            combat.meso = result["meso"]
        player.inventory.use_consume(scroll_item.id)
        player.refresh_equips()
        self.flash(result["msg"])

    def flash(self, text: str, duration: float = 1.6) -> None:
        """顶部居中短暂提示（如无法穿戴 / 背包已满）。"""
        self._toast = (text, duration)

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface, player, meso: int = 0) -> None:
        self._tooltip = None
        self._cell_rects.clear()
        self._slot_rects.clear()
        self._skill_rows.clear()
        self._skill_tab_rects.clear()
        self._tab_rects.clear()
        self._close_rects.clear()
        self._title_rects.clear()
        self._ap_rects.clear()
        self._kc_rows.clear()
        self._auto_rect = None
        mouse = pygame.mouse.get_pos()
        if self.inv_visible:
            self._draw_inventory(surface, player, meso)
        if self.equip_visible:
            self._draw_equip(surface, player)
        if self.skill_visible:
            self._draw_skills(surface, player)
        if self.questlog_visible:
            self._draw_questlog(surface, player)
        if self.stat_visible:
            self._draw_stat(surface, player)
        if self.keyconfig_visible:
            self._draw_keyconfig(surface, player)
        if self._tooltip is not None:
            self._draw_tooltip(surface, mouse)
        # 拖拽中的物品图标跟手（画在最上层，窗口之外也可见）
        if self._item_drag is not None and self._item_drag["active"]:
            it = self._item_drag["item"]
            icon = self._icon(it.id, it.kind)
            if icon is not None:
                icon = _fit_icon(icon, 32)
                px, py = self._item_drag["pos"]
                surface.blit(icon, (px - icon.get_width() // 2,
                                    py - icon.get_height() // 2))
        # 顶部提示
        if self._toast is not None:
            text, remain = self._toast
            remain -= 1 / 60
            if remain <= 0:
                self._toast = None
            else:
                self._toast = (text, remain)
                self._draw_toast(surface, text)

    def _draw_toast(self, surface, text: str) -> None:
        f = self.ui.font
        txt = f.render(text, True, (255, 230, 150))
        w, h = txt.get_width() + 20, 24
        x = (surface.get_width() - w) // 2
        plate = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(plate, (20, 16, 10, 200), (0, 0, w, h), border_radius=6)
        pygame.draw.rect(plate, (150, 130, 90), (0, 0, w, h), 1, border_radius=6)
        plate.blit(txt, (10, (h - txt.get_height()) // 2))
        surface.blit(plate, (x, 34))

    # ── 背包窗口（UIWindow/Item）───────────────────────────────────
    def _draw_inventory(self, surface, player, meso: int) -> None:
        inv = player.inventory
        f, fs = self.ui.font, self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        bg = self._wz(INV_BG)
        tab = self.inv_tab
        base = (4, vh - INV_H - BAR_RESERVE - 2)
        x, y = self._resolve_pos("inv", base, (INV_W, INV_H), vw, vh)
        rect = pygame.Rect(x, y, INV_W, INV_H)
        self._inv_rect = rect

        items = (list(inv.consumes.values()) if tab == "consume"
                 else list(inv.etcs.values()) if tab == "etc"
                 else list(inv.equips))

        if bg is None:      # 素材缺失 → 旧自绘
            self._draw_inventory_fallback(surface, player, meso)
            return
        surface.blit(bg, (x, y))
        self._add_chrome(surface, "inv", x, y, INV_W, 23)

        # 页签条（底图 y23~42 空带；原版汉字烤死在图内）：选中=enabled
        tx = x + 4
        for key in ("consume", "equip", "etc"):
            ti = TAB_INDEX[key]
            state = "enabled" if key == tab else "disabled"
            img = self._wz(f"Item/Tab/{state}/{ti}")
            if img is not None:
                surface.blit(img, (tx, y + 25))
                self._tab_rects.append(
                    (pygame.Rect(tx, y + 25, img.get_width(), img.get_height()), key))
                tx += img.get_width() + 1
            else:
                tr = pygame.Rect(tx, y + 25, 30, 16)
                pygame.draw.rect(surface, (60, 70, 88) if key == tab else (34, 40, 52),
                                 tr, border_radius=4)
                surface.blit(fs.render(TAB_LABEL[key], True, (255, 255, 255)),
                             (tr.x + 2, tr.y + 2))
                self._tab_rects.append((tr, key))
                tx += 31

        # 标题行右侧：当前页数量（浅色标题条 → 深字）
        cap_txt = fs.render(str(len(items)) + "项", True, (70, 72, 86))
        surface.blit(cap_txt, (x + INV_W - cap_txt.get_width() - 40, y + 6))

        # 物品格（底图已含格子，只叠图标 + 数量）
        # 超过 24 种物品时按滚轮滚动：scroll 为当前页首格索引（对齐每行 INV_COLS 格）
        max_scroll = max(0, len(items) - INV_SLOTS)
        base = self._inv_scroll.get(tab, 0)
        base = max(0, min(max_scroll, base))
        for i in range(INV_SLOTS):
            idx = base + i
            cx = x + INV_CELL_X[i % INV_COLS]
            cy = y + INV_CELL_Y[i // INV_COLS]
            cell = pygame.Rect(cx, cy, INV_CELL_W, INV_CELL_H)
            if idx < len(items):
                item = items[idx]
                icon = self._icon(item.id, item.kind)
                if icon is not None:
                    icon = _fit_icon(icon, 32)
                    surface.blit(icon, (cx + (cell.w - icon.get_width()) // 2,
                                        cy + (cell.h - icon.get_height()) // 2))
                if item.count > 1:
                    cnt = fs.render(str(item.count), True, (255, 255, 255))
                    shadow = fs.render(str(item.count), True, (0, 0, 0))
                    surface.blit(shadow, (cell.right - cnt.get_width() - 1,
                                          cell.bottom - cnt.get_height() + 1))
                    surface.blit(cnt, (cell.right - cnt.get_width() - 2,
                                       cell.bottom - cnt.get_height()))
                if cell.collidepoint(pygame.mouse.get_pos()):
                    self._tooltip = self._item_tip(item)
            self._cell_rects.append((cell, tab, idx))

        # 底部页脚：上行 = 金币图标 + 持有数（白底板 → 深棕字）
        coin = self._wz("Item/BtCoin/normal/0")
        if coin is not None:
            surface.blit(coin, (x + 10, y + 266))
        surface.blit(fs.render(f"金币 {meso:,}", True, (110, 68, 18)),
                     (x + 28, y + 265))

    def _draw_inventory_fallback(self, surface, player, meso: int) -> None:
        inv = player.inventory
        f, fs = self.ui.font, self.ui.font_small
        vh = surface.get_height()
        tab = self.inv_tab
        items = (list(inv.consumes.values()) if tab == "consume"
                 else list(inv.etcs.values()) if tab == "etc"
                 else list(inv.equips))
        cols = 6
        rows = max(2, (max(len(items), 8) + cols - 1) // cols)
        w = PAD * 2 + cols * CELL
        h = 58 + rows * CELL
        base = (12, vh - 150 - h)
        x, y = self._resolve_pos("inv", base, (w, h), surface.get_width(), vh)
        rect = pygame.Rect(x, y, w, h)
        self._inv_rect = rect
        _panel(surface, rect)
        surface.blit(f.render("道具栏 (I)", True, (235, 235, 240)), (x + PAD, y + 8))
        meso_txt = f.render(f"{meso} 枫币", True, (255, 220, 90))
        surface.blit(meso_txt, (x + w - PAD - 34 - meso_txt.get_width(), y + 8))
        self._add_chrome(surface, "inv", x, y, w, 24)
        for i, (key, label) in enumerate((("consume", "消耗"), ("equip", "装备"),
                                          ("etc", "其他"))):
            tr = pygame.Rect(x + PAD + i * 58, y + 28, 54, 18)
            on = key == tab
            pygame.draw.rect(surface, (60, 70, 88) if on else (34, 40, 52),
                             tr, border_radius=4)
            surface.blit(fs.render(label, True, (255, 255, 255)),
                         (tr.x + (tr.w - fs.size(label)[0]) // 2, tr.y + 3))
            self._tab_rects.append((tr, key))
        # 超 24 种时滚动：scroll 为当前页首格索引（沿用 INV_SLOTS 一屏容量）
        max_scroll = max(0, len(items) - INV_SLOTS)
        local_scroll = max(0, min(max_scroll, self._inv_scroll.get(tab, 0)))
        for i in range(cols * rows):
            idx = local_scroll + i
            cx = x + PAD + (i % cols) * CELL
            cy = y + 52 + (i // cols) * CELL
            cell = pygame.Rect(cx, cy, CELL - 4, CELL - 4)
            pygame.draw.rect(surface, (40, 46, 60), cell, border_radius=4)
            if idx < len(items):
                item = items[idx]
                icon = self._icon(item.id, item.kind)
                if icon is not None:
                    icon = _fit_icon(icon, 32)
                    surface.blit(icon, (cx + (cell.w - icon.get_width()) // 2,
                                        cy + (cell.h - icon.get_height()) // 2))
                if item.count > 1:
                    cnt = fs.render(str(item.count), True, (255, 255, 255))
                    surface.blit(cnt, (cell.right - cnt.get_width() - 2,
                                       cell.bottom - cnt.get_height() + 1))
                if cell.collidepoint(pygame.mouse.get_pos()):
                    self._tooltip = self._item_tip(item)
            self._cell_rects.append((cell, tab, idx))

    # ── 装备栏窗口（UIWindow/Equip 纸娃娃底板）─────────────────────
    def _draw_equip(self, surface, player) -> None:
        inv = player.inventory
        fs = self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        # 默认锚在背包默认位置右侧（不随背包拖动，两窗口各自独立）
        base = (4 + INV_W + 2,
                vh - INV_H - BAR_RESERVE - 2 + (INV_H - EQP_H) // 2)
        x, y = self._resolve_pos("equip", base, (EQP_W, EQP_H), vw, vh)
        rect = pygame.Rect(x, y, EQP_W, EQP_H)
        self._equip_rect = rect
        bg = self._wz(EQP_BG)
        if bg is None:
            self._draw_equip_fallback(surface, player)
            return
        surface.blit(bg, (x, y))
        self._add_chrome(surface, "equip", x, y, EQP_W, 30)

        for slot in SLOT_ORDER:
            pos = EQP_SLOT_POS.get(slot)
            if pos is None:
                continue
            cx = x + EQP_CELL_X[pos[0]]
            cy = y + EQP_CELL_Y[pos[1]]
            cell = pygame.Rect(cx, cy, EQP_CELL_W, EQP_CELL_H)
            item = inv.equipped.get(slot)
            if item is not None:
                icon = self._icon(item.id, item.kind)
                if icon is not None:
                    icon = _fit_icon(icon, 32)
                    surface.blit(icon, (cx + (cell.w - icon.get_width()) // 2,
                                        cy + (cell.h - icon.get_height()) // 2))
                if cell.collidepoint(pygame.mouse.get_pos()):
                    self._tooltip = self._item_tip(item)
            self._slot_rects.append((cell, slot))

        # 标题条右侧：职业 + 攻/防摘要（浅色条 → 深字）
        job_name = JOBS.get(player.job).name if player.job in JOBS else ""
        stat = fs.render(
            f"{job_name}  攻 {player.attack_value()} 防 {player.defense_value()}",
            True, (70, 72, 86))
        surface.blit(stat, (x + EQP_W - stat.get_width() - 40, y + 6))

    def _draw_equip_fallback(self, surface, player) -> None:
        inv = player.inventory
        f, fs = self.ui.font, self.ui.font_small
        inv_rect = self._inv_rect
        vw = surface.get_width()
        w = 158
        h = inv_rect.h
        base = (inv_rect.right + 10, inv_rect.y)
        x, y = self._resolve_pos("equip", base, (w, h), vw, surface.get_height())
        rect = pygame.Rect(x, y, w, h)
        self._equip_rect = rect
        _panel(surface, rect)
        surface.blit(f.render("装备栏", True, (235, 235, 240)), (x + PAD, y + 8))
        stat = fs.render(
            f"攻 {player.attack_value()} 防 {player.defense_value()} "
            f"SP {player.skills.total_sp}", True, (150, 210, 160))
        surface.blit(stat, (x + w - PAD - 34 - stat.get_width(), y + 9))
        self._add_chrome(surface, "equip", x, y, w, 24)
        for i, slot in enumerate(SLOT_ORDER):
            cx = x + PAD + (i % 2) * 70
            cy = y + 32 + (i // 2) * (CELL + 2)
            if cy + CELL > rect.bottom - 6:
                break
            cell = pygame.Rect(cx, cy, 64, CELL - 4)
            pygame.draw.rect(surface, (40, 46, 60), cell, border_radius=4)
            label = fs.render(SLOT_NAMES.get(slot, slot), True, (130, 138, 152))
            surface.blit(label, (cx + 4, cy + 2))
            item = inv.equipped.get(slot)
            if item is not None:
                icon = self._icon(item.id, item.kind)
                if icon is not None:
                    icon = _fit_icon(icon, 22)
                    surface.blit(icon, (cx + cell.w - icon.get_width() - 3,
                                        cy + cell.h - icon.get_height() - 3))
                if cell.collidepoint(pygame.mouse.get_pos()):
                    self._tooltip = self._item_tip(item)
            self._slot_rects.append((cell, slot))

    # ── 技能窗口（UIWindow/Skill 底板）─────────────────────────────
    def _hotkey_of(self, book, sid: str) -> Optional[int]:
        return next((k for k, v in book.hotkeys.items() if v == sid), None)

    def _skill_tip(self, book, d, lv: int, mouse, row: pygame.Rect) -> None:
        """悬停技能行时把描述/伤害/快捷键放进深色 Tooltip，避免行内文字溢出。"""
        if self._tooltip is not None or not row.collidepoint(mouse):
            return
        lines = [d.name]
        if d.desc:
            lines.append(d.desc)
        if lv > 0:
            lines.append(f"伤害 {d.stat(lv, 'damage', 100)}% · 消耗 MP{d.stat(lv, 'mpCon', 0)}")
            key = self._hotkey_of(book, d.id)
            if key:
                lines.append(f"快捷键 {key}")
        else:
            need = d.char_level or 1
            lines.append(f"Lv{need} 可学习")
        self._tooltip = "\n".join(lines)

    def _skill_view(self, book):
        """技能窗当前视图：(页签[(group,label)], 选中 group, 该栏技能 id 列表)。

        页签按职业链旧→新排（一转/二转/三转）；选中栏默认为最新一转，或用户
        点选后记住的 group。列表含该转全部技能（自动满级的被动也列出）。
        """
        tabs = [(job_sp_group(jd.code), _SKL_ORD[i] + "转")
                for i, jd in enumerate(job_chain(book.job)) if i < len(_SKL_ORD)]
        groups = [g for g, _ in tabs]
        active = self._skill_tab if self._skill_tab in groups else (
            groups[-1] if groups else job_sp_group(book.job))
        sids = book.skills_for_group(active) if groups else []
        return tabs, active, sids

    def _draw_skill_tabs(self, surface, x, strip_y, w, tabs, active) -> None:
        """画转数页签条并登记热区；单页（含无页）不画、直接返回。"""
        if len(tabs) <= 1:
            return
        fs = self.ui.font_small
        n = len(tabs)
        tw = max(20, (w - 12) // n)
        for i, (grp, label) in enumerate(tabs):
            r = pygame.Rect(x + 6 + i * tw, strip_y, tw - 2, SKL_TAB_H - 4)
            sel = grp == active
            pygame.draw.rect(surface, (70, 96, 132) if sel else (38, 42, 54),
                             r, border_radius=4)
            if sel:
                pygame.draw.rect(surface, (150, 190, 235), r, 1, border_radius=4)
            t = fs.render(label, True, (245, 245, 250) if sel else (150, 156, 172))
            surface.blit(t, (r.x + (r.w - t.get_width()) // 2,
                             r.y + (r.h - t.get_height()) // 2))
            self._skill_tab_rects.append((r, grp))

    def _draw_skills(self, surface, player) -> None:
        book = player.skills
        f, ft = self.ui.font, self.ui.font_tiny
        vw, vh = surface.get_width(), surface.get_height()
        tabs, active, sids = self._skill_view(book)
        learn_set = set(book.learnable(active))
        sp_group = book.sp_for_group(active)
        bg = self._wz(SKL_BG)
        base = (vw - 4 - SHT_W - 6 - SKL_W, vh - SKL_H - BAR_RESERVE - 2)
        x, y = self._resolve_pos("skill", base, (SKL_W, SKL_H), vw, vh)
        rect = pygame.Rect(x, y, SKL_W, SKL_H)
        self._skill_rect = rect
        if bg is None:
            self._draw_skills_fallback(surface, player)
            return
        surface.blit(bg, (x, y))
        self._add_chrome(surface, "skill", x, y, SKL_W, 44)
        # SP（本转结余，浅色标题条右侧 → 深字）
        sp = ft.render(f"SP {sp_group}", True,
                       (150, 90, 20) if sp_group > 0 else (110, 112, 124))
        surface.blit(sp, (x + 100, y + 7))
        multi = len(tabs) > 1
        if multi:
            self._draw_skill_tabs(surface, x, y + 44, SKL_W, tabs, active)
        list_top = y + (44 + SKL_TAB_H if multi else 49)
        vis_rows = SKL_ROWS_TAB if multi else SKL_ROWS
        self._skill_visible_rows = vis_rows

        sp_btn = self._wz("Skill/BtSpUp/normal/0")

        # 技能列表：逐行使用 Skill/skill0(已知)/skill1(未学) 原版行背景，
        # 全宽铺开以盖住 backgrnd 里烤死的深色高亮条，避免文字与底色重叠。
        row_h = SKL_ROW_H
        row_w = SKL_W - 12
        row_x = x + 6
        row_img_h = 38
        mouse = pygame.mouse.get_pos()
        max_rows = max(0, len(sids) - vis_rows)
        start = max(0, min(max_rows, self._skill_scroll))
        for i, sid in enumerate(sids[start:start + vis_rows]):
            d = book.defs.get(sid)
            if d is None:
                continue
            lv = book.levels.get(sid, 0)
            ry = list_top + i * row_h
            locked = lv == 0
            row_img = self._wz("Skill/skill1" if locked else "Skill/skill0")
            if row_img is not None:
                surface.blit(pygame.transform.scale(row_img, (row_w, row_img_h)),
                             (row_x, ry))
            icon = self.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (28, 28)),
                             (row_x + 3, ry + 3))
            color = (150, 156, 172) if locked else (46, 38, 32)
            tx = row_x + 46
            name_w = row_x + row_w - tx - 8
            name_txt = _ellipsize(f"{d.name} Lv{lv}/{d.max_level}", ft, name_w)
            surface.blit(ft.render(name_txt, True, color), (tx, ry + 5))
            if lv > 0:
                dmg = d.stat(lv, "damage", 100)
                mp = d.stat(lv, "mpCon", 0)
                surface.blit(ft.render(f"{dmg}%  MP{mp}", True, (40, 90, 46)),
                             (tx, ry + 20))
            else:
                surface.blit(ft.render(f"Lv{d.char_level or 1} 可学习", True, color),
                             (tx, ry + 20))
            self._skill_tip(book, d, lv, mouse, pygame.Rect(row_x, ry, row_w, row_img_h))
            # 升级按钮（原版 BtSpUp）：仅可手学的主动技能、本转有 SP 且未满级
            if sp_group > 0 and lv < d.max_level and sid in learn_set:
                btn = pygame.Rect(row_x + row_w - 20, ry + 3,
                                  sp_btn.get_width() if sp_btn else 12,
                                  sp_btn.get_height() if sp_btn else 12)
                if sp_btn is not None:
                    surface.blit(sp_btn, btn.topleft)
                else:
                    pygame.draw.rect(surface, (70, 130, 90), btn, border_radius=4)
                    surface.blit(f.render("+", True, (255, 255, 255)),
                                 (btn.x + 3, btn.y))
                self._skill_rows.append((btn.inflate(6, 6), sid))

    def _draw_skills_fallback(self, surface, player) -> None:
        book = player.skills
        f, fs = self.ui.font, self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        tabs, active, sids = self._skill_view(book)
        learn_set = set(book.learnable(active))
        sp_group = book.sp_for_group(active)
        multi = len(tabs) > 1
        tab_band = SKL_TAB_H if multi else 0
        sp_h = 52
        vis_rows = max(1, min(len(sids), (vh - 150 - 58 - tab_band) // sp_h))
        self._skill_visible_rows = vis_rows
        w = 330
        h = 46 + tab_band + vis_rows * sp_h + 8
        base = (vw - w - 12, vh - 150 - h)
        x, y = self._resolve_pos("skill", base, (w, h), vw, vh)
        rect = pygame.Rect(x, y, w, h)
        self._skill_rect = rect
        _panel(surface, rect)
        surface.blit(f.render("技能栏 (K)", True, (235, 235, 240)), (x + PAD, y + 8))
        sp = f.render(f"SP {sp_group}", True,
                      (255, 220, 90) if sp_group > 0 else (140, 146, 160))
        surface.blit(sp, (x + w - PAD - 34 - sp.get_width(), y + 8))
        self._add_chrome(surface, "skill", x, y, w, 24)
        if multi:
            self._draw_skill_tabs(surface, x, y + 28, w, tabs, active)
        list_top = y + 40 + tab_band
        mouse = pygame.mouse.get_pos()
        max_rows = max(0, len(sids) - vis_rows)
        start = max(0, min(max_rows, self._skill_scroll))
        for i, sid in enumerate(sids[start:start + vis_rows]):
            d = book.defs.get(sid)
            if d is None:
                continue
            lv = book.levels.get(sid, 0)
            ry = list_top + i * sp_h
            row = pygame.Rect(x + PAD, ry, w - PAD * 2, 48)
            pygame.draw.rect(surface, (40, 46, 60), row, border_radius=4)
            icon = self.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (32, 32)),
                             (row.x + 6, ry + 8))
            locked = lv == 0
            color = (140, 146, 160) if locked else (235, 235, 240)
            key = self._hotkey_of(book, sid)
            keytxt = f"  [{key}]" if key and lv > 0 else ""
            name_txt = _ellipsize(f"{d.name} Lv{lv}/{d.max_level}{keytxt}", f,
                                  row.right - (row.x + 52) - 6)
            surface.blit(f.render(name_txt, True, color), (row.x + 52, ry + 6))
            if lv > 0:
                dmg = d.stat(lv, "damage", 100)
                mp = d.stat(lv, "mpCon", 0)
                info = fs.render(f"{dmg}% MP{mp}", True, (150, 210, 160))
                surface.blit(info, (row.x + 52, ry + 28))
            else:
                surface.blit(fs.render(f"Lv{d.char_level or 1} 可学习",
                                       True, (150, 156, 170)), (row.x + 52, ry + 28))
            self._skill_tip(book, d, lv, mouse, row)
            if sp_group > 0 and lv < d.max_level and sid in learn_set:
                btn = pygame.Rect(row.right - 26, ry + 4, 22, 22)
                pygame.draw.rect(surface, (70, 130, 90), btn, border_radius=4)
                surface.blit(f.render("+", True, (255, 255, 255)),
                             (btn.x + 7, btn.y + 1))
                self._skill_rows.append((btn, sid))

    # ── 任务日志窗口（UIWindow/Quest 底板）────────────────────────
    def _wrap_text(self, text: str, width: int, font) -> List[str]:
        """脱标签后按宽度折行（允许 \\n 分段），确保不溢出面板边界。"""
        cleaned = render_markup(text,
                                map_name=self.assets.map_name_of,
                                npc_name=self.assets.npc_name,
                                item_name=self.assets.item_name,
                                mob_name=self.assets.mob_name_of)
        lines: List[str] = []
        for seg in cleaned.split("\n"):
            lines.extend(self.ui._wrap(seg, width, font))
        return lines or [""]

    def _draw_questlog(self, surface, player) -> None:
        f, fs = self.ui.font, self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        bg = self._wz(QST_BG)
        base = (vw - QST_W - 4, vh - QST_H - BAR_RESERVE - 2)
        x, y = self._resolve_pos("questlog", base, (QST_W, QST_H), vw, vh)
        rect = pygame.Rect(x, y, QST_W, QST_H)
        self._questlog_rect = rect
        if bg is not None:
            surface.blit(bg, (x, y))
        else:
            _panel(surface, rect)
        self._add_chrome(surface, "questlog", x, y, QST_W, 24)

        quests = player.quests
        # 收集进行中任务（保持接取顺序）
        active = [qid for qid in quests.accepted_order
                  if quests.is_accepted(qid)]

        # 标题（backgrnd2 为浅底，文字用深色）
        surface.blit(f.render("任务日志 (Q)", True, (60, 52, 44)),
                     (x + 12, y + 4))
        count = fs.render(f"进行中 {len(active)}", True, (120, 108, 92))
        surface.blit(count, (x + QST_W - count.get_width() - 40, y + 7))

        if not active:
            empty = fs.render("目前没有进行中的任务", True, (120, 108, 92))
            surface.blit(empty, (x + 20, y + 60))
            return

        ty = y + 40
        # 面板可用文字宽度（左右留白，右端避开滚动条位）
        quest_wrap = QST_W - 18 - 30
        for qid in active:
            d = quests.defs.get(qid)
            if d is None:
                continue
            # 任务名（含标记，先脱标签再折行）
            name_lines = self._wrap_text(d.name, quest_wrap, fs)
            if ty + QST_ROW_H * 3 > y + QST_H - 10:
                break
            for ln in name_lines:
                surface.blit(fs.render(ln, True, (60, 52, 44)), (x + 18, ty))
                ty += 20
            # 目标 NPC（优先交付 NPC，无则用接取 NPC）
            npc_id = d.end_npc if d.end_npc is not None else d.start_npc
            if npc_id is not None:
                npc_txt = fs.render(f"目标 NPC：{self.assets.npc_name(str(npc_id))}",
                                    True, (140, 110, 60))
                surface.blit(npc_txt, (x + 30, ty))
                ty += 16
            # 目标行
            if self._quest_goal_lines is not None:
                for line in self._quest_goal_lines(qid):
                    for ln in self._wrap_text(line, quest_wrap, fs):
                        if ty > y + QST_H - 12:
                            break
                        surface.blit(fs.render(ln, True, (90, 82, 70)),
                                     (x + 30, ty))
                        ty += 16
            ty += 8

    # ── 状态窗（UIWindow/Stat/backgrnd，B 键）────────────────────────
    def _num_glyph(self, ch: str, color) -> Optional[pygame.Surface]:
        """StatusBar/number 像素数字（白字 → 染色），缓存。"""
        key = (ch, color)
        hit = self._num_cache.get(key)
        if hit is not None:
            return hit
        path = "number/slash" if ch == "/" else f"number/{ch}"
        src = self._wz(path, img="StatusBar.img")
        if src is None:
            return None
        tinted = src.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self._num_cache[key] = tinted
        return tinted

    def _num_width(self, text: str, color) -> Optional[int]:
        """像素数字串总宽；含不可绘制字符时返回 None（调用方回退字体）。"""
        w = 0
        for ch in text:
            img = self._num_glyph(ch, color) if (ch.isdigit() or ch == "/") else None
            if img is None:
                return None
            w += img.get_width() + 1
        return w

    def _draw_numline(self, surface, text: str, x: int, y_mid: int,
                      color=(60, 60, 60)) -> Optional[int]:
        """用原版像素数字画一串数字（垂直居中于 y_mid），返回结束 x。"""
        w = self._num_width(text, color)
        if w is None:
            return None
        for ch in text:
            img = self._num_glyph(ch, color)
            surface.blit(img, (x, y_mid - img.get_height() // 2))
            x += img.get_width() + 1
        return x

    def _stat_value(self, surface, fs, text: str, x: int, y_band: int) -> None:
        """数值槽文本：纯数字串用原版像素数字，否则回退小字体。"""
        end = self._draw_numline(surface, text, x, y_band + 7)
        if end is None:
            surface.blit(fs.render(text, True, (40, 40, 40)), (x, y_band + 2))

    def _draw_stat(self, surface, player) -> None:
        fs = self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        bg = self._wz(STAT_BG)
        base = (vw - STAT_W - 4, 140)
        if bg is None:
            self._draw_stat_fallback(surface, player)
            return
        x, y = self._resolve_pos("stat", base, (STAT_W, STAT_H), vw, vh)
        self._stat_rect = pygame.Rect(x, y, STAT_W, STAT_H)
        surface.blit(bg, (x, y))
        self._add_chrome(surface, "stat", x, y, STAT_W, 20)
        mouse = pygame.mouse.get_pos()
        total = player.total_stats()
        jobdef = JOBS.get(player.job) or JOBS[0]

        def row(key: str, text: str) -> None:
            surface.blit(fs.render(text, True, (40, 40, 40)),
                         (x + STAT_TEXT_X, y + STAT_ROW_Y[key] + 2))

        def num(key: str, text: str) -> None:
            self._stat_value(surface, fs, text, x + STAT_TEXT_X,
                             y + STAT_ROW_Y[key])

        row("name", "玩家")
        row("job", jobdef.name)
        num("level", str(player.level))
        num("hp", f"{int(player.hp)}/{player.max_hp}")
        num("mp", f"{int(player.mp)}/{player.max_mp}")
        num("exp", f"{player.exp}/{player.exp_to_next()}")
        bx, by, bw, bh = STAT_AP_BOX
        ap_txt = str(player.ap)
        ap_w = self._num_width(ap_txt, (60, 60, 60))
        if ap_w is not None:
            self._draw_numline(surface, ap_txt, x + bx + (bw - ap_w) // 2,
                               y + by + bh // 2)
        else:
            t = fs.render(ap_txt, True, (40, 40, 40))
            surface.blit(t, (x + bx + (bw - t.get_width()) // 2,
                             y + by + (bh - t.get_height()) // 2))
        for st, ry in STAT_ROW.items():
            bonus = player.inventory.bonus(st)
            end = self._draw_numline(surface, str(total[st]),
                                     x + STAT_TEXT_X, y + ry + 7)
            if end is None:
                surface.blit(fs.render(str(total[st]), True, (40, 40, 40)),
                             (x + STAT_TEXT_X, y + ry + 2))
                end = x + STAT_TEXT_X + fs.size(str(total[st]))[0]
            if bonus:
                surface.blit(fs.render(f" (+{bonus})", True, (46, 120, 40)),
                             (end + 2, y + ry + 2))
            rect = pygame.Rect(x + STAT_BT_X, y + ry, 12, 12)
            self._ap_rects.append((rect, st))
            state = ("disabled" if player.ap <= 0 else
                     "mouseOver" if rect.collidepoint(mouse) else "normal")
            img = self._wz(f"Stat/BtApUp/{state}/0")
            if img is not None:
                surface.blit(img, rect.topleft)
        rect = pygame.Rect(x + STAT_AUTO_POS[0], y + STAT_AUTO_POS[1], 73, 35)
        self._auto_rect = rect
        state = "mouseOver" if rect.collidepoint(mouse) else "normal"
        img = self._wz(f"Stat/BtAuto/{state}/0")
        if img is not None:
            surface.blit(img, rect.topleft)

    def _draw_stat_fallback(self, surface, player) -> None:
        """素材缺失时的自绘状态窗（含加点按钮热区）。"""
        fs = self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        w, h = 210, 250
        x, y = self._resolve_pos("stat", (vw - w - 8, 60), (w, h), vw, vh)
        rect = pygame.Rect(x, y, w, h)
        self._stat_rect = rect
        _panel(surface, rect)
        self._add_chrome(surface, "stat", x, y, w, 24)
        mouse = pygame.mouse.get_pos()
        total = player.total_stats()
        jobdef = JOBS.get(player.job) or JOBS[0]
        lines = [f"职业：{jobdef.name}    等级：{player.level}",
                 f"HP {int(player.hp)}/{player.max_hp}   "
                 f"MP {int(player.mp)}/{player.max_mp}",
                 f"经验 {player.exp}/{player.exp_to_next()}",
                 f"属性点：{player.ap}"]
        ty = y + 30
        for line in lines:
            surface.blit(fs.render(line, True, (230, 225, 210)), (x + 10, ty))
            ty += 20
        for st in ("str", "dex", "int", "luk"):
            bonus = player.inventory.bonus(st)
            txt = f"{STAT_LABELS[st]} {total[st]}" + (f" (+{bonus})" if bonus else "")
            surface.blit(fs.render(txt, True, (230, 225, 210)), (x + 10, ty))
            btn = pygame.Rect(x + w - 26, ty - 2, 16, 16)
            self._ap_rects.append((btn, st))
            color = (90, 96, 110) if player.ap <= 0 else (150, 190, 150)
            pygame.draw.rect(surface, color, btn, border_radius=3)
            pygame.draw.line(surface, (250, 250, 250),
                             (btn.x + 8, btn.y + 3), (btn.x + 8, btn.y + 13), 2)
            pygame.draw.line(surface, (250, 250, 250),
                             (btn.x + 3, btn.y + 8), (btn.x + 13, btn.y + 8), 2)
            ty += 24
        abtn = pygame.Rect(x + w - 70, y + h - 30, 60, 22)
        self._auto_rect = abtn
        pygame.draw.rect(surface, (110, 130, 160), abtn, border_radius=4)
        at = fs.render("自动", True, (240, 240, 240))
        surface.blit(at, (abtn.x + (abtn.w - at.get_width()) // 2,
                          abtn.y + (abtn.h - at.get_height()) // 2))

    # ── 快捷栏（UIWindow/ShortCut 竖条，常驻）──────────────────────
    # ── 按键设置窗（O）──────────────────────────────────────────────
    def _slot_label(self, slot: int) -> str:
        """快捷栏角标键名：改绑后显示新键（如 Q/F5），未绑回退槽号。"""
        if self.bindings is not None:
            kc = self.bindings.slot_key(slot)
            if kc is not None and kc > 0:
                return display_key(kc)
        return str(slot)

    def _kc_entries(self) -> List[Tuple[str, str]]:
        """条目序列：分组标题行与动作行交错（绘制与滚轮共用同一序列）。"""
        out: List[Tuple[str, str]] = []
        last: Optional[str] = None
        for a in ACTIONS:
            if a.group != last:
                out.append(("h", a.group))
                last = a.group
            out.append(("a", a.id))
        return out

    def _skill_of_slot(self, player, slot: int) -> str:
        """槽位当前挂的技能名（无则空串），供「技能 N · 断魂箭」行标签。"""
        book = getattr(player, "skills", None)
        sid = book.hotkeys.get(slot) if book is not None else None
        d = book.defs.get(sid) if book is not None and sid else None
        return f" · {d.name}" if d is not None and d.name else ""

    def _draw_keyconfig(self, surface, player) -> None:
        """自绘按键设置窗：分组列表 + 键名，录入行动作显示「请按键…」。"""
        fs = self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        w = KC_W
        h = 24 + KC_ROWS * KC_ROW_H + 20
        x, y = self._resolve_pos("keyconfig", (max(8, (vw - w) // 2), 52),
                                 (w, h), vw, vh)
        rect = pygame.Rect(x, y, w, h)
        self._kc_rect = rect
        _panel(surface, rect)
        self._add_chrome(surface, "keyconfig", x, y, w, 24)
        top = y + 26
        entries = self._kc_entries()
        self._kc_scroll = max(0, min(self._kc_scroll,
                                     max(0, len(entries) - KC_ROWS)))
        for i, (kind, payload) in enumerate(
                entries[self._kc_scroll:self._kc_scroll + KC_ROWS]):
            ry = top + i * KC_ROW_H
            if kind == "h":
                surface.blit(fs.render(f"〔{payload}〕", True, (150, 190, 235)),
                             (x + 10, ry + 2))
                continue
            a = ACTION_BY_ID[payload]
            row = pygame.Rect(x + 8, ry - 1, w - 16, KC_ROW_H)
            capturing = self._capture == payload
            if capturing:
                pygame.draw.rect(surface, (66, 54, 20), row, border_radius=3)
            label = a.label + (self._skill_of_slot(player, int(payload[6:]))
                               if payload.startswith("skill_") else "")
            surface.blit(fs.render(label, True, (235, 235, 225)),
                         (row.x + 3, ry + 2))
            if capturing:
                key_txt = fs.render("请按键…", True, (255, 214, 92))
            elif self.bindings is not None:
                key_txt = fs.render(display_key(self.bindings.key_of(payload)),
                                    True, (255, 220, 90))
            else:
                key_txt = fs.render("?", True, (200, 200, 200))
            surface.blit(key_txt, (row.right - key_txt.get_width() - 3, ry + 2))
            self._kc_rows.append((row, payload))
        surface.blit(fs.render("左键改绑 · 右键重置 · Esc 取消", True,
                               (140, 140, 130)), (x + 10, y + h - 16))

    def draw_quickslots(self, surface, player) -> None:
        fs = self.ui.font_small
        vw, vh = surface.get_width(), surface.get_height()
        bg = self._wz(SHT_BG)
        if bg is None:
            self._draw_quickslots_fallback(surface, player)
            return
        x = vw - SHT_W - 4
        y = vh - SHT_H - BAR_RESERVE - 2
        surface.blit(bg, (x, y))
        # 键位 1..n 依次放进 2 列 × 6 行格子里（读职业动态快捷键表）
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
            icon = self.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (30, 30)),
                             (cx + (cell.w - 30) // 2, cy + (cell.h - 30) // 2))
            cd = player.skills.cooldowns.get(sid, 0.0)
            total = settings.SKILL_COOLDOWN.get(sid, 0.8)
            if cd > 0:
                frac = max(0.0, min(1.0, cd / total))
                cover_h = max(1, int(cell.h * frac))
                shade = pygame.Surface((cell.w, cover_h), pygame.SRCALPHA)
                shade.fill((10, 10, 14, 150))
                surface.blit(shade, (cell.x, cell.bottom - cover_h))
            kb = fs.render(self._slot_label(hk), True, (255, 220, 90))
            surface.blit(kb, (cell.x + 3, cell.y + 1))
            lv = player.skills.levels[sid]
            mp = fs.render(f"{d.stat(lv, 'mpCon', 0)}", True, (140, 180, 240))
            surface.blit(mp, (cell.right - mp.get_width() - 2,
                              cell.bottom - mp.get_height() - 1))

    def _draw_quickslots_fallback(self, surface, player) -> None:
        fs = self.ui.font_small
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
            _panel(surface, slot, (70, 76, 90))
            icon = self.assets.skill_icon(sid)
            if icon is not None:
                surface.blit(pygame.transform.scale(icon, (34, 34)),
                             (slot.x + 6, slot.y + 6))
            cd = player.skills.cooldowns.get(sid, 0.0)
            total = settings.SKILL_COOLDOWN.get(sid, 0.8)
            if cd > 0:
                frac = max(0.0, min(1.0, cd / total))
                cover_h = max(1, int(slot.h * frac))
                shade = pygame.Surface((slot.w, cover_h), pygame.SRCALPHA)
                shade.fill((10, 10, 14, 150))
                surface.blit(shade, (slot.x, slot.y + slot.h - cover_h))
            kb = fs.render(self._slot_label(key), True, (255, 220, 90))
            surface.blit(kb, (slot.x + 3, slot.y + 2))
            mp = fs.render(f"{d.stat(lv, 'mpCon', 0)}", True, (120, 170, 230))
            surface.blit(mp, (slot.right - mp.get_width() - 3,
                              slot.bottom - mp.get_height() - 2))
            y -= slot.h + 8

    # ── 提示框（ContextMenu 官方三段底）───────────────────────────
    def _item_tip(self, item) -> str:
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

    def _draw_tooltip(self, surface, mouse_pos) -> None:
        if self._tooltip is None:
            return
        fs = self.ui.font_small
        f = self.ui.font
        lines = self._tooltip.split("\n")
        # □ 先定框：标题（粗行）用 f，正文用 fs，左右各留 9px 内边距。
        text_pad = 9
        inner = max(f.size(lines[0])[0],
                    max((fs.size(l)[0] for l in lines[1:]), default=0))
        # 先按屏幕可用宽度收紧框宽，再据此换行，避免文字溢出边界。
        avail_w = min(inner + text_pad * 2, surface.get_width() - 20)
        x = min(mouse_pos[0] + 14, surface.get_width() - avail_w - 20)
        y = mouse_pos[1] + 14
        rect = pygame.Rect(x, y, avail_w, 26 + 16 + 8)
        if rect.bottom > surface.get_height():
            rect.bottom = surface.get_height()
        body_w = rect.w - text_pad * 2
        # 正文超宽则自动换行，标题也按需换行，避免文字溢出框边。
        wrapped = [self.ui._wrap(lines[0], body_w, f)]
        for ln in lines[1:]:
            wrapped.append(self.ui._wrap(ln, body_w, fs))
        n_lines = sum(len(l) for l in wrapped)
        rect.h = 26 + (n_lines - 1) * 16 + 8
        if not draw_menu_bg(surface, self.assets, rect):
            _panel(surface, rect, (120, 126, 140))
        surface.blit(f.render(wrapped[0][0], True, (245, 220, 140)),
                     (rect.x + text_pad, rect.y + 5))
        ty = rect.y + 27
        for group in wrapped[1:]:
            for ln in group:
                surface.blit(fs.render(ln, True, (215, 220, 230)),
                             (rect.x + text_pad, ty))
                ty += 16


def _ellipsize(text: str, font: pygame.font.Font, max_w: int) -> str:
    """把文字用省略号截断到 max_w 宽度内，确保不溢出控件边界。"""
    if font.size(text)[0] <= max_w:
        return text
    ell = "..."
    while text and font.size(text + ell)[0] > max_w:
        text = text[:-1]
    return text + ell


def draw_menu_bg(surface, assets, rect: pygame.Rect) -> bool:
    """UIWindow/ContextMenu t/c/s 三段深色官方底（Tooltip 同款）。"""
    t = assets.ui_surface("UIWindow.img", "ContextMenu/t")
    c = assets.ui_surface("UIWindow.img", "ContextMenu/c")
    s = assets.ui_surface("UIWindow.img", "ContextMenu/s")
    if not (t and c and s):
        return False
    W, H = rect.size
    th, sh = t[0].get_height(), s[0].get_height()
    top = t[0] if W == t[0].get_width() else pygame.transform.smoothscale(t[0], (W, th))
    bot = s[0] if W == s[0].get_width() else pygame.transform.smoothscale(s[0], (W, sh))
    surface.blit(top, rect.topleft)
    surface.blit(bot, (rect.x, rect.bottom - sh))
    mid_h = max(0, H - th - sh)
    if mid_h > 0:
        mid = pygame.transform.smoothscale(c[0], (W, mid_h))
        surface.blit(mid, (rect.x, rect.y + th))
    return True
