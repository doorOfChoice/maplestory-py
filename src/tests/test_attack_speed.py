"""攻速生效：武器 WZ speed 值（0最快）换算攻击动画推进倍率与出手间隔手感。"""
from __future__ import annotations

import pygame

from game import settings
from game.core.animation import Animation
from game.core.stats import base_stats
from game.entities.player import Player
from game.systems.inventory import Inventory, Item
from game.systems.skills import SkillBook


class Keys:
    up = down = left = right = jump = attack = False


class StubAssets:
    def __init__(self):
        self.equips = None
        self.job = 0

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def _init(self, assets, quest_defs=None):
    self.inventory = Inventory()
    self.skills = SkillBook(None, 0)
    self.quests = {}
    self.stats = base_stats()
    self.level = 1
    self.pending_skill = None
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


def make_player(monkeypatch, weapon_speed: int | None) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _init)
    p = Player(StubAssets(), 0.0, 0.0)
    if weapon_speed is not None:
        info = {"islot": "Wp", "incPAD": 25, "speed": weapon_speed}
        p.inventory.equipped["weapon"] = Item(id="01302000", name="测试剑",
                                              kind="equip", info=info)
    return p


def test_anim_rate_maps_weapon_speed_to_delay_table(monkeypatch):
    """delay=300+60×speed、以 speed4 为基准：0→1.8 倍、4→1、6→0.818。"""
    assert make_player(monkeypatch, 0).attack_anim_rate() == 1.8
    assert make_player(monkeypatch, 4).attack_anim_rate() == 1.0
    rate6 = make_player(monkeypatch, 6).attack_anim_rate()
    assert rate6 == settings.ATTACK_DELAY_REF_MS / (
        settings.ATTACK_DELAY_BASE_MS + 6 * settings.ATTACK_DELAY_STEP_MS)


def test_fast_weapon_finishes_swing_in_fewer_ticks(monkeypatch):
    """同一套 2×100ms 攻击动画：speed0 武器比 speed6 更早收招。"""
    def swings_until_idle(weapon_speed: int) -> int:
        p = make_player(monkeypatch, weapon_speed)
        k = Keys()
        assert p.start_attack()
        surf = pygame.Surface((4, 4))
        p.anim = Animation([(surf, 100), (surf, 100)], loop=False)
        ticks = 0
        while p.attacking and ticks < 500:
            p.update(0.016, k, Physics_stub())
            ticks += 1
        assert not p.attacking
        return ticks

    assert swings_until_idle(0) < swings_until_idle(6)


def Physics_stub():
    from game.core.physics import Physics
    seg = {"id": 1, "layer": 0, "platform": 0, "x1": -100, "y1": 20,
           "x2": 100, "y2": 20, "prev": -1, "next": -1}
    return Physics([seg], [], bounds={"left": -1000, "right": 1000,
                                      "top": -500, "width": 2000,
                                      "height": 2000})
