"""技能冷却：cast 读取 WZ `cooltime`（秒）并换算为毫秒交给 start_cooldown。

seam：SkillBook.cast / SkillBook.start_cooldown；合成 SkillDef，不依赖 WZ。
"""
from __future__ import annotations

from game.systems.skills import SkillBook, SkillDef


def make_book(sid: str, lv1: dict) -> SkillBook:
    defs = {sid: SkillDef(sid, "测试", "", [dict(lv1)], 1)}
    book = SkillBook(None, 3000, defs=defs)
    book.levels[sid] = 1
    return book


def test_cast_translates_cooltime_seconds_to_ms():
    """WZ cooltime=360（秒）→ cooldown_ms=360000。"""
    book = make_book("3121008", {"cooltime": 360, "time": 120, "pad": 26})
    data = book.cast("3121008", 120)
    assert data is not None
    assert data["cooldown_ms"] == 360_000


def test_cast_without_cooltime_has_zero_ms():
    """无 cooltime 字段（多数攻击技）→ 0，由 start_cooldown 决定是否回退。"""
    book = make_book("3001004", {"mpCon": 7, "damage": 190})
    assert book.cast("3001004", 10)["cooldown_ms"] == 0


def test_start_cooldown_uses_wz_seconds():
    """start_cooldown 收到 360000ms → 冷却 360 秒入表。"""
    book = make_book("3121008", {"cooltime": 360, "time": 120, "pad": 26})
    data = book.cast("3121008", 120)
    book.start_cooldown("3121008", data["cooldown_ms"])
    assert book.cooldowns["3121008"] == 360.0
    assert book.cooldown_totals["3121008"] == 360.0
