"""聊天框渲染：左下角无底日志（白字黑描边）+ 聚焦时的输入行。

原版风格：日志不加黑底、直接叠在场景上；输入行用官方 StatusBar/base/chat
细线做底衬，过长时只显示能贴进宽度的词尾（光标跟字符走）。
纯逻辑（聊天状态）在 core/chat.py，这里只读不写。
"""

from __future__ import annotations

from typing import Dict, Tuple

import pygame

from game.core.chat import Chat
from game.core.fonts import load_cjk_font, render_text

CHAT_W = 380                # 日志 / 输入区宽度
CHAT_MARGIN = 8             # 距屏边与状态栏的间距
CHAT_LINE_H = 19            # 日志行高（随 12px 字号放大）
CHAT_VISIBLE_LINES = 8      # 日志最多同时显示的行数
INPUT_H = 20                # 输入行高

# 消息着色：发言白 / 系统黄 / 错误红
LINE_COLORS: Dict[str, Tuple[int, int, int]] = {
    "player": (240, 240, 245),
    "system": (255, 233, 107),
    "error": (255, 120, 120),
}


def compute_chat_rect(vw: int, vh: int, bar_h: int, height: int) -> pygame.Rect:
    """聊天日志区矩形：左对齐屏边、底边压在状态栏上方（输入行之上）。"""
    return pygame.Rect(CHAT_MARGIN, vh - bar_h - CHAT_MARGIN - height - INPUT_H,
                       CHAT_W, height)


def visible_tail(text: str, font: pygame.font.Font, max_w: int) -> str:
    """按像素宽截取文本后缀，保证光标端的字符始终可见。"""
    if font.size(text)[0] <= max_w:
        return text
    for i in range(len(text)):          # 从最左可行起点 → 最长可贴边后缀
        if font.size(text[i:])[0] <= max_w:
            return text[i:]
    return ""


class ChatView:
    def __init__(self) -> None:
        self.font = load_cjk_font(12)

    def draw(self, surface, chat: Chat, bar_h: int, assets=None) -> None:
        """绘制日志区（原版无底、描边字）与输入行（官方 chat 细线做底衬）。"""
        vw, vh = surface.get_width(), surface.get_height()
        shown = chat.lines[-CHAT_VISIBLE_LINES:]
        if not shown and not chat.focused:
            return
        if shown:
            height = len(shown) * CHAT_LINE_H + 6
            rect = compute_chat_rect(vw, vh, bar_h, height)
            y = rect.y + 3
            for line in shown:
                color = LINE_COLORS.get(line.kind, LINE_COLORS["player"])
                self._blit_outlined(surface, line.text, rect.x + 4, y, color)
                y += CHAT_LINE_H
        if chat.focused:
            ir = pygame.Rect(CHAT_MARGIN, vh - bar_h - CHAT_MARGIN - INPUT_H,
                             CHAT_W, INPUT_H)
            caret = "▌" if int(pygame.time.get_ticks() / 500) % 2 == 0 else ""
            text = visible_tail(chat.text + caret, self.font, CHAT_W - 12)
            self._blit_outlined(surface, text, ir.x + 4, ir.y, (255, 255, 255))
            line = None
            if assets is not None:
                from game.render.conv import ui_image
                line = ui_image(assets, "StatusBar.img", "base/chat")
            if line is not None:
                line = pygame.transform.scale(line, (CHAT_W, line.get_height()))
                surface.blit(line, (ir.x, ir.bottom - line.get_height()))
            else:
                pygame.draw.line(surface, (150, 160, 178),
                                 (ir.x, ir.bottom - 1), (ir.right, ir.bottom - 1))

    def _blit_outlined(self, surface, text: str, x: int, y: int,
                       color: Tuple[int, int, int]) -> None:
        """白字黑描边（1px 八向）：原版聊天/名字的通用画法。"""
        shadow = render_text(self.font, text, (0, 0, 0))
        main = render_text(self.font, text, color)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surface.blit(shadow, (x + dx, y + dy))
        surface.blit(main, (x, y))
