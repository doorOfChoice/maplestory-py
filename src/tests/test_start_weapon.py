"""新游戏出生武器：新手开局即带一把木剑并穿戴；转职时换发职业武器、旧剑回背包。"""

from __future__ import annotations

from game import settings
from game.entities.player import Player

ISLOT = {
    "01040000": "Cp", "01060000": "Pn", "01070000": "So",
    "01302000": "WpSs", "01452002": "WpOB",
}


class StarterAssets:
    def equip_info(self, item_id: str) -> dict:
        return {"islot": ISLOT.get(f"{int(item_id):08d}", "")}

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


def test_new_game_starts_with_equipped_weapon(monkeypatch):
    p = make_player(monkeypatch)
    weapon = p.inventory.equipped.get("weapon")
    assert weapon is not None
    assert weapon.id == "01302000"


def test_new_game_weapon_in_render_equips(monkeypatch):
    p = make_player(monkeypatch)
    assert "01302000" in p.equips


def test_start_weapon_configured_in_settings():
    assert settings.DEFAULT_EQUIPS[-1] == "01302000"


def test_advance_replaces_starter_weapon_with_job_weapon(monkeypatch):
    p = make_player(monkeypatch)
    p.level = 10
    p.advance_to(3000, StarterAssets())
    assert p.inventory.equipped["weapon"].id == "01452002"
    assert any(i.id == "01302000" for i in p.inventory.equips)
