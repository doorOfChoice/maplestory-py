"""虚拟键盘布局：键盘窗绘制与拖拽落点的共享数据。

验证布局自身的公开数据（KEY_ROWS / key_units_total）：所有默认绑定键都
在布局内、格不重复、行宽不超首行（首行决定窗宽）。
"""

from __future__ import annotations

import pygame

from game.core.keybindings import ACTIONS
from game.core.keylayout import (KEY_ROWS, key_units_total,
                                 keyboard_width_units)


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


def test_width_basis_is_widest_row():
    """窗宽基准 = 全行最大单位宽（F 功能行比数字行窄也不能把窗缩掉）。"""
    totals = [key_units_total(row) for row in KEY_ROWS]
    assert keyboard_width_units() == max(totals)
    # F1~F12 功能行已入列（手动存档默认 F5 可显示 / 可改绑）
    codes = set(_all_codes())
    assert {pygame.K_F1, pygame.K_F5, pygame.K_F12} <= codes


def test_arrow_cluster_present():
    codes = set(_all_codes())
    assert {pygame.K_LEFT, pygame.K_UP, pygame.K_DOWN, pygame.K_RIGHT} <= codes


def test_escape_in_layout_for_display():
    """Esc 在布局里展示（固定取消），窗口层负责把它排除出绑定目标。"""
    assert pygame.K_ESCAPE in set(_all_codes())
