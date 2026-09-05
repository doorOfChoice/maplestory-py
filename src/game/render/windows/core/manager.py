"""WindowManager：窗口注册表 + z 序 + 统一事件分发 + 全局 toast/tooltip/拖扔。

game.py 只需把原始 pygame 事件交给 dispatch()，返回 True 即 UI 已消费；
坐标在这里完成「物理窗口 → 内部视口」缩放，窗口层永远只看 VIEW 坐标。
物品拖扔状态机（拖出来源窗口 = 扔地；0.35s 双击 = 使用/穿戴）由本类驱动，
落地动作（combat.drop_player_item / 音效）仍归 game.py —— UI 层不碰世界。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

from game import settings
from game.render.windows.core import widgets
from game.systems.scrolls import is_scroll_id
from game.render.windows.core.services import WindowServices
from game.render.windows.core.window import DOUBLE_CLICK_TIME, DRAG_THRESHOLD, \
    DragPickup, Window


def to_view_pos(window_pos: Tuple[int, int]) -> Tuple[int, int]:
    """物理窗口坐标 → 内部视口坐标（与 game.py 旧算法一致）。"""
    return (window_pos[0] * settings.VIEW_W // settings.WINDOW_W,
            window_pos[1] * settings.VIEW_H // settings.WINDOW_H)


@dataclass
class _Pick:
    """一次物品按下/拖拽的运行时状态。"""

    win: Window
    pk: DragPickup
    start: Tuple[int, int]
    pos: Tuple[int, int]
    active: bool = False


class WindowManager:
    def __init__(self, svc: WindowServices) -> None:
        self.svc = svc
        self._stack: List[Window] = []          # 底 → 顶（注册序 = 默认 z 序）
        self._drag_win: Optional[Tuple[Window, Tuple[int, int]]] = None  # (窗口, 抓取偏移)
        self._pick: Optional[_Pick] = None
        self._last_click: Optional[Tuple[tuple, float]] = None   # ((key, source), 时刻)
        self._dropped: Optional[object] = None
        self._toast: Optional[Tuple[str, float]] = None
        self._tip: Optional[str] = None
        self._view: Tuple[int, int] = (settings.VIEW_W, settings.VIEW_H)
        self._mouse: Tuple[int, int] = (-1, -1)   # 最近事件位置（VIEW 坐标）
        svc.flash = self.flash
        svc.tooltip = self.set_tooltip
        svc.mouse = lambda: self._mouse

    # ── 注册 ───────────────────────────────────────────────────────
    def add(self, win: Window) -> Window:
        self._stack.append(win)
        return win

    def get(self, key: str) -> Window:
        for win in self._stack:
            if win.key == key:
                return win
        raise KeyError(f"未注册的窗口: {key}")

    @property
    def windows(self) -> List[Window]:
        return list(self._stack)

    # ── 全局服务 ───────────────────────────────────────────────────
    def flash(self, text: str, duration: float = 1.6) -> None:
        self._toast = (text, duration)

    def set_tooltip(self, text: str) -> None:
        self._tip = text

    def take_dropped(self):
        """game.py 每帧取走「拖出扔地」的物品（取一次即清空）。"""
        item, self._dropped = self._dropped, None
        return item

    def close_npc_windows(self) -> None:
        for win in self._stack:
            if win.closes_on_map_change and win.visible:
                win.close()

    def handle_escape(self) -> bool:
        """Esc：自顶向下关第一个声明 escape_closes 的可见窗口。"""
        for win in reversed(self._stack):
            if win.visible and win.escape_closes:
                win.close()
                return True
        return False

    # ── 事件分发（返回 True = UI 已消费）───────────────────────────
    def dispatch(self, event) -> bool:
        if hasattr(event, "pos"):
            self._mouse = to_view_pos(event.pos)   # hover/tooltip 用最近位置
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._left_down(to_view_pos(event.pos))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            return self._right_click(to_view_pos(event.pos))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            return self._wheel(to_view_pos(event.pos),
                               -1 if event.button == 4 else 1)
        if event.type == pygame.MOUSEMOTION:
            return self._motion(to_view_pos(event.pos))
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self._left_up(to_view_pos(event.pos))
        return False

    def dispatch_key(self, key: int) -> bool:
        """键盘：自顶向下问窗口（按键设置的录入态吞键走这里）。"""
        for win in reversed(self._stack):
            if win.visible and win.handle_keydown(key):
                return True
        return False

    # ── 命中扫描 ───────────────────────────────────────────────────
    def _raise_to_top(self, win: Window) -> None:
        self._stack.remove(win)
        self._stack.append(win)

    def _topmost_at(self, pos: Tuple[int, int],
                    interactive_only: bool = False) -> Optional[Window]:
        for win in reversed(self._stack):
            if (win.visible and win.rect.collidepoint(pos)
                    and (win.interactive or not interactive_only)):
                return win
        return None

    def dragging(self) -> bool:
        """是否有进行中的拖拽（物品/技能/按键或窗口标题移动），供光标手势判定。"""
        return (self._pick is not None and self._pick.active
                or self._drag_win is not None)

    def _left_down(self, pos: Tuple[int, int]) -> bool:
        for win in reversed(self._stack):
            if (win.visible and win.close_rect is not None
                    and win.close_rect.collidepoint(pos)):
                self.cancel_interactions()
                win.close()
                return True
        if self._drag_win is not None or self._pick is not None:
            return True
        hit = self._topmost_at(pos, interactive_only=True)
        if hit is not None:
            self._raise_to_top(hit)
        for win in reversed(self._stack):
            if not win.visible:
                continue
            if win.title_rect is not None and win.title_rect.collidepoint(pos):
                self._drag_win = (win, (pos[0] - win.rect.x, pos[1] - win.rect.y))
                return True
        for win in reversed(self._stack):
            if not win.visible:
                continue
            pk = win.pickup(pos)
            if pk is not None:
                self._pick = _Pick(win=win, pk=pk, start=pos, pos=pos)
                return True
        if hit is not None and hit.handle_mouse_down(pos):
            return True
        return False

    def _motion(self, pos: Tuple[int, int]) -> bool:
        if self._drag_win is not None:
            win, (gx, gy) = self._drag_win
            win.move_to(pos[0] - gx, pos[1] - gy, self._view[0], self._view[1])
            return True
        if self._pick is not None:
            d = self._pick
            d.pos = pos
            if not d.active:
                dx = pos[0] - d.start[0]
                dy = pos[1] - d.start[1]
                if dx * dx + dy * dy > DRAG_THRESHOLD * DRAG_THRESHOLD:
                    d.active = True
            return True
        hit = self._topmost_at(pos, interactive_only=True)
        return hit.handle_mouse_motion(pos) if hit is not None else False

    def cancel_interactions(self) -> None:
        """清空进行中的窗口/物品拖拽（关窗、切图等外部动作后调用）。"""
        self._drag_win = None
        self._pick = None

    def _left_up(self, pos: Tuple[int, int]) -> bool:
        if self._drag_win is not None:
            self._drag_win = None
            return True
        d = self._pick
        if d is None:
            hit = self._topmost_at(pos, interactive_only=True)
            return hit.handle_mouse_up(pos) if hit is not None else False
        self._pick = None
        if d.active:
            hit = self._topmost_at(pos)
            if hit is not None and hit.handle_drop(d.pk, pos):
                return True
            if d.pk.kind != "item":
                return True
            if not d.pk.home.collidepoint(pos):
                item = d.win.take_for_drop(d.pk)
                if item is not None:
                    self._dropped = item
            return True
        key = (d.win.key, d.pk.source)
        now = pygame.time.get_ticks() / 1000.0
        last = self._last_click
        is_double = (last is not None and last[0] == key
                     and now - last[1] <= DOUBLE_CLICK_TIME)
        self._last_click = None if is_double else (key, now)
        if is_double:
            d.win.activate(d.pk)
        return True

    def _wheel(self, pos: Tuple[int, int], amount: int) -> bool:
        win = self._topmost_at(pos, interactive_only=True)
        return win.handle_wheel(pos, amount) if win is not None else False

    def _right_click(self, pos: Tuple[int, int]) -> bool:
        win = self._topmost_at(pos, interactive_only=True)
        return win.handle_right_click(pos) if win is not None else False

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface) -> None:
        self._view = (surface.get_width(), surface.get_height())
        self._tip = None
        for win in self._stack:
            if win.visible:
                win.draw(surface)
        if self._tip is not None:
            widgets.draw_tooltip(surface, self.svc, self._mouse, self._tip)
        if self._pick is not None and self._pick.active:
            self._draw_drag_icon(surface, self._pick)
        if self._toast is not None:
            text, remain = self._toast
            remain -= 1 / 60
            if remain <= 0:
                self._toast = None
            else:
                self._toast = (text, remain)
                widgets.draw_toast(surface, self.svc, text)

    def _draw_drag_icon(self, surface, d: _Pick) -> None:
        if d.pk.kind == "skill":
            icon = self.svc.assets.skill_icon(d.pk.payload)
            if icon is not None:
                icon = widgets.fit_icon(icon, 32)
                px, py = d.pos
                surface.blit(icon, (px - icon.get_width() // 2,
                                    py - icon.get_height() // 2))
                return
        if d.pk.kind != "item":
            self._draw_drag_label(surface, d)
            return
        item = d.pk.item
        if is_scroll_id(item.id):
            icon = widgets.scroll_icon()        # 234 段自制卷轴：统一自绘图标
        else:
            icon = (self.svc.assets.equip_icon(item.id) if item.kind == "equip"
                    else self.svc.assets.item_icon(item.id))
        if icon is None:
            return
        icon = widgets.fit_icon(icon, 32)
        px, py = d.pos
        surface.blit(icon, (px - icon.get_width() // 2,
                            py - icon.get_height() // 2))

    def _draw_drag_label(self, surface, d: _Pick) -> None:
        """无图标的拖拽载荷：跟随鼠标的胶囊文字（指令名 / 技能名）。"""
        fs = self.svc.ui.font_small
        txt = fs.render(d.pk.label or "?", True, (255, 240, 200))
        w, h = txt.get_width() + 12, txt.get_height() + 6
        px, py = d.pos
        plate = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(plate, (30, 26, 16, 220), (0, 0, w, h),
                         border_radius=7)
        pygame.draw.rect(plate, (160, 140, 90), (0, 0, w, h), 1,
                         border_radius=7)
        plate.blit(txt, (6, 3))
        surface.blit(plate, (px - w // 2, py - h // 2))
