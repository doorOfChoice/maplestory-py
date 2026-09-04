"""聊天框渲染：左下角半透明日志区 + 聚焦时的输入行。

原版布局的自制替身：日志贴左下、压在状态栏上方，输入行在最底（贴栏），
新消息永远可见；输入过长时只显示能贴进宽度的词尾（光标跟字符走）。
纯逻辑（聊天状态）在 core/chat.py，这里只读不写。
"""

from __future__ import annotations

from typing import Dict, Tuple

import pygame

from game.core.chat import Chat
from game.core.fonts import load_cjk_font, render_text

CHAT_W = 380                # 日志 / 输入区宽度
CHAT_MARGIN = 8             # 距屏边与状态栏的间距
CHAT_LINE_H = 15            # 日志行高
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
        self.font = load_cjk_font(11)

    def draw(self, surface, chat: Chat, bar_h: int) -> None:
        """绘制日志区（有内容才画底）与输入行（聚焦时画底）。"""
        vw, vh = surface.get_width(), surface.get_height()
        shown = chat.lines[-CHAT_VISIBLE_LINES:]
        if not shown and not chat.focused:
            return
        if shown:
            height = len(shown) * CHAT_LINE_H + 6
            rect = compute_chat_rect(vw, vh, bar_h, height)
            bg = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 110))
            surface.blit(bg, rect.topleft)
            y = rect.y + 3
            for line in shown:
                color = LINE_COLORS.get(line.kind, LINE_COLORS["player"])
                surface.blit(render_text(self.font, line.text, color),
                             (rect.x + 4, y))
                y += CHAT_LINE_H
        if chat.focused:
            ir = pygame.Rect(CHAT_MARGIN, vh - bar_h - CHAT_MARGIN - INPUT_H,
                             CHAT_W, INPUT_H)
            bg = pygame.Surface((ir.width, ir.height), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 150))
            surface.blit(bg, ir.topleft)
            pygame.draw.rect(surface, (150, 160, 178), ir, 1)
            caret = "▌" if int(pygame.time.get_ticks() / 500) % 2 == 0 else ""
            text = visible_tail(chat.text + caret, self.font, CHAT_W - 12)
            surface.blit(render_text(self.font, text, (255, 255, 255)),
                         (ir.x + 5, ir.y + 3))
