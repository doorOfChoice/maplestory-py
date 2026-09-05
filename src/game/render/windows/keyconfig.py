"""按键设置窗（原版式）：上半虚拟键盘 + 下半可拖拽指令栏。

纯鼠标交互：把指令栏条目或技能窗里的技能拖到键格即完成绑定（KeyBindings
冲突自动互换、即时 save 落盘）；右键键格把该键动作恢复默认（链式归位）。
Esc 键格仅展示「取消」职能，永不作为绑定落点。坐标约定同 Window 基类
（事件 pos 为内部 VIEW 坐标），热区（key_cells / rows）由 draw 重建。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.core.keybindings import (ACTION_BY_ID, ACTIONS, GROUP_SKILL,
                                   display_key, item_action,
                                   item_id_of_action)
from game.core.keylayout import KEY_ROWS, key_units_total
from game.render.windows.core import widgets
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DragPickup, Window
from game.systems.skills import assign_skill_to_key

# ── 窗体几何 ────────────────────────────────────────────────────────
UNIT = 34                # 键帽单位宽（1u = 一个标准键）
KEY_H = 34               # 键帽高
KEY_GAP = 2              # 键帽间隙
KC_PAD = 8               # 面板留白
CHROME_H = 24            # 标题条高
TILE_W = 62              # 指令方块宽
TILE_H = 20              # 指令方块高
TILE_GAP = 4             # 方块间隙
GROUP_LABEL_H = 15       # 分组小标题占高
KEY_ICON = 16            # 键帽上技能图标边长

# 指令方块的两字短签（键帽标签与拖拽胶囊共用）
SHORT_LABELS = {
    "move_left": "左移", "move_right": "右移",
    "move_up": "上爬", "move_down": "下跳",
    "jump": "跳跃", "attack": "攻击", "pickup": "拾取",
    "talk": "对话", "chat": "聊天", "respawn": "复活",
    "window_inventory": "背包", "window_skill": "技能",
    "window_stat": "状态", "window_quest": "任务",
    "minimap": "地图", "window_keyconfig": "按键",
    "quest_tracker": "追踪",
}


def _group_entries() -> List[Tuple[str, str]]:
    """指令栏条目序列：分组标题行与动作行交错（技能组除外——技能只从技能窗拖入）。"""
    out: List[Tuple[str, str]] = []
    last: Optional[str] = None
    for a in ACTIONS:
        if a.group == GROUP_SKILL:
            continue
        if a.group != last:
            out.append(("h", a.group))
            last = a.group
        out.append(("a", a.id))
    return out


class KeyConfigWindow(Window):
    """键盘式改绑窗：拖指令方块/技能到键格绑定、右键键格重置。"""

    key = "keyconfig"
    escape_closes = True

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self._entries = _group_entries()
        # 本帧登记热区（契约同 title_rect：绘制重建、事件帧命中）
        self.key_cells: List[Tuple[pygame.Rect, int]] = []
        self.rows: List[Tuple[pygame.Rect, str]] = []

    # ── 定位 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        w, h = self._size()
        return (max(8, (vw - w) // 2), max(8, (vh - h) // 2 - 20))

    @staticmethod
    def _size() -> Tuple[int, int]:
        w = int(KC_PAD * 2 + key_units_total(KEY_ROWS[0]) * UNIT)
        return w, (CHROME_H + len(KEY_ROWS) * (KEY_H + KEY_GAP)
                   + 8 + KeyConfigWindow._palette_height(w) + 16)

    @staticmethod
    def _per_row(w: int) -> int:
        return max(1, (w - KC_PAD * 2 + TILE_GAP) // (TILE_W + TILE_GAP))

    @classmethod
    def _palette_height(cls, w: int) -> int:
        """标题带 + 每组（小标题带 + 方块行 × 行距）。"""
        per = cls._per_row(w)
        counts: List[int] = []
        for kind, _ in _group_entries():
            if kind == "h":
                counts.append(0)
            else:
                counts[-1] += 1
        rows = sum(-(-n // per) for n in counts)
        return ((1 + len(counts)) * GROUP_LABEL_H
                + rows * (TILE_H + TILE_GAP))

    # ── 事件：拖拽源与落点 ─────────────────────────────────────────
    def pickup(self, pos: Tuple[int, int]) -> Optional[DragPickup]:
        """按住指令栏动作行 → 起拖一个 cmd 载荷。"""
        for rect, action in self.rows:
            if rect.collidepoint(pos):
                return DragPickup(source=("cmd", action), item=None,
                                  home=rect, kind="cmd", payload=action,
                                  label=self.row_label(action))
        return None

    def handle_drop(self, pk: DragPickup, pos: Tuple[int, int]) -> bool:
        """cmd / skill / item 载荷落在键格上 → 改绑（冲突互换）并落盘。"""
        bindings = self.svc.bindings
        if bindings is None or pk.kind not in ("cmd", "skill", "item"):
            return False
        hit = next((k for rect, k in self.key_cells
                    if rect.collidepoint(pos)), None)
        if hit is None:
            return False
        if pk.kind == "cmd":
            if not bindings.set(str(pk.payload), hit):
                return False
            bindings.save()
            return True
        if pk.kind == "item":
            item = pk.item
            if item is None or getattr(item, "kind", "") != "consume":
                self.svc.flash("只有消耗品可以绑到键上")
                return False
            if not bindings.set(item_action(str(item.id)), hit):
                return False
            bindings.save()
            return True
        player = self.svc.player()
        book = getattr(player, "skills", None)
        if book is None or not assign_skill_to_key(
                book, bindings, str(pk.payload), hit):
            self.svc.flash("技能放不下：槽位已满或被占用")
            return False
        bindings.save()
        return True

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)

    def handle_right_click(self, pos: Tuple[int, int]) -> bool:
        """右键键格：该键上的动作恢复默认绑法（被顶用的动作链式归位）。"""
        bindings = self.svc.bindings
        if bindings is None:
            return False
        for rect, key in self.key_cells:
            if rect.collidepoint(pos):
                action = bindings.action_for(key)
                if action is None:
                    return True
                bindings.reset(action)
                bindings.save()
                return True
        return False

    # ── 标签 ───────────────────────────────────────────────────────
    def row_label(self, action: str) -> str:
        """方块/胶囊用两字短签，未收录的动作回退全名。"""
        return SHORT_LABELS.get(action, ACTION_BY_ID[action].label)

    def _book(self):
        player = self.svc.player()
        return getattr(player, "skills", None)

    def _skill_sid(self, action: str) -> Optional[str]:
        """skill_N 动作 → 槽位当前技能 id（无玩家/无技能则 None）。"""
        if not action.startswith("skill_"):
            return None
        book = self._book()
        return book.hotkeys.get(int(action[len("skill_"):])) if book else None

    def _action_icon(self, action: str):
        """键帽图标：技能取技能图，绑定消耗品取物品图。"""
        sid = self._skill_sid(action)
        if sid:
            return self.svc.assets.skill_icon(sid)
        item_id = item_id_of_action(action)
        return self.svc.assets.item_icon(item_id) if item_id else None

    def _item_name(self, item_id: str) -> str:
        player = self.svc.player()
        inv = getattr(player, "inventory", None) if player is not None else None
        item = inv.consumes.get(item_id) if inv is not None else None
        name = item.name if item is not None and item.name else ""
        return name or self.svc.assets.item_name(item_id) or f"物品{item_id}"

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        """键盘区逐行画键帽（技能绑定时显示技能图标），下方画指令方块栏。"""
        fs, ft = self.svc.ui.font_small, self.svc.ui.font_tiny
        bindings = self.svc.bindings
        w, h = self._size()
        x, y = self.place(surface, (w, h))
        widgets.panel_frame(surface, self.rect)
        self.add_chrome(surface, x, y, w, CHROME_H)
        self.key_cells = []
        self.rows = []
        full = key_units_total(KEY_ROWS[0]) * UNIT
        mouse = pygame.mouse.get_pos()
        ry = y + CHROME_H
        for row in KEY_ROWS:
            cx = x + KC_PAD + (full - key_units_total(row) * UNIT) / 2
            for spec in row:
                cell = pygame.Rect(int(cx), ry,
                                   int(spec.width * UNIT) - KEY_GAP, KEY_H)
                self._draw_key(surface, cell, spec.key, bindings, fs, mouse)
                if spec.key != pygame.K_ESCAPE:
                    self.key_cells.append((cell, spec.key))
                cx += spec.width * UNIT
            ry += KEY_H + KEY_GAP
        self._draw_palette(surface, x, ry + 8, w, bindings, fs, ft, mouse)

    def _draw_key(self, surface, cell: pygame.Rect, key: int, bindings,
                  fs, mouse: Tuple[int, int]) -> None:
        """单颗键帽：底色 + 键名 + 绑定动作（技能画图标）；Esc 灰显「取消」。"""
        esc = key == pygame.K_ESCAPE
        held = None if bindings is None else bindings.action_for(key)
        hover = cell.collidepoint(mouse) and not esc
        base = (34, 38, 48) if esc else (70, 78, 96) if hover else (52, 58, 74)
        pygame.draw.rect(surface, base, cell, border_radius=4)
        pygame.draw.rect(surface, (150, 190, 235) if hover else (90, 96, 110),
                         cell, 1, border_radius=4)
        ff = self.svc.ui.font
        name = "取消" if esc else display_key(key)
        t = ff.render(name, True, (150, 156, 172) if esc else (235, 235, 225))
        surface.blit(t, (cell.centerx - t.get_width() // 2, cell.y + 3))
        if esc or held is None:
            return
        icon = self._action_icon(held)
        if icon is not None:
            icon = pygame.transform.scale(icon, (KEY_ICON, KEY_ICON))
            surface.blit(icon, (cell.centerx - KEY_ICON // 2,
                                cell.bottom - KEY_ICON - 3))
            return
        label = widgets.ellipsize(self._action_text(held), fs, cell.width - 4)
        t2 = fs.render(label, True, (255, 214, 92))
        surface.blit(t2, (cell.centerx - t2.get_width() // 2, cell.bottom - 14))

    def _draw_palette(self, surface, x: int, top: int, w: int, bindings,
                      fs, ft, mouse: Tuple[int, int]) -> None:
        """指令方块栏：分组小标题 + 琥珀色方块网格逐行铺排，方块即拖拽源。"""
        left = x + KC_PAD
        per = self._per_row(w)
        y = top + GROUP_LABEL_H          # 首行留给「指令栏」大标题
        cx = 0
        for kind, payload in self._entries:
            if kind == "h":
                if cx:
                    y += TILE_H + TILE_GAP
                surface.blit(ft.render(f"〔{payload}〕", True,
                                       (160, 170, 190)), (left + 2, y + 2))
                y += GROUP_LABEL_H
                cx = 0
                continue
            if cx and cx % per == 0:
                cx = 0
                y += TILE_H + TILE_GAP
            tile = pygame.Rect(left + cx * (TILE_W + TILE_GAP), y,
                               TILE_W, TILE_H)
            self._draw_tile(surface, tile, payload, bindings, ft, mouse)
            self.rows.append((tile, payload))
            cx += 1
        surface.blit(fs.render("右键键位恢复默认 · 技能可从技能窗拖入", True,
                               (140, 140, 130)),
                     (x + KC_PAD + 2, self.rect.bottom - 15))

    def _draw_tile(self, surface, tile: pygame.Rect, action: str, bindings,
                   ft, mouse: Tuple[int, int]) -> None:
        """单个指令方块：画动作文字；右侧显示当前键。"""
        hover = tile.collidepoint(mouse)
        pygame.draw.rect(surface, (84, 68, 32) if hover else (62, 50, 24),
                         tile, border_radius=4)
        pygame.draw.rect(surface, (188, 158, 88) if hover else (130, 108, 60),
                         tile, 1, border_radius=4)
        tx = tile.x + 3
        text = self.row_label(action)
        bound = bindings.key_of(action) if bindings is not None else None
        key_txt = (ft.render(display_key(bound), True, (255, 220, 90))
                   if bound is not None and bound > 0 else None)
        avail = tile.right - tx - 3 - (key_txt.get_width() + 3
                                       if key_txt else 0)
        t = ft.render(widgets.ellipsize(text, ft, max(8, avail)), True,
                      (240, 232, 210))
        surface.blit(t, (tx, tile.centery - t.get_height() // 2))
        if key_txt is not None:
            surface.blit(key_txt, (tile.right - key_txt.get_width() - 3,
                                   tile.centery - key_txt.get_height() // 2))

    def _action_text(self, action: str) -> str:
        """动作短签：技能取绑定技能名（无则「技N」），物品取物品名，其余两字短签。"""
        if action.startswith("skill_"):
            sid = self._skill_sid(action)
            book = self._book()
            d = book.defs.get(sid) if book is not None and sid else None
            if d is not None and d.name:
                return d.name
            return f"技{int(action[len('skill_'):])}"
        item_id = item_id_of_action(action)
        if item_id is not None:
            return self._item_name(item_id)
        return self.row_label(action)
