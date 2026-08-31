"""技能学习四重门控与转职附赠：SP / 前置 req / 人物等级 / invisible 排除。"""
from __future__ import annotations

from game.jobs import JOBS
from game.skills import SkillBook, SkillDef


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
    book.sp = 5
    assert book.learn("3001005", player_level=10) is False
    book.learn("3001004", player_level=10)
    assert book.learn("3001005", player_level=10) is True
    assert book.levels["3001005"] == 1


def test_learn_blocked_by_charlevel():
    """人物等级低于技能 CharLevel 时不可学。"""
    book = book_with(make_def("3001005", char_level=12))
    book.sp = 5
    assert book.learn("3001005", player_level=10) is False
    assert book.learn("3001005", player_level=12) is True


def test_learn_blocked_by_max_level():
    """满级后不可再学。"""
    book = book_with(make_def("3001004", max_level=2))
    book.sp = 10
    assert book.learn("3001004", player_level=10) is True
    assert book.learn("3001004", player_level=10) is True
    assert book.learn("3001004", player_level=10) is False


def test_learnable_excludes_invisible():
    """invisible 被动不出现在可学习列表。"""
    book = book_with(make_def("3000000", invisible=True),
                     make_def("3001004"))
    assert book.learnable() == ["3001004"]


def test_learn_assigns_hotkey():
    """学会主动技能自动补入最小空闲快捷键。"""
    book = book_with(make_def("3001004"), make_def("3001005"))
    book.sp = 5
    book.learn("3001004", player_level=10)
    book.learn("3001005", player_level=10)
    assert book.hotkeys == {1: "3001004", 2: "3001005"}


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
    book.sp = 5
    book.learn("3001004", player_level=10)
    book.learn("3001005", player_level=10)
    data = book.cast("3001005", 10)
    assert data["bullet_count"] == 2
    assert data["mp_con"] == 10
    assert book.cast("3001004", 10) is not None
    book.tick(10.0)
    assert book.cast("3001004", 10) is not None


def test_hotkeys_roundtrip():
    """to_dict / from_dict 保留快捷键表。"""
    book = book_with(make_def("3001004"))
    book.sp = 2
    book.learn("3001004", player_level=10)
    d = book.to_dict()
    book2 = book_with(make_def("3001004"))
    book2.from_dict(d)
    assert book2.hotkeys == {1: "3001004"}
    assert book2.levels == {"3001004": 1}
    assert book2.sp == 1
