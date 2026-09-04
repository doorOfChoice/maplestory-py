"""虚拟键盘布局：键盘窗绘制与拖拽落点的共享数据。

验证布局自身的公开数据（KEY_ROWS / key_units_total）：所有默认绑定键都
在布局内、格不重复、行宽不超首行（首行决定窗宽）。
"""

from __future__ import annotations

import pygame

from game.core.keybindings import ACTIONS
from game.core.keylayout import KEY_ROWS, key_units_total


def _all_codes() -> list:
    return [spec.key for row in KEY_ROWS for spec in row]


def test_default_bound_keys_all_in_layout():
    """每个动作的默认键都画得出来：布局漏键会让绑定无处显示。"""
    codes = set(_all_codes())
    missing = {a.id for a in ACTIONS if a.default not in codes}
    assert missing == set()


def test_layout_has_no_duplicate_cells():
    codes = _all_codes()
    assert len(codes) == len(set(codes))


def test_first_row_is_the_widest():
    """首行（Esc + 数字行）是最宽行，其余行按单位宽缩进对齐。"""
    totals = [key_units_total(row) for row in KEY_ROWS]
    assert all(t <= totals[0] for t in totals)


def test_arrow_cluster_present():
    codes = set(_all_codes())
    assert {pygame.K_LEFT, pygame.K_UP, pygame.K_DOWN, pygame.K_RIGHT} <= codes


def test_escape_in_layout_for_display():
    """Esc 在布局里展示（固定取消），窗口层负责把它排除出绑定目标。"""
    assert pygame.K_ESCAPE in set(_all_codes())
