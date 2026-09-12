"""NPC 视觉开关：info/hideName 隐藏名牌、info/float 悬空小幅浮动。"""

from __future__ import annotations

import pygame

from game.entities.npc import NPC


class _Assets:
    """只提供 NPC 建构所需查询的合成资产。"""

    def __init__(self, info: dict):
        self._info = info

    def npc_name(self, npc_id: str) -> str:
        return "测试"

    def npc_frames(self, npc_id: str, action: str = "stand"):
        return [(pygame.Surface((10, 10), pygame.SRCALPHA), 100)]

    def npc_origin(self, npc_id: str, action: str = "stand"):
        return (5, 10)

    def npc_info(self, npc_id: str) -> dict:
        return self._info


def _make(**info) -> NPC:
    data = {"id": "1012100", "x": 0, "y": 0, "cy": 0}
    return NPC(_Assets(info), data, 0)


def test_hide_name_flag_hides_plate():
    """info/hideName=1 → NPC 不显示头顶名牌。"""
    assert _make(hide_name=True).show_name is False


def test_name_shown_by_default():
    """无 hideName 标记时照常显示名牌。"""
    assert _make().show_name is True


def test_float_flag_bobs_vertically():
    """info/float=1 → 悬空 NPC 的垂直偏移随时间变化。"""
    npc = _make(float=True)
    offsets = set()
    for _ in range(60):
        npc.update(0.05)
        offsets.add(round(npc.float_offset(), 3))
    assert len(offsets) > 1


def test_float_offset_bounded():
    """悬空浮动幅度不超过设定的 ±4px。"""
    npc = _make(float=True)
    for _ in range(60):
        npc.update(0.05)
        assert abs(npc.float_offset()) <= 4.0


def test_non_float_has_no_offset():
    """未标记 float 的 NPC 恒贴地，无垂直偏移。"""
    npc = _make()
    npc.update(0.05)
    assert npc.float_offset() == 0.0
