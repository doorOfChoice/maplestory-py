"""NPC 寒暄台词：每个 NPC 有专属内容，未收录 NPC 回退到通用池，重复对话有变化。

同时测试 Lua 动态注册的台词池（register_lua_dialogue）。
"""
from __future__ import annotations

from game.systems import dialogues
from game.systems.lua_quests import load_lua_quest_defs

load_lua_quest_defs()


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
    owned = {tuple(s) for s in dialogues.DIALOGUES.values() for s in s}
    assert tuple(got) not in owned


def test_repeat_talk_varies():
    """同一 NPC 连续对话会出现不同套台词。"""
    seen = {tuple(dialogues.get_dialog("1012110", "小安")) for _ in range(50)}
    assert len(seen) >= 2


def test_lua_dialogue_overrides_hardcoded():
    """Lua 注册的台词优先于硬编码配置。"""
    dialogues.register_lua_dialogue("1012100", [["Lua 台词 A", "Lua 台词 B"]])
    got = dialogues.get_dialog("1012100", "赫丽娜")
    assert got == ["Lua 台词 A", "Lua 台词 B"]
    # 清理
    dialogues.DIALOGUES.pop("1012100", None)


def test_lua_dialogue_for_unknown_npc():
    """Lua 注册的台词可用于未在硬编码中的 NPC。"""
    dialogues.register_lua_dialogue("9999998", [["Lua 专属台词"]])
    got = dialogues.get_dialog("9999998", "测试NPC")
    assert got == ["Lua 专属台词"]
    # 清理
    dialogues.DIALOGUES.pop("9999998", None)