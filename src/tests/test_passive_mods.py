"""被动技能聚合：逐技能字段语义、暴伤取最强来源、跨转确定性（合成 SkillDef）。

seam：SkillBook.passive_mods（公开查询）；不依赖 WZ。
"""
from __future__ import annotations

from game.core.jobs import JobDef
from game.systems.skills import SkillBook, SkillDef


def make_book(defs: dict, passive_ids: list) -> SkillBook:
    book = SkillBook(None, 3000, defs=defs)
    book.on_advance(JobDef(code=3000, name="测试", passive_ids=passive_ids))
    return book


def passive(sid: str, name: str, lv1: dict) -> SkillDef:
    return SkillDef(sid, name, "", [dict(lv1)], 1)


def test_passive_mods_sums_crit_and_takes_strongest_crit_mult():
    """暴击率各来源求和；暴伤取最强来源而非被后一被动覆盖。"""
    book = make_book({
        "3000001": passive("3000001", "霸王箭", {"prop": 40, "damage": 200}),
        "3110001": passive("3110001", "致命箭", {"prop": 90, "damage": 250}),
    }, [3000001, 3110001])
    mods = book.passive_mods()
    assert mods["crit"] == 130
    assert mods["crit_mult"] == 250


def test_passive_mods_is_deterministic():
    """同一本书重复查询结果一致（不随集合迭代顺序漂移）。"""
    defs = {
        "3000001": passive("3000001", "霸王箭", {"prop": 40, "damage": 200}),
        "3110001": passive("3110001", "致命箭", {"prop": 90, "damage": 250}),
    }
    first = make_book(defs, [3000001, 3110001]).passive_mods()
    for _ in range(5):
        assert make_book(defs, [3110001, 3000001]).passive_mods() == first


def test_passive_mods_collects_mastery_speed_and_accuracy():
    """精準之弓(3100000) 与疾風步(3110000) 的 mastery/x/speed 正确入表。"""
    book = make_book({
        "3100000": passive("3100000", "精準之弓", {"mastery": 10, "x": 20}),
        "3110000": passive("3110000", "疾風步", {"speed": 30}),
    }, [3100000, 3110000])
    mods = book.passive_mods()
    assert mods["mastery"] == 10
    assert mods["acc"] == 20
    assert mods["speed"] == 30


def test_final_attack_passive_produces_no_bogus_crit_mods():
    """終極之弓(3100001) 未实现：不得把 prop/damage 误当暴击/暴伤。"""
    book = make_book({
        "3100001": passive("3100001", "終極之弓", {"prop": 60, "damage": 250}),
    }, [3100001])
    assert book.passive_mods() == {}
