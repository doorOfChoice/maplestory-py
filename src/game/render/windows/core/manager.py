"""WindowManager：窗口注册表 + z 序 + 统一事件分发 + 全局 toast/tooltip/模态框/拖扔。

game.py 只需把原始 pygame 事件交给 dispatch()，返回 True 即 UI 已消费；
坐标在这里完成「物理窗口 → 内部视口」缩放，窗口层永远只看 VIEW 坐标。
物品拖扔状态机：拖到别的窗口 = 投递 handle_drop（穿戴/卖出/存入）；拖出界
先弹确认框（堆叠可拆数量），确认后才取出扔地；0.35s 双击 = 使用/穿戴。
落地动作（combat.drop_player_item / 音效）仍归 game.py —— UI 层不碰世界。
窗口拖动位置持久化到 WINDOW_POS_FILE，跨会话记忆。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

from game import settings
from game.render.windows.core import widgets
from game.render.windows.core.dialogs import Modal
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
    def __init__(self, svc: WindowServices,
                 pos_path: Optional[object] = None) -> None:
        self.svc = svc
        self._stack: List[Window] = []          # 底 → 顶（注册序 = 默认 z 序）
        self._drag_win: Optional[Tuple[Window, Tuple[int, int]]] = None  # (窗口, 抓取偏移)
        self._pick: Optional[_Pick] = None
        self._last_click: Optional[Tuple[tuple, float]] = None   # ((key, source), 时刻)
        self._dropped: Optional[object] = None
        self._toasts: List[List] = []         # [[text, remain], ...] 先到先显示
        self._tip: Optional[object] = None   # str 或 core.item_tip.TipLine 列表
        self._view: Tuple[int, int] = (settings.VIEW_W, settings.VIEW_H)
        self._mouse: Tuple[int, int] = (-1, -1)   # 最近事件位置（VIEW 坐标）
        self._modal: Optional[Modal] = None       # 全局模态框（确认/数量）
        self._pos_path = pos_path                 # 窗口位置持久化文件（可 None）
        self._positions = self._load_positions()
        svc.flash = self.flash
        svc.tooltip = self.set_tooltip
        svc.modal = self.request_modal
        svc.mouse = lambda: self._mouse

    # ── 注册 ───────────────────────────────────────────────────────
    def add(self, win: Window) -> Window:
        win._mgr = self
        saved = self._positions.get(win.key)
        if isinstance(saved, (list, tuple)) and len(saved) == 2:
            win._user_pos = (int(saved[0]), int(saved[1]))
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
        """顶部提示：同文案重复触发只续命；不同文案排队（最多 3 条）。"""
        for t in self._toasts:
            if t[0] == text:
                t[1] = duration
                return
        self._toasts.append([text, duration])
        if len(self._toasts) > 3:
            del self._toasts[:-3]

    def set_tooltip(self, tip) -> None:
        """悬停提示：纯文本或 core.item_tip.TipLine 结构化行列表。"""
        self._tip = tip

    def last_toast(self) -> Optional[str]:
        """最近一条尚未消失的 toast 文本（无则 None）。"""
        return self._toasts[-1][0] if self._toasts else None

    def request_modal(self, modal: Modal) -> None:
        """弹全局模态框（同一时刻只保留最新一个）。

        确认/取消都先收起再跑回调：先收起，回调里再开新框（如链式确认）
        才不会被本框的关闭动作覆盖掉。
        """
        on_ok, on_cancel = modal.on_ok, modal.on_cancel

        def ok(qty) -> None:
            self._modal = None
            on_ok(qty)

        def cancel() -> None:
            self._modal = None
            if on_cancel is not None:
                on_cancel()

        modal.on_ok = ok
        modal.on_cancel = cancel
        self._modal = modal.open()

    def modal_open(self) -> bool:
        return self._modal is not None

    def take_dropped(self):
        """game.py 每帧取走「拖出扔地」的物品（取一次即清空）。"""
        item, self._dropped = self._dropped, None
        return item

    def close_npc_windows(self) -> None:
        for win in self._stack:
            if win.closes_on_map_change and win.visible:
                self._close_window(win)

    def _close_window(self, win: Window) -> None:
        """关窗并联动伙伴窗（背包 × 同时关纸娃娃，与 I 键语义对称）。"""
        win.close()
        if win.also_close:
            for other in self._stack:
                if other.key == win.also_close and other.visible:
                    other.close()

    def handle_escape(self) -> bool:
        """Esc 逐层关窗：模态框 > escape_closes 窗 > 最顶普通窗。"""
        if self._modal is not None:
            self._cancel_modal()
            return True
        for win in reversed(self._stack):
            if win.visible and win.escape_closes:
                self._close_window(win)
                return True
        for win in reversed(self._stack):
            if win.visible:
                self._close_window(win)
                return True
        return False

    # ── 窗口位置持久化 ─────────────────────────────────────────────
    def _load_positions(self) -> dict:
        if self._pos_path is None:
            return {}
        try:
            with open(self._pos_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _remember_position(self, win: Window) -> None:
        if self._pos_path is None or win._user_pos is None:
            return
        self._positions[win.key] = [int(win._user_pos[0]), int(win._user_pos[1])]
        try:
            with open(self._pos_path, "w", encoding="utf-8") as fh:
                json.dump(self._positions, fh)
        except OSError:
            pass

    # ── 事件分发（返回 True = UI 已消费）───────────────────────────
    def dispatch(self, event) -> bool:
        if hasattr(event, "pos"):
            self._mouse = to_view_pos(event.pos)   # hover/tooltip 用最近位置
        if self._modal is not None:                # 模态框打开：吞掉一切鼠标
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._modal.handle_mouse_down(self._mouse)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._left_down(to_view_pos(event.pos))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            return self._right_click(to_view_pos(event.pos))
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            return self._wheel(to_view_pos(event.pos),
                               -1 if event.button == 4 else 1)
        if event.type == pygame.MOUSEWHEEL:      # pygame2 滚轮事件无 pos，用最近鼠标位
            return self._wheel(self._mouse, -1 if event.y > 0 else 1)
        if event.type == pygame.MOUSEMOTION:
            return self._motion(to_view_pos(event.pos))
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            return self._left_up(to_view_pos(event.pos))
        return False

    def dispatch_key(self, key: int) -> bool:
        """键盘：模态框 > 自顶向下问窗口（按键设置的录入态吞键走这里）。"""
        if self._modal is not None:
            return self._modal.handle_keydown(key)
        for win in reversed(self._stack):
            if win.visible and win.handle_keydown(key):
                return True
        return False

    def _cancel_modal(self) -> None:
        modal, self._modal = self._modal, None
        if modal is not None:
            modal.cancel()

    # ── 命中扫描 ───────────────────────────────────────────────────
    def raise_to_top(self, win: Window) -> None:
        if win in self._stack:
            self._stack.remove(win)
            self._stack.append(win)

    _raise_to_top = raise_to_top       # 兼容旧私有名调用点

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
        # 命中点最顶的可交互窗口独占本次点击：关闭钮 / 拖标题 / 拾取 / 普通
        # 按钮一律只问它。若扫描全部窗口，顶层面板按钮会被下层窗口的标题热区
        # 或物品格抢占，导致「最前面的面板按钮点不动」。
        hit = self._topmost_at(pos, interactive_only=True)
        if hit is None:
            return False
        if hit.close_rect is not None and hit.close_rect.collidepoint(pos):
            self.cancel_interactions()
            self._close_window(hit)
            return True
        if self._drag_win is not None or self._pick is not None:
            return True
        self._raise_to_top(hit)
        if hit.title_rect is not None and hit.title_rect.collidepoint(pos):
            self._drag_win = (hit, (pos[0] - hit.rect.x, pos[1] - hit.rect.y))
            return True
        pk = hit.pickup(pos)
        if pk is not None:
            self._pick = _Pick(win=hit, pk=pk, start=pos, pos=pos)
            return True
        if hit.handle_mouse_down(pos):
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
            win, self._drag_win = self._drag_win[0], None
            self._remember_position(win)
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
                self._begin_ground_drop(d)
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

    def _begin_ground_drop(self, d: _Pick) -> None:
        """拖出界松手 ≠ 立刻销毁：先弹确认框（可堆叠 >1 时可选数量）。"""
        win, pk = d.win, d.pk
        item = pk.item
        name = getattr(item, "name", None) or "物品"
        count = max(1, int(getattr(item, "count", 1) or 1))
        stackable = getattr(item, "kind", "") in ("consume", "etc")

        def finish(qty: Optional[int]) -> None:
            got = win.take_for_drop(pk, qty)
            if got is not None:
                self._dropped = got
                n = int(getattr(got, "count", 1) or 1)
                self.flash(f"扔出 {got.name} ×{n}" if n > 1
                           else f"扔出 {getattr(got, 'name', '物品')}")

        if stackable and count > 1:
            self.request_modal(Modal(
                title=f"丢弃「{name}」", numeric=True, max_value=count,
                hint=f"拥有 {count} 个，扔出多少个？（不可找回）",
                ok_label="扔出", on_ok=finish))
        else:
            self.request_modal(Modal(
                title=f"丢弃「{name}」",
                hint="物品将扔在脚下，确定？（不可找回）",
                ok_label="扔出",
                on_ok=lambda _q: finish(count)))

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
        if self._modal is None:                   # 模态框打开时不画气泡/拖影
            if self._tip is not None:
                widgets.draw_tooltip(surface, self.svc, self._mouse, self._tip)
            if self._pick is not None and self._pick.active:
                self._draw_drag_icon(surface, self._pick)
        self._draw_toasts(surface)

    def draw_modal(self, surface) -> None:
        """模态框单独最外层绘制：game.py 在对话/聊天/死亡面板之后再调用，
        否则出租车确认框会被后画的 NPC 对话气泡盖住。"""
        if self._modal is not None:
            self._modal.draw(surface, self.svc)

    def _draw_toasts(self, surface) -> None:
        """toast 队列：每条独立倒计时，同屏最多叠 3 条，先到先消。"""
        alive: List[List] = []
        y = 34
        for t in self._toasts:
            t[1] -= 1 / 60
            if t[1] > 0:
                alive.append(t)
                widgets.draw_toast(surface, self.svc, t[0], y=y)
                y += 30
        self._toasts = alive

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
