"""法师二转 debuff/被动接线：缓速术减速、冰冻术冻结、魔力吸收回蓝（合成资产）。"""
from __future__ import annotations

import random

import pygame

from game.systems.combat import Combat
from game.systems.skills import SkillBook, SkillDef


class _Mob:
    x, cy, sprite_h, level = 100.0, 100.0, 30, 1
    pd = 0
    mdd = 0
    eva = 0
    dead = False
    exp = 0
    boss = False
    mob_id = "9999999"

    def __init__(self, x: float = 100.0, cy: float = 100.0, mp: int = 0,
                 max_mp: int = 100):
        self.x = x
        self.cy = cy
        self.mp = mp
        self.max_mp = max_mp
        self.slow: list = []
        self.freeze: list = []
        self.poison: list = []

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def take_hit(self, damage: int, from_x=None) -> bool:
        return False

    def roll_drop(self):
        return None

    def apply_slow(self, mult, seconds) -> None:
        self.slow.append((mult, seconds))

    def apply_freeze(self, seconds) -> None:
        self.freeze.append(seconds)

    def element_multiplier(self, element) -> float:
        return 1.0

    def apply_poison(self, dps, seconds) -> None:
        self.poison.append((dps, seconds))


class _Assets:
    def skill_ball_frames(self, sid, level=1):
        return []

    def skill_hit_frames(self, sid):
        return []


class _Player:
    x, y = 0.0, 100.0
    facing_right = True
    level = 30
    attack_hit_applied = False
    pending_skill = None

    def __init__(self):
        self.skills = None
        self.mp = 0
        self.max_mp = 999

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-10, 60, 60, 60)

    def attack_range(self):
        return (1, 1)

    def magic_attack_range(self, skill_mad=0, skill_mastery=0):
        return (100, 100)

    def crit_rate(self):
        return 0.0

    def crit_mult(self):
        return 1.5

    def accuracy_value(self):
        return 100


def _magic_book() -> SkillBook:
    return SkillBook(None, 2200, defs={
        "2200000": SkillDef("2200000", "魔力吸收", "", [{"prop": 100, "x": 10}], 1),
    })


SLOW_SKILL = {"id": "2201003", "damage": 1.0, "mob_count": 6, "magic": False,
              "form": "mob_status", "status": "slow", "slow_x": -20,
              "duration": 20.0, "attack_count": 1,
              "area": ((-200, -150), (200, 150))}


def test_slow_skill_debuffs_area_targets_without_damage():
    """缓速术：范围内最多 mobCount 只被减速（无伤害飘字），范围外不动。"""
    combat = Combat(_Assets(), rng=random.Random(1))
    player = _Player()
    player.pending_skill = dict(SLOW_SKILL)
    inside, outside = _Mob(100.0), _Mob(400.0)
    combat.player_attack(player, [inside, outside])
    assert inside.slow == [(0.8, 20.0)]
    assert outside.slow == []
    assert combat.numbers == []


def test_freeze_applies_on_magic_hit():
    """冰冻术：魔法命中给目标上冻结（时长取 WZ time）。"""
    combat = Combat(_Assets(), rng=random.Random(1))
    player = _Player()
    player.pending_skill = {"id": "2201004", "damage": 1.0, "mob_count": 1,
                            "magic": True, "cone_attack": True,
                            "skill_mad": 13, "skill_mastery": 1,
                            "attack_count": 1, "freeze": 1.0}
    mob = _Mob(100.0)
    combat.player_attack(player, [mob])
    assert mob.freeze == [1.0]


def test_magic_absorb_restores_player_mp_from_mob():
    """魔力吸收：魔法命中按 prop/x 吸怪 MP 回蓝。"""
    combat = Combat(_Assets(), rng=random.Random(1))
    player = _Player()
    player.skills = _magic_book()
    player.skills.levels["2200000"] = 1
    player.mp = 5
    player.pending_skill = {"id": "2001004", "damage": 1.0, "mob_count": 1,
                            "magic": True, "cone_attack": True,
                            "skill_mad": 20, "skill_mastery": 1,
                            "attack_count": 1}
    mob = _Mob(100.0, mp=50)
    combat.player_attack(player, [mob])
    assert mob.mp == 40
    assert player.mp == 15


def test_absorb_skips_mob_without_mp():
    """魔力吸收：怪无 MP 时不回蓝（吸不到）。"""
    combat = Combat(_Assets(), rng=random.Random(1))
    player = _Player()
    player.skills = _magic_book()
    player.skills.levels["2200000"] = 1
    player.mp = 5
    player.pending_skill = {"id": "2001004", "damage": 1.0, "mob_count": 1,
                            "magic": True, "cone_attack": True,
                            "skill_mad": 20, "skill_mastery": 1,
                            "attack_count": 1}
    mob = _Mob(100.0, mp=0)
    combat.player_attack(player, [mob])
    assert player.mp == 5
