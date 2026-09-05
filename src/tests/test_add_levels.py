"""GM 加等级：add_levels 直接升 N 级，补 AP/SP/上下限并回满，不改经验值。"""

from __future__ import annotations

from game import settings
from game.entities.player import Player


class StarterAssets:
    def equip_info(self, item_id: str) -> dict:
        return {"islot": "WpSs"}

    def consume_info(self, item_id: str) -> dict:
        return {}

    def item_name(self, item_id: str):
        return None

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)


def make_player(monkeypatch) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    return Player(StarterAssets(), 0.0, 0.0)


def test_add_levels_raises_level_and_ap(monkeypatch):
    p = make_player(monkeypatch)
    start_level, start_ap = p.level, p.ap
    p.add_levels(5)
    assert p.level == start_level + 5
    assert p.ap == start_ap + 5 * settings.AP_PER_LEVEL


def test_add_levels_refills_vitals(monkeypatch):
    p = make_player(monkeypatch)
    p.hp = 1
    p.mp = 1
    p.add_levels(1)
    assert p.hp == p.max_hp
    assert p.mp == p.max_mp


def test_add_levels_gives_sp(monkeypatch):
    p = make_player(monkeypatch)
    before = p.skills.total_sp
    p.add_levels(3)
    assert p.skills.total_sp >= before + 3 * settings.SP_PER_LEVEL
