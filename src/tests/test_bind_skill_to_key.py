"""技能落键：把技能窗拖到键盘键上的槽位分配与改绑互换语义。

测 assign_skill_to_key 公开函数：已学主动技复用现有槽换键、未学槽取最小
空闲槽、被占用键自动互换、未学/槽满拒绝。不触 UI、不依赖 WZ。
"""

from __future__ import annotations

import pygame

from game.core.jobs import sp_group_of_skill
from game.core.keybindings import KeyBindings
from game.systems.skills import SkillBook, SkillDef, assign_skill_to_key


def make_book(*sids: str) -> SkillBook:
    defs = {s: SkillDef(s, f"S{s}", "", [{"damage": 100}], 5) for s in sids}
    return SkillBook(assets=None, job=3000, defs=defs)


def learn(book: SkillBook, sid: str) -> None:
    book.add_sp(sp_group_of_skill(sid), 5)
    assert book.learn(sid, 1)


def test_already_assigned_skill_moves_to_new_key():
    """学过的技能已有槽位：只把该槽的动作键换掉，槽位号不变。"""
    book, kb = make_book("3001000"), KeyBindings()
    learn(book, "3001000")
    assert book.hotkeys == {1: "3001000"}
    assert assign_skill_to_key(book, kb, "3001000", pygame.K_q)
    assert kb.key_of("skill_1") == pygame.K_q
    assert kb.skill_slot_for(pygame.K_q) == 1
    assert book.hotkeys == {1: "3001000"}


def test_two_skills_swap_keys_via_slots():
    """把技能 2 拖到技能 1 的键上：互换后各槽技能名不变、键位对调。"""
    book, kb = make_book("3001000", "3001001"), KeyBindings()
    learn(book, "3001000")
    learn(book, "3001001")
    assert assign_skill_to_key(book, kb, "3001001", pygame.K_1)
    assert kb.key_of("skill_1") == pygame.K_2
    assert kb.key_of("skill_2") == pygame.K_1
    assert book.hotkeys == {1: "3001000", 2: "3001001"}


def test_unassigned_skill_takes_free_slot():
    """槽位空出的已学技能（手动删槽后）：落键时分配最小空闲槽。"""
    book, kb = make_book("3001000", "3001001"), KeyBindings()
    learn(book, "3001000")
    learn(book, "3001001")
    del book.hotkeys[2]
    assert assign_skill_to_key(book, kb, "3001001", pygame.K_w)
    assert book.hotkeys == {1: "3001000", 2: "3001001"}
    assert kb.skill_slot_for(pygame.K_w) == 2


def test_drop_on_key_held_by_action_swaps_it_out():
    """拖到「普通攻击」占的 A 键：攻击换到该技能槽的原键。"""
    book, kb = make_book("3001000"), KeyBindings()
    learn(book, "3001000")
    assert assign_skill_to_key(book, kb, "3001000", pygame.K_a)
    assert kb.key_of("skill_1") == pygame.K_a
    assert kb.key_of("attack") == pygame.K_1


def test_unknown_skill_rejected():
    book, kb = make_book("3001000"), KeyBindings()
    assert not assign_skill_to_key(book, kb, "3009999", pygame.K_q)
    assert kb.key_of("skill_1") == pygame.K_1


def test_full_hotkeys_block_unassigned_skill():
    """12 槽全被别的技能占着且拖入技未上键：拒绝且不动绑定表。"""
    sids = [f"30010{i:02d}" for i in range(13)]
    book, kb = make_book(*sids), KeyBindings()
    for sid in sids:
        learn(book, sid)
    assert len(book.hotkeys) == 12
    assert not assign_skill_to_key(book, kb, sids[12], pygame.K_w)
    assert kb.key_of("skill_1") == pygame.K_1
