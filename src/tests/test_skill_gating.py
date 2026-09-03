"""技能学习四重门控与转职附赠：SP / 前置 req / 人物等级 / invisible 排除。"""
from __future__ import annotations

from game.core.jobs import JOBS
from game.systems.skills import SkillBook, SkillDef


def make_def(sid: str, name: str = "技能", max_level: int = 3,
             req: dict | None = None, char_level: int = 0,
             invisible: bool = False, **lv1) -> SkillDef:
    levels = [dict(lv1) or {"damage": 100} for _ in range(max_level)]
    return SkillDef(sid, name, "", levels, max_level,
                    req=req or {}, char_level=char_level, invisible=invisible)


def book_with(*defs: SkillDef) -> SkillBook:
    return SkillBook(None, 3000, defs={d.id: d for d in defs})


def test_new_book_has_no_skills():
    """开局（无转职赠送前）零技能零快捷键。"""
    book = book_with(make_def("3001004", mpCon=7, damage=190))
    assert book.levels == {}
    assert book.hotkeys == {}


def test_learn_blocked_by_sp():
    """SP 不足无法学习。"""
    book = book_with(make_def("3001004"))
    assert book.learn("3001004", player_level=10) is False


def test_learn_blocked_by_prereq():
    """前置技能未达等级时不可学；满足后可学。"""
    book = book_with(make_def("3001004"),
                     make_def("3001005", req={"3001004": 1}))
    book.add_sp(300, 5)
    assert book.learn("3001005", player_level=10) is False
    book.learn("3001004", player_level=10)
    assert book.learn("3001005", player_level=10) is True
    assert book.levels["3001005"] == 1


def test_learn_blocked_by_charlevel():
    """人物等级低于技能 CharLevel 时不可学。"""
    book = book_with(make_def("3001005", char_level=12))
    book.add_sp(300, 5)
    assert book.learn("3001005", player_level=10) is False
    assert book.learn("3001005", player_level=12) is True


def test_learn_blocked_by_max_level():
    """满级后不可再学。"""
    book = book_with(make_def("3001004", max_level=2))
    book.add_sp(300, 10)
    assert book.learn("3001004", player_level=10) is True
    assert book.learn("3001004", player_level=10) is True
    assert book.learn("3001004", player_level=10) is False


def test_learn_consumes_only_that_job_group():
    """学习只扣所属转的 SP：二转技能不吃一转池。"""
    book = book_with(make_def("3001004"), make_def("3101005"))
    book.add_sp(300, 1)                      # 一转池 1 点
    assert book.learn("3101005", player_level=30) is False   # 二转无 SP
    assert book.learn("3001004", player_level=10) is True
    assert book.sp_for_group(300) == 0


def test_learn_assigns_hotkey():
    """学会主动技能自动补入最小空闲快捷键。"""
    book = book_with(make_def("3001004"), make_def("3001005"))
    book.add_sp(300, 5)
    book.learn("3001004", player_level=10)
    book.learn("3001005", player_level=10)
    assert book.hotkeys == {1: "3001004", 2: "3001005"}


def test_learnable_excludes_invisible_and_passives():
    """invisible 与转职附赠被动都不进可学习列表。"""
    book = book_with(make_def("3000000", invisible=True),
                     make_def("3001004"))
    assert book.learnable() == ["3001004"]


def test_on_advance_grants_passives_and_hotkeys():
    """转职：被动直接满级、主动技能填入快捷键、被动不占键位。"""
    book = book_with(
        make_def("3000000", max_level=16),
        make_def("3000001", max_level=20),
        make_def("3000002", max_level=8),
        make_def("3001003", max_level=20),
        make_def("3001004", max_level=20),
        make_def("3001005", max_level=20),
    )
    book.on_advance(JOBS[3000])
    assert book.levels["3000000"] == 16
    assert book.levels["3000001"] == 20
    assert book.levels["3000002"] == 8
    assert set(book.hotkeys.values()) == {"3001003", "3001004", "3001005"}


def test_cast_returns_bullet_count():
    """施放数据带 bulletCount（默认 1）。"""
    book = book_with(make_def("3001004", mpCon=7, damage=190),
                     make_def("3001005", mpCon=10, damage=92, bulletCount=2))
    book.add_sp(300, 5)
    book.learn("3001004", player_level=10)
    book.learn("3001005", player_level=10)
    data = book.cast("3001005", 10)
    assert data["bullet_count"] == 2
    assert data["mp_con"] == 10
    assert book.cast("3001004", 10) is not None
    book.tick(10.0)
    assert book.cast("3001004", 10) is not None


def test_hotkeys_roundtrip():
    """to_dict / from_dict 保留快捷键、等级与各转 SP。"""
    book = book_with(make_def("3001004"))
    book.add_sp(300, 2)
    book.learn("3001004", player_level=10)
    d = book.to_dict()
    book2 = book_with(make_def("3001004"))
    book2.from_dict(d)
    assert book2.hotkeys == {1: "3001004"}
    assert book2.levels == {"3001004": 1}
    assert book2.sp_for_group(300) == 1


def test_from_dict_migrates_legacy_single_sp():
    """旧档单一 sp 字段 → 归入当前职业组。"""
    book = book_with(make_def("3001004"))
    book.from_dict({"sp": 7, "levels": {"3001004": 2}, "hotkeys": {"1": "3001004"}})
    assert book.sp_for_group(300) == 7
    assert book.levels == {"3001004": 2}


def test_from_dict_legacy_derives_passives_from_levels():
    """无 passives 字段的旧档：按职业链从已学 id 反推附赠被动。"""
    book = SkillBook(None, 3000, defs={
        "3000001": make_def("3000001", max_level=20),
        "3001004": make_def("3001004")})
    book.from_dict({"sp": 0, "levels": {"3000001": 20, "3001004": 2}, "hotkeys": {}})
    assert book.learnable() == ["3001004"]
    assert book.levels["3000001"] == 20


def test_gain_sp_for_level_routes_to_tier():
    """升级 SP 归入职业链中「解锁等级 ≤ 本等级」的最高一阶组。"""
    book = SkillBook(None, 3100, defs={})       # 链 = [弓箭手(10), 猎人(30)]
    book.gain_sp_for_level(20, 1)               # Lv20 → 一组 300
    book.gain_sp_for_level(35, 2)               # Lv35 → 二组 310
    assert book.sp_for_group(300) == 1
    assert book.sp_for_group(310) == 2


def test_learnable_and_skills_grouped_by_owner():
    """可学列表 / 页签列表可按所属转过滤。"""
    book = book_with(make_def("3001004"), make_def("3101005"))
    assert book.learnable(owner_group=300) == ["3001004"]
    assert book.learnable(owner_group=310) == ["3101005"]
    assert book.skills_for_group(310) == ["3101005"]


def test_inherit_preserves_old_job_progress():
    """转职累积：旧转已学等级与各转 SP 结余搬入新书。"""
    old = book_with(make_def("3001004", max_level=20))
    old.add_sp(300, 4)
    old.levels["3001004"] = 5
    new = SkillBook(None, 3100, defs={
        "3001004": make_def("3001004"), "3101005": make_def("3101005")})
    new.inherit(old)
    assert new.levels.get("3001004") == 5
    assert new.sp_for_group(300) == 4


def test_inherit_keeps_old_passives_non_learnable():
    """转职后旧转附赠被动仍不可手学（passive 集合累积）。"""
    old = book_with(make_def("3000001", max_level=20))
    old.on_advance(JOBS[3000])
    assert "3000001" not in old.learnable()
    new = SkillBook(None, 3100, defs={"3000001": make_def("3000001", max_level=20)})
    new.inherit(old)
    assert "3000001" not in new.learnable()
    assert new.levels.get("3000001") == 20
