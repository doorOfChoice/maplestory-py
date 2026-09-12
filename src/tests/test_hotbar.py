"""快捷栏快照：物理键已解绑的技能槽不再进入 HUD 槽位列表。"""

from __future__ import annotations

from types import SimpleNamespace

from game.core.hotbar import build_hotbar
from game.core.keybindings import KeyBindings


def make_player(*sids: str) -> SimpleNamespace:
    skills = SimpleNamespace(
        levels={sid: 1 for sid in sids},
        hotkeys={i + 1: sid for i, sid in enumerate(sids)},
        cooldowns={},
        cooldown_totals={},
        defs={sid: SimpleNamespace(name=f"技能{sid[-2:]}") for sid in sids},
    )
    return SimpleNamespace(skills=skills, inventory=None)


def skill_refs(player, bindings):
    return [s.ref_id for s in build_hotbar(player, bindings) if s.kind == "skill"]


def test_bound_skill_slot_is_shown():
    """物理键仍在绑定的技能槽进快捷栏。"""
    player = make_player("3001000")
    assert skill_refs(player, KeyBindings()) == ["3001000"]


def test_unbound_skill_slot_is_hidden():
    """右键解绑 skill_1 后：槽位映射仍在，但快捷栏不再展示该技能。"""
    player = make_player("3001000")
    bindings = KeyBindings()
    bindings.unbind("skill_1")
    assert skill_refs(player, bindings) == []


def test_unbound_slot_does_not_hide_other_slots():
    """只隐藏被解绑的槽，其它已绑槽照常展示。"""
    player = make_player("3001000", "3001001")
    bindings = KeyBindings()
    bindings.unbind("skill_1")
    assert skill_refs(player, bindings) == ["3001001"]
