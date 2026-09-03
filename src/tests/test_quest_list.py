"""多任务选择列表（UtilDlgEx 面板）布局几何：面板高度随条目增长、条目行等距。"""
from __future__ import annotations

import os

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()

from game.render.ui import (
    UI, DLG_BOTTOM_H, DLG_LINE_H, DLG_TOP_H, DLG_TEXT_X, DLG_TEXT_W, DLG_W,
    LIST_ROW_H, LIST_PAD_TOP, LIST_PAD_BOTTOM, CONV_TEXT_LINK_GAP,
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
    ui.show_conv("任务", ["测" * 80], [], ["yes", "no"], False)
    ui.draw_quest(pygame.Surface((960, 540), pygame.SRCALPHA))
    assert ui.quest_rect.width == DLG_W
    assert DLG_TEXT_X + DLG_TEXT_W <= ui.quest_rect.width * 0.79


# ── show_conv 统一渲染契约 ─────────────────────────────────────────


def test_show_conv_body_counts_lines_and_links():
    """正文行数与蓝字行数共同决定面板高度（同一面板共存）。"""
    ui = UI(FakeAssets())
    ui.show_conv("T", ["a", "b", "c", "d"], [("l1", 0), ("l2", 5)], [], False)
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    ui.draw_quest(surface)
    # 4 黑行（高出 min 70 兜底、不触顶）+ 2 蓝字行：比只有黑行时高 2×LIST_ROW_H + 6 隔行
    only_lines = UI(FakeAssets())
    only_lines.show_conv("T", ["a", "b", "c", "d"], [], [], False)
    only_lines.draw_quest(pygame.Surface((960, 540), pygame.SRCALPHA))
    assert ui.quest_rect.height == only_lines.quest_rect.height + 2 * LIST_ROW_H + CONV_TEXT_LINK_GAP


def test_conv_link_hit_returns_index():
    """点击蓝字行区域 → 返回链接序号；空白处 None。"""
    ui = UI(FakeAssets())
    ui.show_conv("T", [], [("l1", 0), ("l2", 0)], [], False)
    ui.draw_quest(pygame.Surface((960, 540), pygame.SRCALPHA))
    rect0, idx0 = ui.quest_entry_rects[0]
    assert ui.conv_link_hit((rect0.centerx, rect0.centery)) == 0
    outside = (ui.quest_rect.centerx, ui.quest_rect.y + 3)
    assert ui.conv_link_hit(outside) is None


def test_show_conv_folds_all_slots_into_state():
    """统一会话状态：黑正文/蓝字链接/yes-no 按钮/终态各槽位独立装载。"""
    ui = UI(FakeAssets())
    ui.show_conv("Q", ["台词"], [("任务", 10)], ["yes", "no"], False)
    assert ui.quest_lines == ["台词"] and ui.quest_links == [("任务", 10)]
    assert ui.quest_button_keys == ["yes", "no"] and not ui.quest_terminal
    ui.show_conv("T", [], [], [], True)
    assert ui.quest_terminal and ui.quest_button_keys == []
