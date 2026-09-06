"""全局模态弹框：确认 / 数字数量输入（ WindowManager 持有、叠在所有窗口之上）。

一套弹框同时服务：扔装备确认、堆叠拆分数量、商店/仓库拖放卖出/存入数量、
任务放弃确认等。数字弹框带「最大」按钮与实时演算行（note 回调按当前数量
生成文案，如「合计 1200 金币」）。键盘：数字录入 / 退格 / Enter 确认 /
Esc 取消；鼠标：确认 / 取消 / 最大。打开期间 manager 吞掉一切事件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import pygame

from game.render.windows.core import widgets

MAX_DIGITS = 4           # 数量最多录入 4 位（≤9999，与堆叠上限一致）


@dataclass
class Modal:
    """一个模态弹框的状态 + 绘制/事件处理（由 WindowManager 转发调用）。

    numeric=True 时 on_ok 收到所选数量（1..max_value 钳制）；否则收到 None。
    """

    title: str = ""
    hint: str = ""
    ok_label: str = "确认"
    cancel_label: str = "取消"
    numeric: bool = False
    max_value: int = 0
    note: Optional[Callable[[int], str]] = None      # 数字弹框的实时演算行
    on_ok: Callable[[Optional[int]], None] = field(default=lambda _qty: None)
    on_cancel: Optional[Callable[[], None]] = None

    text: str = ""
    _prefilled: bool = False
    ok_rect: Optional[pygame.Rect] = None
    cancel_rect: Optional[pygame.Rect] = None
    max_rect: Optional[pygame.Rect] = None

    def open(self) -> "Modal":
        self.text = str(max(1, self.max_value)) if (
            self.numeric and self.max_value > 0) else ""
        self._prefilled = bool(self.text)
        return self

    # ── 输入 ───────────────────────────────────────────────────────
    def type_digit(self, digit: str) -> None:
        if self._prefilled:            # 预填视作整串选中：打字即替换
            self._prefilled = False
            self.text = ""
        if len(self.text) < MAX_DIGITS:
            self.text += digit

    def backspace(self) -> None:
        self._prefilled = False
        self.text = self.text[:-1]

    def quantity(self) -> int:
        """当前录入数量：非法/空按 1，超上限钳到 max_value。"""
        try:
            n = int(self.text)
        except ValueError:
            n = 0
        n = max(1, n)
        if self.max_value > 0:
            n = min(n, self.max_value)
        return n

    def confirm(self) -> None:
        self.on_ok(self.quantity() if self.numeric else None)

    def cancel(self) -> None:
        if self.on_cancel is not None:
            self.on_cancel()

    def handle_keydown(self, key: int) -> bool:
        """弹框打开期间吃掉全部键；数字/退格/Enter/Esc 有语义。"""
        if pygame.K_0 <= key <= pygame.K_9:
            self.type_digit(str(key - pygame.K_0))
        elif pygame.K_KP0 <= key <= pygame.K_KP9:
            self.type_digit(str(key - pygame.K_KP0))
        elif key == pygame.K_BACKSPACE:
            self.backspace()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.confirm()
        elif key == pygame.K_ESCAPE:
            self.cancel()
        return True

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        """命中确认/取消/最大即执行；其余点击只消费。返回 True = 已处理。"""
        if self.ok_rect is not None and self.ok_rect.collidepoint(pos):
            self.confirm()
        elif self.max_rect is not None and self.max_rect.collidepoint(pos):
            self.text = str(max(1, self.max_value))
            self._prefilled = True
        elif self.cancel_rect is not None and self.cancel_rect.collidepoint(pos):
            self.cancel()
        return True

    # ── 绘制 ───────────────────────────────────────────────────────
    def draw(self, surface, svc) -> None:
        vw, vh = surface.get_width(), surface.get_height()
        f, fs = svc.ui.font, svc.ui.font_small
        w = 270
        h = 118 if self.numeric else 96
        x, y = (vw - w) // 2, (vh - h) // 2 - 20
        panel = pygame.Surface((w, h), pygame.SRCALPHA)
        panel.fill((24, 28, 38, 246))
        surface.blit(panel, (x, y))
        pygame.draw.rect(surface, (170, 160, 110), (x, y, w, h), 1,
                         border_radius=4)
        surface.blit(f.render(self.title, True, (255, 216, 96)), (x + 14, y + 8))
        row_y = y + 32
        if self.hint:
            surface.blit(fs.render(widgets.ellipsize(self.hint, fs, w - 28),
                                   True, (205, 210, 220)), (x + 14, row_y))
            row_y += 18
        qty = 0
        if self.numeric:
            box = pygame.Rect(x + 14, row_y, 120, 24)
            pygame.draw.rect(surface, (252, 252, 250), box, border_radius=3)
            pygame.draw.rect(surface, (110, 118, 134), box, 1, border_radius=3)
            caret = "▌" if int(pygame.time.get_ticks() / 500) % 2 == 0 else ""
            surface.blit(fs.render(self.text + caret, True, (30, 32, 38)),
                         (box.x + 6, box.y + 4))
            self.max_rect = pygame.Rect(box.right + 6, box.y, 40, 24)
            self._draw_button(surface, fs, self.max_rect, "最大",
                              (96, 84, 52), svc)
            row_y += 30
            if self.note is not None:
                qty = self.quantity()
                surface.blit(fs.render(
                    widgets.ellipsize(self.note(qty), fs, w - 28), True,
                    (150, 210, 160)), (x + 14, row_y))
                row_y += 16
        else:
            self.max_rect = None
        ok_w = 56 + max(0, (fs.size(self.ok_label)[0] - 28))
        self.ok_rect = pygame.Rect(x + w - 14 - ok_w, y + h - 34, ok_w, 24)
        cw = 56 + max(0, (fs.size(self.cancel_label)[0] - 28))
        self.cancel_rect = pygame.Rect(self.ok_rect.x - cw - 8, y + h - 34,
                                       cw, 24)
        self._draw_button(surface, fs, self.ok_rect, self.ok_label,
                          (52, 110, 78), svc)
        self._draw_button(surface, fs, self.cancel_rect, self.cancel_label,
                          (84, 70, 66), svc)
        foot = "数字键输入 · Enter 确认 · Esc 取消" if self.numeric \
            else "Enter 确认 · Esc 取消"
        surface.blit(fs.render(foot, True, (140, 146, 160)),
                     (x + 14, y + h - 18))

    @staticmethod
    def _draw_button(surface, fs, rect: pygame.Rect, label: str,
                     color: Tuple[int, int, int], svc) -> None:
        hover = rect.collidepoint(svc.mouse())
        base = tuple(min(255, c + 26) for c in color) if hover else color
        pygame.draw.rect(surface, base, rect, border_radius=4)
        pygame.draw.rect(surface, (150, 158, 175) if hover else (96, 102, 118),
                         rect, 1, border_radius=4)
        surface.blit(fs.render(label, True, (240, 240, 245)),
                     (rect.centerx - fs.size(label)[0] // 2,
                      rect.centery - fs.size(label)[1] // 2))
