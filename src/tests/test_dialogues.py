"""NPC 寒暄台词：每个 NPC 有专属内容，未收录 NPC 回退到通用池，重复对话有变化。"""
from __future__ import annotations

from game.systems import dialogues


def test_known_npcs_get_distinct_dialogues():
    """两个不同 NPC 的台词内容不同（不再千篇一律）。"""
    a = dialogues.get_dialog("1012110", "小安")
    b = dialogues.get_dialog("1012119", "王年海")
    assert a and b
    assert a != b


def test_dialogue_matches_npc_own_pool():
    """返回的台词必须出自该 NPC 自己的台词池。"""
    for _ in range(20):
        got = dialogues.get_dialog("1012100", "赫丽娜")
        assert got in dialogues.DIALOGUES["1012100"]


def test_unknown_npc_falls_back_to_generic():
    """未收录 NPC 回退通用池：非空且不会撞上任何专属台词。"""
    got = dialogues.get_dialog("9999999", "路人")
    assert got
    owned = {tuple(s) for pool in dialogues.DIALOGUES.values() for s in pool}
    assert tuple(got) not in owned


def test_repeat_talk_varies():
    """同一 NPC 连续对话会出现不同套台词。"""
    seen = {tuple(dialogues.get_dialog("1012110", "小安")) for _ in range(50)}
    assert len(seen) >= 2
