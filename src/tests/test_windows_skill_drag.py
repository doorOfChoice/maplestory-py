"""技能窗 → 键盘窗跨窗拖拽：从技能行起拖、落在键格上完成上键+改绑。

SkillWindow 的已学主动技能行是 skill 类拖拽源（被动 / 未学不可拖）；
松手时由 WindowManager 投递给 KeyConfigWindow.handle_drop，同时更新
hotkeys 槽位映射与按键绑定表。全程走 manager 公开事件链路。
"""

from __future__ import annotations

from types import SimpleNamespace

import pygame

from game.core.jobs import sp_group_of_skill
from game.core.keybindings import KeyBindings
from game.render.windows.keyconfig import KeyConfigWindow
from game.render.windows.skill import SkillWindow
from game.render.windows.core.services import WindowServices
from game.systems.skills import SkillBook, SkillDef
from tests.windows_harness import (FakeAssets, FakeUI, draw_once,
                                   make_manager, motion, press, release)

MAGIC_ARROW = "3001000"
SECOND_SKILL = "3001001"


def make_book() -> SkillBook:
    defs = {sid: SkillDef(sid, f"技能{sid[-2:]}", "", [{"damage": 100}], 5)
            for sid in (MAGIC_ARROW, SECOND_SKILL)}
    book = SkillBook(assets=None, job=3000, defs=defs)
    book.add_sp(sp_group_of_skill(MAGIC_ARROW), 3)
    book.learn(MAGIC_ARROW, 1)          # 已学：自动占 1 号槽
    return book


def build() -> tuple:
    """装配技能窗 + 键盘窗（挪到左侧避免重叠），开双窗并画帧。"""
    book = make_book()
    player = SimpleNamespace(skills=book, level=10)
    kb = KeyBindings()
    svc = WindowServices(assets=FakeAssets(), ui=FakeUI(),
                         player=lambda: player, bindings=kb)
    skillw = SkillWindow(svc)
    keyw = KeyConfigWindow(svc)
    mgr = make_manager(keyw, skillw)
    keyw.open()
    skillw.open()
    draw_once(mgr)
    keyw.move_to(8, 40, 800, 600)
    draw_once(mgr)
    return mgr, skillw, keyw, book, kb


def skill_row(skillw: SkillWindow, sid: str) -> pygame.Rect:
    return next(rect for rect, s in skillw._drag_rects if s == sid)


def key_cell(keyw: KeyConfigWindow, key: int) -> pygame.Rect:
    return next(rect for rect, k in keyw.key_cells if k == key)


def test_learned_active_row_is_draggable():
    mgr, skillw, keyw, book, kb = build()
    pk = skillw.pickup(skill_row(skillw, MAGIC_ARROW).center)
    assert pk is not None and pk.kind == "skill"
    assert pk.payload == MAGIC_ARROW and pk.label == "技能00"


def test_unlearned_row_is_not_draggable():
    """未学（Lv0）技能行不进拖拽源表：pickup 永远抓不起它。"""
    mgr, skillw, keyw, book, kb = build()
    assert [s for _, s in skillw._drag_rects] == [MAGIC_ARROW]


def test_drag_skill_from_skill_window_binds_key():
    """拖「技能00」到 F 键：槽 1 的动作键变 F，原默认键 1 腾空。"""
    mgr, skillw, keyw, book, kb = build()
    row = skill_row(skillw, MAGIC_ARROW)
    assert press(mgr, row.center)
    target = key_cell(keyw, pygame.K_f)
    assert motion(mgr, (row.centerx, row.centery - 40))
    assert motion(mgr, target.center)
    assert release(mgr, target.center)
    assert book.hotkeys == {1: MAGIC_ARROW}
    assert kb.key_of("skill_1") == pygame.K_f
    assert kb.action_for(pygame.K_1) is None


def test_drag_skill_released_off_keyboard_is_noop():
    mgr, skillw, keyw, book, kb = build()
    row = skill_row(skillw, MAGIC_ARROW)
    assert press(mgr, row.center)
    assert motion(mgr, (795, 595))            # 视口角落：两窗与键格都不在
    assert release(mgr, (795, 595))
    assert kb.key_of("skill_1") == pygame.K_1
