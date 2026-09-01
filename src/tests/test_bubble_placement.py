"""对话气泡定位：浮在 NPC 头顶、尖尾指向 NPC、贴边时夹紧不出屏。"""
from __future__ import annotations

from game.render.ui import compute_bubble_rect


def test_bubble_centers_above_npc():
    """屏幕中央的 NPC：气泡水平居中于 NPC，底缘（含尖尾）悬在头顶上方。"""
    x, y, tail_x = compute_bubble_rect(
        npc_sx=480, npc_top_sy=300, w=200, h=80, tail_w=24, tail_h=14,
        vw=960, vh=540)
    assert x == 380                       # 480 - 200/2
    assert y == 300 - 80 - 14 - 6         # 头顶 - 泡高 - 尾高 - 间隙
    assert tail_x + 12 == 480             # 尖尾正对 NPC


def test_bubble_clamped_horizontally_but_tail_still_points():
    """NPC 贴近左缘：气泡夹回屏内，但尖尾仍指向 NPC 所在列。"""
    x, y, tail_x = compute_bubble_rect(
        npc_sx=30, npc_top_sy=300, w=200, h=80, tail_w=24, tail_h=14,
        vw=960, vh=540)
    assert x >= 4
    assert tail_x <= 30 <= tail_x + 24


def test_bubble_clamped_below_screen_top():
    """NPC 头顶贴近屏幕上缘：气泡不会露出屏幕顶部。"""
    x, y, tail_x = compute_bubble_rect(
        npc_sx=480, npc_top_sy=40, w=200, h=80, tail_w=24, tail_h=14,
        vw=960, vh=540)
    assert y >= 4
