"""多任务选择列表（UtilDlgEx 面板）布局几何：面板高度随条目增长、条目行等距。"""
from __future__ import annotations

import os

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()

from game.render.ui import (
    UI, DLG_TOP_H, DLG_TEXT_X, DLG_TEXT_W, DLG_W,
    LIST_ROW_H, LIST_PAD_TOP, LIST_PAD_BOTTOM,
)
from tests.fake_assets import FakeAssets


def test_body_height_grows_with_rows():
    """条目越多正文越高；空列表仍有最小高度。"""
    assert UI.quest_list_body_height(0) == max(70, LIST_PAD_TOP + LIST_PAD_BOTTOM)
    assert UI.quest_list_body_height(3) == LIST_PAD_TOP + 3 * LIST_ROW_H + LIST_PAD_BOTTOM


def test_row_rects_start_below_title_and_advance():
    """条目行从（顶栏 + 留白）起，逐行等距下移，宽度内缩避开边框。"""
    x, y, w = 10, 100, 560
    rows = UI.quest_list_row_rects(x, y, w, 2)
    assert rows[0] == (x + DLG_TEXT_X, y + DLG_TOP_H + LIST_PAD_TOP,
                       w - 2 * DLG_TEXT_X, LIST_ROW_H)
    assert rows[1][1] == rows[0][1] + LIST_ROW_H
    assert rows[1][0] == rows[0][0]


def test_single_quest_dialog_keeps_native_width():
    """单任务对话框面板用原生宽 DLG_W：文字换行区（16+348）不越出 ic 白纸区。"""
    ui = UI(FakeAssets())
    ui.show_quest("任务", ["测" * 80], ["yes", "no"])
    ui.draw_quest(pygame.Surface((960, 540), pygame.SRCALPHA))
    assert ui.quest_rect.width == DLG_W
    assert DLG_TEXT_X + DLG_TEXT_W <= ui.quest_rect.width * 0.79
