"""会话面板 ConvPanel：布局几何（面板高度随条目增长、条目行等距）与统一渲染契约。"""
from __future__ import annotations

import os

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()

from game.render.conv import (
    ConvPanel, DLG_BOTTOM_H, DLG_LINE_H, DLG_TOP_H, DLG_TEXT_X, DLG_TEXT_W,
    DLG_W, LIST_ROW_H, LIST_PAD_TOP, LIST_PAD_BOTTOM, MAX_BODY_H,
    CONV_TEXT_LINK_GAP,
)
from tests.fake_assets import FakeAssets


def test_body_height_grows_with_rows():
    """条目越多正文越高；空列表仍有最小高度。"""
    assert ConvPanel.list_body_height(0) == max(70, LIST_PAD_TOP + LIST_PAD_BOTTOM)
    assert ConvPanel.list_body_height(3) == LIST_PAD_TOP + 3 * LIST_ROW_H + LIST_PAD_BOTTOM


def test_row_rects_start_below_title_and_advance():
    """条目行从（顶栏 + 留白）起，逐行等距下移，宽度内缩避开边框。"""
    x, y, w = 10, 100, 560
    rows = ConvPanel.row_rects(x, y, w, 2)
    assert rows[0] == (x + DLG_TEXT_X, y + DLG_TOP_H + LIST_PAD_TOP,
                       w - 2 * DLG_TEXT_X, LIST_ROW_H)
    assert rows[1][1] == rows[0][1] + LIST_ROW_H
    assert rows[1][0] == rows[0][0]


def test_single_quest_dialog_keeps_native_width():
    """单任务对话框面板用原生宽 DLG_W：文字换行区（16+348）不越出 ic 白纸区。"""
    panel = ConvPanel(FakeAssets())
    panel.show("任务", ["测" * 80], [], ["yes", "no"], False)
    panel.draw(pygame.Surface((960, 540), pygame.SRCALPHA))
    assert panel.rect.width == DLG_W
    assert DLG_TEXT_X + DLG_TEXT_W <= panel.rect.width * 0.79


# ── ConvPanel.show 统一渲染契约 ────────────────────────────────────


def test_show_body_counts_lines_and_links():
    """正文行数与蓝字行数共同决定面板高度（同一面板共存）。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", ["a", "b", "c", "d"], [("l1", 0), ("l2", 5)], [], False)
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    panel.draw(surface)
    # 4 黑行（高出 min 70 兜底、不触顶）+ 2 蓝字行：比只有黑行时高 2×LIST_ROW_H + 6 隔行
    only_lines = ConvPanel(FakeAssets())
    only_lines.show("T", ["a", "b", "c", "d"], [], [], False)
    only_lines.draw(pygame.Surface((960, 540), pygame.SRCALPHA))
    assert panel.rect.height == only_lines.rect.height + 2 * LIST_ROW_H + CONV_TEXT_LINK_GAP


def test_link_hit_returns_index():
    """点击蓝字行区域 → 返回链接序号；空白处 None。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], [("l1", 0), ("l2", 0)], [], False)
    panel.draw(pygame.Surface((960, 540), pygame.SRCALPHA))
    rect0, idx0 = panel.entry_rects[0]
    assert panel.link_hit((rect0.centerx, rect0.centery)) == 0
    outside = (panel.rect.centerx, panel.rect.y + 3)
    assert panel.link_hit(outside) is None


# ── 定高视口：正文超限封顶 + 滚轮滚动 ──────────────────────────────


def many_links(n: int):
    return [(f"任务{i}", 0) for i in range(n)]


def draw_panel(panel: ConvPanel) -> pygame.Surface:
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    panel.draw(surface)
    return surface


def test_body_height_capped_when_rows_exceed():
    """条目超出上限时面板正文固定为 MAX_BODY_H，不再纵向撑满屏幕。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    assert panel.rect.height == DLG_TOP_H + MAX_BODY_H + DLG_BOTTOM_H


def test_only_visible_rows_are_clickable():
    """滚动视口外（或被裁切到不可见）的条目行不注册热区。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    assert 0 < len(panel.entry_rects) < 40
    body = pygame.Rect(panel.rect.x, panel.rect.y + DLG_TOP_H,
                       panel.rect.width, MAX_BODY_H)
    assert all(body.contains(rect) for rect, _ in panel.entry_rects)


def test_wheel_scrolls_link_rows():
    """视口内滚轮下滚 → 条目整体上移、首条索引前移，link_hit 仍命中正确条目。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    assert panel.entry_rects[0][1] == 0
    assert panel.handle_wheel(panel.rect.center, 1)
    draw_panel(panel)
    assert panel.entry_rects[0][1] == 0        # 行 0 尚部分可见 → 仍可点
    assert panel.handle_wheel(panel.rect.center, 1)
    draw_panel(panel)
    assert panel.entry_rects[0][1] == 1        # 滚出两行后首条热区为行 1
    rect, idx = panel.entry_rects[0]
    assert panel.link_hit(rect.center) == idx


def test_wheel_clamped_at_both_edges():
    """滚到底/顶后偏移钳制不越界；底缘仍能看到最后一条。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    for _ in range(60):
        panel.handle_wheel(panel.rect.center, 1)
    draw_panel(panel)
    assert panel.entry_rects[-1][1] == 39
    bottom = panel.scroll
    panel.handle_wheel(panel.rect.center, 1)
    assert panel.scroll == bottom
    for _ in range(60):
        panel.handle_wheel(panel.rect.center, -1)
    assert panel.scroll == 0


def test_wheel_outside_panel_not_consumed():
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    assert not panel.handle_wheel((5, 5), 1)
    assert panel.scroll == 0


def test_link_text_drawn_inside_row_rect():
    """链接文字必须落在条目热区内（回归：scratch 局部坐标不得带面板绝对偏移）。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], [("拾取物品", 10)], [], False)
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    surface.fill((255, 255, 255, 255))
    panel.draw(surface)
    rect, _ = panel.entry_rects[0]
    blues = [xx for yy in range(rect.top, rect.bottom)
             for xx in range(surface.get_width())
             if surface.get_at((xx, yy))[2] > 150 and surface.get_at((xx, yy))[0] < 120]
    assert blues
    assert all(rect.left <= xx <= rect.right for xx in blues)


def test_show_resets_scroll():
    """装载新快照（切步骤）滚动位置回顶。"""
    panel = ConvPanel(FakeAssets())
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    panel.handle_wheel(panel.rect.center, 1)
    panel.show("T", [], many_links(40), [], False)
    draw_panel(panel)
    assert panel.scroll == 0
    assert panel.entry_rects[0][1] == 0


# ── NPC 立绘：右侧米色空区 ──────────────────────────────────────────


class PortraitAssets(FakeAssets):
    """npc_frames 返回一块可辨识的纯色立绘，供像素级断言。"""

    def npc_frames(self, npc_id, action="stand", flip=False):
        img = pygame.Surface((60, 90), pygame.SRCALPHA)
        img.fill((233, 30, 99, 255))
        return [(img, (0, 0))]


def pink_pixels(surface) -> list:
    import numpy as np

    arr = pygame.surfarray.array3d(surface)
    mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] < 80) \
        & (arr[:, :, 2] > 80) & (arr[:, :, 2] < 160)
    xs, ys = np.nonzero(mask)
    return list(zip(xs.tolist(), ys.tolist()))


def test_npc_portrait_drawn_in_right_strip():
    """会话锚定 NPC：立绘落在白纸文字区右侧的米色空带、正文视口内。"""
    panel = ConvPanel(PortraitAssets())
    panel.show("T", [], [("l", 0)], [], False, npc_id="1012100")
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    panel.draw(surface)
    pts = pink_pixels(surface)
    assert pts
    left = panel.rect.x + DLG_TEXT_W + 2 * DLG_TEXT_X
    assert all(x >= left for x, _ in pts)
    top, bottom = min(y for _, y in pts), max(y for _, y in pts)
    assert all(panel.rect.y + DLG_TOP_H <= y < panel.rect.bottom - DLG_BOTTOM_H
               for _, y in pts)
    # 上下居中：立绘在正文视口内的上下留白相等（±1px 取整误差）
    body_top = panel.rect.y + DLG_TOP_H
    body_bot = panel.rect.bottom - DLG_BOTTOM_H
    assert abs((top - body_top) - ((body_bot - 1) - bottom)) <= 1


def test_npc_portrait_absent_without_npc():
    """未锚定 NPC：不画立绘。"""
    panel = ConvPanel(PortraitAssets())
    panel.show("T", [], [("l", 0)], [], False)
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    panel.draw(surface)
    assert not pink_pixels(surface)


def test_show_folds_all_slots_into_state():
    """统一会话状态：黑正文/蓝字链接/yes-no 按钮/终态各槽位独立装载。"""
    panel = ConvPanel(FakeAssets())
    panel.show("Q", ["台词"], [("任务", 10)], ["yes", "no"], False)
    assert panel.lines == ["台词"] and panel.links == [("任务", 10)]
    assert panel.button_keys == ["yes", "no"] and not panel.terminal
    panel.show("T", [], [], [], True)
    assert panel.terminal and panel.button_keys == []
