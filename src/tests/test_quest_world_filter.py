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


def test_drops_quest_with_garbled_name():
    """乱码/未本地化任务名剔除：韩文残留、多处 ? 占位；含 ?! 标点的正常中文名保留。"""
    defs = {
        "1": _d(qid="1", start_npc=9000, name="마야의 사랑의 증표"),
        "2": _d(qid="2", start_npc=9000, name="???? ????<??>-1??"),
        "3": _d(qid="3", start_npc=9000, name="欺骗骗子!?"),
    }
    kept = filter_world_quest_defs(defs, NPCS, MOBS)
    assert set(kept) == {"3"}


def test_drops_event_quest_by_qid_range():
    """活动类任务（季节/联动/周年庆）按编号区段剔除，即便 NPC 真实存在。"""
    defs = {
        "9004": _d(qid="9004", start_npc=9000),     # 中秋/圣诞等 9xxx 季节活动
        "10000": _d(qid="10000", start_npc=9000),   # 特殊干员O 活动线
        "28000": _d(qid="28000", start_npc=9000),   # 圣诞惊喜舞会
        "52001": _d(qid="52001", start_npc=9000),   # 4周年庆
        "4437": _d(qid="4437", start_npc=9000),     # 白色圣诞节（散落个体）
    }
    assert filter_world_quest_defs(defs, NPCS, MOBS) == {}


def test_keeps_normal_quest_outside_event_ranges():
    """活动区段边界外的常规任务照常保留（区间为左闭右开）。"""
    defs = {
        "8999": _d(qid="8999", start_npc=9000),
        "11000": _d(qid="11000", start_npc=9000),
        "29000": _d(qid="29000", start_npc=9000),   # 称号挑战非活动，保留
        "4436": _d(qid="4436", start_npc=9000),
        "20000": _d(qid="20000", start_npc=9000),   # 20xxx 主线不误伤
    }
    kept = filter_world_quest_defs(defs, NPCS, MOBS)
    assert set(kept) == set(defs)


def test_filters_per_quest_not_wholesale():
    defs = {
        "1": _d(qid="1", start_npc=9000),
        "2": _d(qid="2", start_npc=9999999),
        "3": _d(qid="3", start_npc=1012111, end_npc=9000),
    }
    kept = filter_world_quest_defs(defs, NPCS, MOBS)
    assert set(kept) == {"1", "3"}
