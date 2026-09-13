"""技能窗双击已学技能行 → 触发按技能 id 施放（cast_skill 服务回调）。

双击判定复用 WindowManager 的 0.35s 双击链路（与背包使用/穿戴同源）；
SkillWindow.activate 只把技能 id 交给 svc.cast_skill，窗口层不感知世界。
"""

from __future__ import annotations

from types import SimpleNamespace

from game.core.jobs import sp_group_of_skill
from game.render.windows.core.services import WindowServices
from game.render.windows.skill import SkillWindow
from game.systems.skills import SkillBook, SkillDef
from tests.windows_harness import (FakeAssets, FakeUI, draw_once,
                                   make_manager, press, release)

MAGIC_ARROW = "3001000"
SECOND_SKILL = "3001001"


def make_book() -> SkillBook:
    defs = {sid: SkillDef(sid, f"技能{sid[-2:]}", "", [{"damage": 100}], 5)
            for sid in (MAGIC_ARROW, SECOND_SKILL)}
    book = SkillBook(assets=None, job=3000, defs=defs)
    book.add_sp(sp_group_of_skill(MAGIC_ARROW), 3)
    book.learn(MAGIC_ARROW, 1)
    return book


def build() -> tuple:
    """装配技能窗并接线 cast_skill 记录器，开窗画帧以登记技能行热区。"""
    book = make_book()
    player = SimpleNamespace(skills=book, level=10)
    casted: list = []
    svc = WindowServices(assets=FakeAssets(), ui=FakeUI(),
                         player=lambda: player)
    svc.cast_skill = casted.append
    skillw = SkillWindow(svc)
    mgr = make_manager(skillw)
    skillw.open()
    draw_once(mgr)
    return mgr, skillw, book, casted


def skill_row(skillw: SkillWindow, sid: str):
    return next(rect for rect, s in skillw._drag_rects if s == sid)


def test_double_click_learned_skill_casts_it():
    """双击已学技能行 → cast_skill 收到该技能 id。"""
    mgr, skillw, book, casted = build()
    pos = skill_row(skillw, MAGIC_ARROW).center
    press(mgr, pos)
    release(mgr, pos)
    press(mgr, pos)
    release(mgr, pos)
    assert casted == [MAGIC_ARROW]


def test_single_click_does_not_cast():
    """单击（未构成双击）不施放。"""
    mgr, skillw, book, casted = build()
    pos = skill_row(skillw, MAGIC_ARROW).center
    press(mgr, pos)
    release(mgr, pos)
    assert casted == []


def test_unlearned_skill_row_not_activatable():
    """未学技能的行走不进拖拽源表，双击不触发施放。"""
    mgr, skillw, book, casted = build()
    assert [s for _, s in skillw._drag_rects] == [MAGIC_ARROW]
