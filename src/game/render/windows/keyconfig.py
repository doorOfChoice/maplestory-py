"""按键设置窗组件：动作列表 + 单击录入改绑（冲突互换）、右键恢复默认、滚轮翻页。

无专属原版素材，自绘风格与其它 fallback 面板一致；坐标约定同 Window 基类
（事件 pos 为内部 VIEW 坐标）。绑定表取 svc.bindings（改动即时 save 落盘）；
录入态吞键走 handle_keydown，由 manager.dispatch_key 在 Esc 链之前优先消费。
行为自 panels._draw_keyconfig / consume_binding_key 1:1 迁移。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import pygame

from game.core.keybindings import ACTION_BY_ID, ACTIONS, display_key
from game.render.windows import widgets
from game.render.windows.services import WindowServices
from game.render.windows.window import Window

# 按键设置窗几何（与旧 panels.KC_* 一致）
KC_W = 240           # 窗宽
KC_ROW_H = 18        # 行高
KC_ROWS = 15         # 一屏可见条目数（含分组标题行）


def _group_entries() -> List[Tuple[str, str]]:
    """条目序列：分组标题行与动作行交错（绘制与滚轮共用同一序列）。"""
    out: List[Tuple[str, str]] = []
    last: Optional[str] = None
    for a in ACTIONS:
        if a.group != last:
            out.append(("h", a.group))
            last = a.group
        out.append(("a", a.id))
    return out


class KeyConfigWindow(Window):
    """按键设置窗：点行进录入、按键改绑并落盘、右键行重置、Esc 取消/关闭。"""

    key = "keyconfig"
    escape_closes = True

    def __init__(self, svc: WindowServices) -> None:
        super().__init__(svc)
        self._capture: Optional[str] = None      # 正在录入改绑的动作 id
        self._entries = _group_entries()
        self._scroll = widgets.ScrollList(step=1)
        # 本帧登记的动作行热区（契约同 title_rect：绘制重建、事件帧命中）
        self.rows: List[Tuple[pygame.Rect, str]] = []

    # ── 开合（旧语义：每次打开重置录入与滚动）───────────────────────
    def open(self) -> None:
        self._capture = None
        self._scroll.reset()
        super().open()

    def on_close(self) -> None:
        self._capture = None

    @property
    def capturing_action(self) -> Optional[str]:
        """当前正在录入改绑的动作 id（None = 未录入）。"""
        return self._capture

    # ── 定位 ───────────────────────────────────────────────────────
    def anchor(self, vw: int, vh: int) -> Tuple[int, int]:
        return (max(8, (vw - KC_W) // 2), 52)

    # ── 事件 ───────────────────────────────────────────────────────
    def handle_keydown(self, key: int) -> bool:
        """录入态吞键完成改绑（冲突自动互换）并落盘；Esc 只取消录入。"""
        bindings = self.svc.bindings
        if self._capture is None or bindings is None:
            return False
        if key != pygame.K_ESCAPE:
            bindings.set(self._capture, key)
            bindings.save()
        self._capture = None
        return True

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        for rect, action in self.rows:
            if rect.collidepoint(pos):
                if self.svc.bindings is not None:
                    self._capture = None if self._capture == action else action
                return True
        return self.rect.collidepoint(pos)

    def handle_right_click(self, pos: Tuple[int, int]) -> bool:
        """右键按键设置行 → 该动作恢复默认绑法（被顶用的动作链式归位）。"""
        bindings = self.svc.bindings
        if bindings is None:
            return False
        for rect, action in self.rows:
            if rect.collidepoint(pos):
                bindings.reset(action)
                bindings.save()
                return True
        return False

    def handle_wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        self._scroll.scroll(amount, len(self._entries), KC_ROWS)
        return True

    # ── 标签 ───────────────────────────────────────────────────────
    def skill_of_slot(self, slot: int) -> str:
        """槽位当前挂的技能名（无则空串），供「技能 N · 断魂箭」行标签。"""
        player = self.svc.player()
        book = getattr(player, "skills", None)
        sid = book.hotkeys.get(slot) if book is not None else None
        d = book.defs.get(sid) if book is not None and sid else None
        return f" · {d.name}" if d is not None and d.name else ""

    def row_label(self, action: str) -> str:
        a = ACTION_BY_ID[action]
        if action.startswith("skill_"):
            return a.label + self.skill_of_slot(int(action[len("skill_"):]))
        return a.label

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        """自绘按键设置窗：分组列表 + 键名，录入行动作显示「请按键…」。"""
        fs = self.svc.ui.font_small
        bindings = self.svc.bindings
        w = KC_W
        h = 24 + KC_ROWS * KC_ROW_H + 20
        x, y = self.place(surface, (w, h))
        widgets.panel_frame(surface, self.rect)
        self.add_chrome(surface, x, y, w, 24)
        self.rows = []
        top = y + 26
        self._scroll.clamp(len(self._entries), KC_ROWS)
        for i, (kind, payload) in enumerate(
                self._entries[self._scroll.offset:
                              self._scroll.offset + KC_ROWS]):
            ry = top + i * KC_ROW_H
            if kind == "h":
                surface.blit(fs.render(f"〔{payload}〕", True, (150, 190, 235)),
                             (x + 10, ry + 2))
                continue
            row = pygame.Rect(x + 8, ry - 1, w - 16, KC_ROW_H)
            capturing = self._capture == payload
            if capturing:
                pygame.draw.rect(surface, (66, 54, 20), row, border_radius=3)
            surface.blit(fs.render(self.row_label(payload), True,
                                   (235, 235, 225)),
                         (row.x + 3, ry + 2))
            if capturing:
                key_txt = fs.render("请按键…", True, (255, 214, 92))
            elif bindings is not None:
                key_txt = fs.render(display_key(bindings.key_of(payload)),
                                    True, (255, 220, 90))
            else:
                key_txt = fs.render("?", True, (200, 200, 200))
            surface.blit(key_txt, (row.right - key_txt.get_width() - 3, ry + 2))
            self.rows.append((row, payload))
        surface.blit(fs.render("左键改绑 · 右键重置 · Esc 取消", True,
                               (140, 140, 130)), (x + 10, y + h - 16))
