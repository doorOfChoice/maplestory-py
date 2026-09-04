"""世界存在性过滤：只保留 start_npc/end_npc/击杀怪真实存在于地图 life 里的任务。"""
from __future__ import annotations

from game.systems.quests import QuestDef, filter_world_quest_defs


def _d(**kw) -> QuestDef:
    kw.setdefault("qid", "1")
    kw.setdefault("name", "测试任务")
    return QuestDef(**kw)


NPCS = {"9000", "1012111"}
MOBS = {"210100", "210101"}


def test_keeps_quest_with_existing_start_npc():
    defs = {"1": _d(start_npc=9000)}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == defs


def test_drops_quest_without_start_npc():
    defs = {"1": _d(start_npc=None)}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == {}


def test_drops_quest_with_missing_start_npc():
    defs = {"1": _d(start_npc=9999999)}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == {}


def test_drops_quest_with_missing_end_npc():
    defs = {"1": _d(start_npc=9000, end_npc=9999999)}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == {}


def test_keeps_quest_when_kill_mobs_exist():
    defs = {"1": _d(start_npc=9000, kills=[(210100, 10), (210101, 5)])}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == defs


def test_drops_quest_when_any_kill_mob_missing():
    defs = {"1": _d(start_npc=9000, kills=[(210100, 10), (999999, 5)])}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == {}


def test_drops_collection_quest_when_item_unavailable():
    """收集类（end_items）不过滤——物品可获得性无法由 life 判定，保留。"""
    defs = {"1": _d(start_npc=9000, end_items=[(4000011, 10)])}
    assert filter_world_quest_defs(defs, NPCS, MOBS) == defs


def test_filters_per_quest_not_wholesale():
    defs = {
        "1": _d(qid="1", start_npc=9000),
        "2": _d(qid="2", start_npc=9999999),
        "3": _d(qid="3", start_npc=1012111, end_npc=9000),
    }
    kept = filter_world_quest_defs(defs, NPCS, MOBS)
    assert set(kept) == {"1", "3"}
