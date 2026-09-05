"""官方掉落表（drop_data）：逐行以百万分比独立掷骰，金币行与物品行分开结算。"""

from __future__ import annotations

import random

from game.systems.drops import OfficialDropTable


def test_full_chance_item_always_drops_with_count_in_range():
    """掉率百万比 =1000000 的物品行必掉，数量落在 [min, max]。"""
    table = OfficialDropTable.from_dict({
        "210100": [{"item": "4000000", "min": 2, "max": 5, "chance": 1_000_000}],
    })
    rng = random.Random(7)
    for _ in range(30):
        res = table.roll("210100", rng)
        assert [it["id"] for it in res.items] == ["4000000"]
        assert 2 <= res.items[0]["count"] <= 5


def test_zero_chance_row_never_drops():
    """掉率 0 的行永不命中（任务限定等极端行）。"""
    table = OfficialDropTable.from_dict({
        "210100": [{"item": "4000000", "min": 1, "max": 1, "chance": 0}],
    })
    res = table.roll("210100", random.Random(1))
    assert res.items == [] and res.meso == 0


def test_unknown_mob_has_no_official_data():
    """表里没有的怪：has_mob 为假，roll 出空结果（调用方据此回退旧逻辑）。"""
    table = OfficialDropTable.from_dict({})
    assert table.has_mob("100101") is False
    res = table.roll("100101", random.Random(1))
    assert res.items == [] and res.meso == 0


def test_meso_row_rolls_separately_from_items():
    """item="0" 是金币行：命中给 [min,max] 金币，不进物品列表。"""
    table = OfficialDropTable.from_dict({
        "100101": [
            {"item": "0", "min": 8, "max": 12, "chance": 1_000_000},
            {"item": "4000000", "min": 1, "max": 1, "chance": 1_000_000},
        ],
    })
    res = table.roll("100101", random.Random(3))
    assert 8 <= res.meso <= 12
    assert [it["id"] for it in res.items] == ["4000000"]


def test_quest_row_needs_active_quest():
    """带 quest 的行：不在进行中任务集内不掷骰；传入该任务才按掉率掉。"""
    table = OfficialDropTable.from_dict({
        "210100": [{"item": "4031273", "min": 1, "max": 1, "chance": 1_000_000,
                    "quest": 2104}],
    })
    assert table.roll("210100", random.Random(1)).items == []
    assert table.roll("210100", random.Random(1), active_quests={"2104"}
                     ).items == [{"id": "4031273", "count": 1}]
    assert table.roll("210100", random.Random(1), active_quests={"2105"}
                     ).items == []


def test_quest_filter_only_skips_quest_rows():
    """任务过滤只作用于任务限定行：普通物品/金币行不受进行中任务集影响。"""
    table = OfficialDropTable.from_dict({
        "210100": [
            {"item": "0", "min": 8, "max": 12, "chance": 1_000_000},
            {"item": "4000000", "min": 1, "max": 1, "chance": 1_000_000,
             "quest": 2104},
            {"item": "2000000", "min": 1, "max": 1, "chance": 1_000_000},
        ],
    })
    res = table.roll("210100", random.Random(1))
    assert 8 <= res.meso <= 12
    assert [it["id"] for it in res.items] == ["2000000"]


def test_all_rows_roll_independently_multiple_drops():
    """逐行独立掷骰：全命中的行一次击杀全部掉出（原版可多件）。"""
    table = OfficialDropTable.from_dict({
        "100101": [
            {"item": "2000000", "min": 1, "max": 1, "chance": 1_000_000},
            {"item": "4010000", "min": 1, "max": 1, "chance": 1_000_000},
            {"item": "4020000", "min": 1, "max": 1, "chance": 1_000_000},
        ],
    })
    res = table.roll("100101", random.Random(5))
    assert [it["id"] for it in res.items] == ["2000000", "4010000", "4020000"]
