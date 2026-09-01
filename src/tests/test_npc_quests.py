"""NPC 可接/可交付任务收集：按 NPC 过滤 QuestDef，交付优先于接取。"""
from __future__ import annotations

from types import SimpleNamespace

from game.systems.quests import NpcQuest, QuestDef, QuestLog, collect_npc_quests


def make_defs() -> dict:
    offer = QuestDef(qid="1", name="弓箭手入门", start_npc=1012100, lvmin=10,
                     end_items=[(4000019, 1)])
    handin = QuestDef(qid="2", name="回报师傅", start_npc=1012101, end_npc=1012100,
                      lvmin=10, kills=[(1210102, 3)])
    other = QuestDef(qid="3", name="别处任务", start_npc=9999999, lvmin=10)
    return {"1": offer, "2": handin, "3": other}


def make_player():
    return SimpleNamespace(level=10, job=0, x=0.0, y=0.0,
                           inventory=SimpleNamespace(etcs={}, consumes={}))


def test_offerable_quest_of_npc_returned():
    """NPC 的可接任务被收集，含名称与等级。"""
    defs = make_defs()
    log = QuestLog(defs)
    got = collect_npc_quests(defs, log, "1012100", make_player())
    assert [q.qid for q in got] == ["1"]
    assert got[0].title == "弓箭手入门"
    assert got[0].level == 10
    assert got[0].state == "offer"


def test_deliverable_precedes_offerable():
    """同一 NPC 可交付任务排在可接任务之前。"""
    defs = make_defs()
    log = QuestLog(defs)
    # 接取并完成「回报师傅」的击杀条件
    log.status["2"] = "accepted"
    log.kills["2"] = {1210102: 3}
    got = collect_npc_quests(defs, log, "1012100", make_player())
    assert [q.qid for q in got] == ["2", "1"]
    assert [q.state for q in got] == ["complete", "offer"]


def test_other_npc_quest_excluded():
    """不改动本 NPC 的任务不出现。"""
    defs = make_defs()
    log = QuestLog(defs)
    got = collect_npc_quests(defs, log, "1012100", make_player())
    assert "3" not in [q.qid for q in got]


def test_force_complete_marks_completed_without_rewards():
    """force_complete 直接把任务置为已完成，不发任何奖励。"""
    defs = make_defs()
    log = QuestLog(defs)
    player = make_player()
    log.force_complete("1")
    assert log.is_completed("1")
    # 不触发 accept（无 accept_items），也不走 complete（无 reward 结算）
    assert log.started("1")
    # 完成后不再出现在可接列表
    got = collect_npc_quests(defs, log, "1012100", player)
    assert [q.qid for q in got] == []


def test_force_complete_unknown_qid_noop():
    """不存在的 qid 调用 force_complete 不报错。"""
    defs = make_defs()
    log = QuestLog(defs)
    log.force_complete("99999")
    assert not log.started("99999") or log.is_completed("99999")
