"""出租车传送：Lua entries() 按类型翻译 + travel 传送注册表。"""

from __future__ import annotations

from game.core import travel
from game.systems.lua_quests import load_lua_quest_defs

_MIXED_LUA = """
local M = {}
function M.entries(ctx)
  return {
    { type = "quest", name = "打地兽", lvmin = 5, kills = { { 100101, 3 } } },
    { type = "teleport", label = "射手村", map = "100000000" },
    { type = "teleport", label = "废弃都市", map = "103000000" },
    { type = "warp_whatever", label = "未知类型" },
  }
end
return M
"""


def _write(dir, name: str, src: str) -> None:
    (dir / name).write_text(src, encoding="utf-8")


def test_entries_split_by_type(tmp_path):
    """entries() 里 quest 条目进任务表、teleport 条目进传送注册表、未知类型跳过。"""
    travel.clear_teleports()
    _write(tmp_path, "9900001.lua", _MIXED_LUA)
    defs = load_lua_quest_defs(tmp_path)
    assert len(defs) == 1
    d = next(iter(defs.values()))
    assert d.name == "打地兽"
    assert d.start_npc == 9900001
    assert travel.teleports_of("9900001") == [
        ("射手村", "100000000"), ("废弃都市", "103000000")]


def test_teleports_exclude_current_map(tmp_path):
    """已在目的地图时，该目的地从菜单剔除。"""
    travel.clear_teleports()
    _write(tmp_path, "9900002.lua", _MIXED_LUA)
    load_lua_quest_defs(tmp_path)
    names = [n for n, _ in travel.teleports_of("9900002", "100000000")]
    assert names == ["废弃都市"]


def test_legacy_quests_fn_not_loaded(tmp_path):
    """旧契约 quests() 不再被识别。"""
    travel.clear_teleports()
    _write(tmp_path, "9900003.lua",
           "local M = {}\nfunction M.quests(ctx) return { { name='x' } } end\nreturn M\n")
    assert load_lua_quest_defs(tmp_path) == {}


def test_four_town_taxis_have_destinations():
    """四大城镇出租车 NPC 的真实 lua 各注册四个目的地。"""
    travel.clear_teleports()
    load_lua_quest_defs()
    expected = {"废弃都市": "103000000", "射手村": "100000000",
                "魔法密林": "101000000", "勇士部落": "102000000"}
    for npc_id in ("1012000", "1022001", "1032000", "1052016"):
        assert dict(travel.teleports_of(npc_id, "999999999")) == expected
