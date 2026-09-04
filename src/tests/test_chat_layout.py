"""聊天框布局：日志区锚定左下角状态栏上方；输入行按尾字符截断跟随光标。"""

import os

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame.init()

from game.core.fonts import load_cjk_font
from game.render.chat import INPUT_H, compute_chat_rect, visible_tail


def test_chat_log_sits_above_input_line_at_left():
    """日志区左对齐屏边，底边压在输入行之上（输入行再贴住状态栏）。"""
    rect = compute_chat_rect(800, 600, bar_h=71, height=160)
    assert rect.left == 8
    assert rect.bottom == 600 - 71 - 8 - INPUT_H
    assert rect.width == 380


def test_visible_tail_keeps_suffix_that_fits():
    """超宽文本只保留贴得下的词尾（输入行随光标走）。"""
    font = load_cjk_font(11)
    text = "hello 冒险岛的聊天框真好用"
    room = font.size("聊天框真好用")[0]
    out = visible_tail(text, font, room)
    assert text.endswith(out)
    assert font.size(out)[0] <= room
    # 再往左多带一个字就放不下：说明取的是最大后缀
    assert font.size("的" + out)[0] > room
