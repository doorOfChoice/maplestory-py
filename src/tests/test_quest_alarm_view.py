"""可接任务列表面板（QuestAlarmView）布局几何：九宫高度、条目行位置。"""
from __future__ import annotations

from game.render.quest_alarm import (
    QuestAlarmView, TILE_TOP_H, TILE_BOT_H, ROW_H, PAD_TOP,
)


def test_panel_height_grows_with_rows():
    """面板高度 = 顶帽 + 留白 + 行数×行高 + 底帽。"""
    assert QuestAlarmView.panel_height(0) == TILE_TOP_H + PAD_TOP + TILE_BOT_H
    assert QuestAlarmView.panel_height(3) == TILE_TOP_H + PAD_TOP + 3 * ROW_H + TILE_BOT_H


def test_row_rects_start_below_top_and_advance():
    """条目行从（顶帽+留白）起，逐行等距下移，宽度铺满。"""
    x, y, w = 10, 100, 200
    rows = QuestAlarmView.row_rects(x, y, w, 2)
    assert rows[0] == (x, y + TILE_TOP_H + PAD_TOP, w, ROW_H)
    assert rows[1] == (x, y + TILE_TOP_H + PAD_TOP + ROW_H, w, ROW_H)
