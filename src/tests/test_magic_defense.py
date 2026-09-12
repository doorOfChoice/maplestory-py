"""魔法攻击改吃怪物魔法防御（mdd）：物理攻击仍用 pd，未标记 magic 时行为不变。"""
from __future__ import annotations

import random

import pygame

from game.systems.combat import Arrow, Combat


class _Mob:
    """物防极高、魔防为零的合成怪：物理近乎无伤，魔法全额。

    如此只要断言伤害 > 1 即可证明本次结算用了哪一项防御。
    """

    x, cy, sprite_h, level = 10.0, 100.0, 30, 1
    pd = 5000
    mdd = 0
    eva = 0
    dead = False
    exp = 0
    mob_id = "9999999"

    def __init__(self):
        self.hp_lost = 0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def take_hit(self, damage: int, from_x=None) -> bool:
        self.hp_lost += damage
        return False

    def roll_drop(self):
        return None


class _Player:
    x, y = 0.0, 100.0
    level = 10
    attack_hit_applied = False
    pending_skill = None

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-10, 60, 60, 60)

    def attack_range(self):
        return (100, 100)

    def magic_attack_range(self, skill_mad=0, skill_mastery=0):
        return (100, 100)

    def crit_rate(self) -> float:
        return 0.0

    def crit_mult(self) -> float:
        return 1.5

    def accuracy_value(self) -> int:
        return 100


class _Assets:
    footholds: list = []

    def skill_hit_frames(self, sid):
        return []


def _magic_player() -> _Player:
    """带 magic 标记的技能攻击者。"""
    p = _Player()
    p.pending_skill = {"id": "2001004", "damage": 1.0, "mob_count": 1,
                       "magic": True}
    return p


def _physical_player() -> _Player:
    """普通物理技能攻击者（skill 未标 magic）。"""
    p = _Player()
    p.pending_skill = {"id": "1001002", "damage": 1.0, "mob_count": 1}
    return p


def test_melee_magic_attack_uses_magic_defense():
    """魔法技能打高物防怪：只吃 mdd（0），伤害远高于 1。"""
    c = Combat(_Assets(), rng=random.Random(1))
    c.player_attack(_magic_player(), [_Mob()])
    assert c.numbers[-1].amount > 1


def test_melee_physical_attack_uses_physical_defense():
    """物理技能打同一只怪：吃 pd（5000），伤害被压到下限 1。"""
    c = Combat(_Assets(), rng=random.Random(1))
    c.player_attack(_physical_player(), [_Mob()])
    assert c.numbers[-1].amount == 1


def test_melee_normal_attack_without_magic_flag_uses_physical_defense():
    """普攻 skill=None：默认物理，仍用 pd 结算。"""
    c = Combat(_Assets(), rng=random.Random(1))
    c.player_attack(_Player(), [_Mob()])
    assert c.numbers[-1].amount == 1


def test_arrow_magic_attack_uses_magic_defense():
    """magic=True 的箭矢：吃 mdd（0），伤害远高于 1。"""
    c = Combat(_Assets(), rng=random.Random(1))
    mob = _Mob()
    a = Arrow(x=0.0, y=100.0, vx=0.0, vy=0.0, frames=[], hit_frames=[],
              dmg=10, atk_lo=100, atk_hi=100, mult=1.0, player_level=10,
              magic=True)
    a.update(1 / 60.0, [mob], c, player=_Player())
    assert c.numbers[-1].amount > 1


def test_arrow_without_magic_flag_uses_physical_defense():
    """未标 magic 的箭矢：默认物理，仍用 pd 结算。"""
    c = Combat(_Assets(), rng=random.Random(1))
    mob = _Mob()
    a = Arrow(x=0.0, y=100.0, vx=0.0, vy=0.0, frames=[], hit_frames=[],
              dmg=10, atk_lo=100, atk_hi=100, mult=1.0, player_level=10)
    a.update(1 / 60.0, [mob], c, player=_Player())
    assert c.numbers[-1].amount == 1
