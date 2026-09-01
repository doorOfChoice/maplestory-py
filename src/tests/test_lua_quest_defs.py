"""Lua 自定义任务定义：验证 quests() 翻译成 QuestDef 的字段映射与边界。

透过公开 seam _quest_to_def 测试；用 lupa 快捷建表构造输入，不依赖 WZ。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from lupa import LuaRuntime

from game.systems.lua_quests import _ints, _lines, _pairs, _quest_to_def, load_lua_quest_defs, build_advance_quest_defs
from game.systems.quests import QuestDef, QuestLog, collect_npc_quests

pytest.importorskip("lupa")

_rt = LuaRuntime(unpack_returned_tuples=True, register_eval=False)


def T(*args, **kwargs):
    """快捷建 lupa table。"""
    return _rt.table(*args, **kwargs)


def test_pairs_empty():
    """None 输入返回空列表。"""
    assert _pairs(None) == []


def test_pairs_normal():
    """[[id, count], ...] 折成 [(int, int), ...]。"""
    tbl = T(T(2000000, 3), T(100, 5))
    assert _pairs(tbl) == [(2000000, 3), (100, 5)]


def test_ints_empty():
    """None 输入返回空列表。"""
    assert _ints(None) == []


def test_ints_normal():
    """数组折成 int 列表。"""
    assert _ints(T(0, 3000)) == [0, 3000]


def test_lines_empty():
    """None 输入返回空列表。"""
    assert _lines(None) == []


def test_lines_normal():
    """数组折成 str 列表。"""
    assert _lines(T("你好", "冒险家")) == ["你好", "冒险家"]


def test_quest_to_def_minimal():
    """最小字段：只给 name, lvmin, kills, reward_exp。"""
    tbl = T(
        name="红药水收集",
        lvmin=1,
        kills=T(T(100, 5)),
        reward_exp=100,
        accept_lines=T("要接受吗？"),
        accept_yes=T("已接受"),
        complete_lines=T("完成了吗？"),
        complete_yes=T("奖励发放"),
        complete_stop=T("还差一些"),
    )
    d = _quest_to_def("1012100", 1, tbl)
    assert d is not None
    assert d.qid == "c_1012100_1"
    assert d.name == "红药水收集"
    assert d.lvmin == 1
    assert d.start_npc == 1012100
    assert d.end_npc == 1012100
    assert d.kills == [(100, 5)]
    assert d.reward_exp == 100
    assert d.accept_lines == ["要接受吗？"]


def test_quest_to_def_with_start_npc():
    """显式 start_npc 可覆盖文件名的 NPC id。"""
    tbl = T(name="跨 NPC 任务", start_npc=1012100, end_npc=1012110,
            accept_lines=T("ok"), complete_lines=T("done"))
    d = _quest_to_def("1012110", 1, tbl)
    assert d.start_npc == 1012100
    assert d.end_npc == 1012110


def test_quest_to_def_missing_name_is_skipped():
    """没有 name 字段的任务返回 None。"""
    tbl = T(accept_lines=T("no name"))
    assert _quest_to_def("1012100", 1, tbl) is None


def test_quest_to_def_full_fields():
    """所有可选字段完整翻译。"""
    tbl = T(
        name="完整任务",
        lvmin=10, lvmax=50, jobs=T(0, 3000),
        start_items=T(T(100, 1)),
        prereq=T(T(1000, 2)),
        kills=T(T(100, 5)),
        end_items=T(T(2000000, 3)),
        accept_items=T(T(100, 1)),
        reward_exp=500, reward_money=1000,
        reward_items=T(T(2000000, 2)),
        next_quest=2001,
        accept_lines=T("a1", "a2"),
        accept_yes=T("ay"),
        accept_no=T("an"),
        complete_lines=T("c1"),
        complete_yes=T("cy"),
        complete_stop=T("cs"),
        parent="p1", order=1, area=2,
        desc0="d0", desc1="d1", desc2="d2",
    )
    d = _quest_to_def("1012100", 1, tbl)
    assert d.lvmax == 50
    assert d.jobs == [0, 3000]
    assert d.start_items == [(100, 1)]
    assert d.prereq == [(1000, 2)]
    assert d.kills == [(100, 5)]
    assert d.end_items == [(2000000, 3)]
    assert d.accept_items == [(100, 1)]
    assert d.reward_exp == 500
    assert d.reward_money == 1000
    assert d.reward_items == [(2000000, 2)]
    assert d.next_quest == 2001
    assert d.accept_lines == ["a1", "a2"]


# ── 加载器：目录扫描 + 沙箱执行 ──────────────────────────────────────────

def _write_script(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


def test_load_lua_quest_defs_single_npc():
    """单个 NPC 脚本定义 2 个任务，返回正确的 qid 和字段。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_script(tmp, "1012100.lua", """\
local M = {}
function M.quests(ctx)
  return {
    { name = "任务1", lvmin=1, accept_lines = {"a1"}, complete_lines = {"c1"} },
    { name = "任务2", lvmin=5, end_items = {{2000000, 3}},
      accept_lines = {"a2"}, complete_lines = {"c2"} },
  }
end
return M
""")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert len(defs) == 2
        assert "c_1012100_1" in defs
        assert defs["c_1012100_1"].name == "任务1"
        assert defs["c_1012100_1"].lvmin == 1
        assert defs["c_1012100_1"].start_npc == 1012100
        assert "c_1012100_2" in defs
        assert defs["c_1012100_2"].end_items == [(2000000, 3)]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_lua_quest_defs_two_npcs():
    """两个 NPC 脚本，各自任务都能正确加载。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_script(tmp, "1012100.lua", """\
local M = {}
function M.quests(ctx) return {{ name = "N1", accept_lines = {"a"}, complete_lines = {"c"} }} end
return M
""")
        _write_script(tmp, "1012119.lua", """\
local M = {}
function M.quests(ctx) return {{ name = "N2", accept_lines = {"b"}, complete_lines = {"d"} }} end
return M
""")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert len(defs) == 2
        assert "c_1012100_1" in defs
        assert "c_1012119_1" in defs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_lua_quest_defs_no_quests():
    """脚本没有 quests 函数，跳过。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_script(tmp, "empty.lua", "local M = {} return M\n")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert defs == {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_lua_quest_defs_one_bad_skip():
    """多条任务中一条翻译失败，不拖垮其余。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        _write_script(tmp, "1012100.lua", """\
local M = {}
function M.quests(ctx)
  return {
    { name = "good", accept_lines = {"a"}, complete_lines = {"c"} },
    { },  -- 没 name → 跳过
    { name = "also_good", accept_lines = {"b"}, complete_lines = {"d"} },
  }
end
return M
""")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert len(defs) == 2
        assert "c_1012100_1" in defs
        assert "c_1012100_3" in defs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_collect_npc_quests_merges_lua_and_wz():
    """collect_npc_quests 能同时找到官方和自定义任务（qid 不冲突）。"""
    wz_defs = {
        "1000": QuestDef(qid="1000", name="WZ任务", start_npc=1012100,
                         end_npc=1012100, lvmin=1,
                         accept_lines=["a"], complete_lines=["c"]),
    }
    lua_defs = {
        "c_1012100_1": QuestDef(qid="c_1012100_1", name="Lua任务",
                                start_npc=1012100, end_npc=1012100,
                                lvmin=1,
                                accept_lines=["b"], complete_lines=["d"]),
    }
    defs = {**wz_defs, **lua_defs}
    log = QuestLog(defs)
    player = SimpleNamespace(level=10, job=0, x=0.0, y=0.0,
                             inventory=SimpleNamespace(etcs={}, consumes={}))
    items = collect_npc_quests(defs, log, "1012100", player)
    assert len(items) == 2
    qids = [it.qid for it in items]
    assert "1000" in qids
    assert "c_1012100_1" in qids


def test_trainer_newbie_quest_def():
    """转职教官 1012100 的新手任务：新手专属、击杀蓝宝、有奖励。"""
    defs = load_lua_quest_defs()
    d = defs.get("c_1012100_1")
    assert d is not None
    assert d.name == "新手入门"
    assert d.start_npc == 1012100
    assert d.end_npc == 1012100
    assert d.jobs == [0]
    assert d.kills == [(100101, 10)]
    assert d.reward_exp == 200
    assert d.reward_money == 200


def test_trainer_newbie_quest_lifecycle():
    """新手任务接取后可随击杀推进，凑满 10 只蓝宝即可完成。"""
    defs = {**load_lua_quest_defs(), **build_advance_quest_defs()}
    log = QuestLog(defs)
    player = SimpleNamespace(level=5, job=0, x=0.0, y=0.0,
                             inventory=SimpleNamespace(etcs={}, consumes={}))
    assert log.accept("c_1012100_1", player)
    for _ in range(5):
        log.on_kill(100101)
    assert not log.can_complete("c_1012100_1", player)
    for _ in range(5):
        log.on_kill(100101)
    assert log.can_complete("c_1012100_1", player)
    assert log.kill_progress("c_1012100_1", 100101) == 10


def test_trainer_quests_merge_newbie_and_advance():
    """新手对话转职教官时，新手任务与转职任务同时出现在可接列表。"""
    defs = {**load_lua_quest_defs(), **build_advance_quest_defs()}
    log = QuestLog(defs)
    player = SimpleNamespace(level=5, job=0, x=0.0, y=0.0,
                             inventory=SimpleNamespace(etcs={}, consumes={}))
    items = collect_npc_quests(defs, log, "1012100", player)
    assert [it.qid for it in items] == ["c_1012100_1", "adv_3000"]


def test_build_advance_quest_defs():
    """有导师的职业生成转职任务：script=advance，接取条件为前置职业（lvmin 不限等级）。"""
    defs = build_advance_quest_defs()
    assert "adv_3000" in defs
    d = defs["adv_3000"]
    assert d.name == "转职：弓箭手"
    assert d.script == "advance"
    assert d.start_npc == 1012100
    assert d.end_npc == 1012100
    assert d.lvmin == 0
    assert d.jobs == [0]


def test_build_advance_quest_defs_trainer_collect():
    """转职任务出现在其导师 NPC 的可接列表里（玩家为前置职业且达标）。"""
    defs = build_advance_quest_defs()
    log = QuestLog(defs)
    player = SimpleNamespace(level=10, job=0, x=0.0, y=0.0,
                             inventory=SimpleNamespace(etcs={}, consumes={}))
    items = collect_npc_quests(defs, log, "1012100", player)
    assert [it.qid for it in items] == ["adv_3000"]


def test_build_advance_quest_defs_hidden_after_job():
    """已转职（job=3000）后，转职任务不再出现在列表。"""
    defs = build_advance_quest_defs()
    log = QuestLog(defs)
    player = SimpleNamespace(level=30, job=3000, x=0.0, y=0.0,
                             inventory=SimpleNamespace(etcs={}, consumes={}))
    items = collect_npc_quests(defs, log, "1012100", player)
    assert items == []
