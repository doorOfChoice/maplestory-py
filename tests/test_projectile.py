"""远程箭矢弹道：直线飞行、命中结算、mobCount 上限、bulletCount 支数、寿命消失。"""
from __future__ import annotations

import pygame
import pytest

from game.combat import Arrow, Combat

pygame.init()


class FakeTarget:
    """合成怪物：暴露 rect()/take_hit()/x/cy/dead。"""

    def __init__(self, x: float, cy: float, w: int = 30, h: int = 30):
        self.x = x
        self.cy = cy
        self.w, self.h = w, h
        self.dead = False
        self.sprite_h = h
        self.exp = 0
        self.mob_id = "9999999"
        self.hits = 0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.w / 2), int(self.cy - self.h),
                           self.w, self.h)

    def take_hit(self, damage: int, from_x=None) -> bool:
        self.hits += 1
        return False


def arrow(x=0.0, y=0.0, vx=900.0, mob_count=1, life=0.6) -> Arrow:
    return Arrow(x=x, y=y, vx=vx, vy=0.0, frames=[], hit_frames=[],
                 dmg=10, mob_count=mob_count, life=life)


def test_arrow_hits_once_and_flies_straight():
    """一支箭命中单个 target：take_hit 恰好一次、y 不变（无重力）。"""
    a = arrow(x=-40.0, y=100.0)
    mob = FakeTarget(x=0.0, cy=110.0)
    combat = Combat(None)
    y0 = a.y
    for _ in range(20):
        a.update(1 / 60.0, [mob], combat, player=None)
    assert mob.hits == 1
    assert a.y == y0


def test_arrow_respects_mob_count():
    """mob_count=2：穿透结算前两只，第三只不再受伤。"""
    a = arrow(x=-40.0, y=100.0, mob_count=2, life=1.0)
    m1 = FakeTarget(x=0.0, cy=110.0)
    m2 = FakeTarget(x=60.0, cy=110.0)
    m3 = FakeTarget(x=120.0, cy=110.0)
    combat = Combat(None)
    for _ in range(60):
        a.update(1 / 60.0, [m1, m2, m3], combat, player=None)
    assert (m1.hits, m2.hits, m3.hits) == (1, 1, 0)


def test_arrow_despawns_after_lifetime():
    """寿命耗尽 → dead。"""
    a = arrow(x=-400.0, y=100.0, life=0.1)
    combat = Combat(None)
    for _ in range(12):
        a.update(1 / 60.0, [], combat, player=None)
    assert a.dead


def test_spawn_arrows_bullet_count():
    """bulletCount=2 → 一次生成 2 支箭。"""
    class FakeAssets:
        def skill_ball_frames(self, sid):
            return []
        def skill_hit_frames(self, sid):
            return []
    combat = Combat(FakeAssets())

    class P:
        x, y = 0.0, 100.0
        facing_right = True
        feet_y = 120.0
        level = 10
        def attack_value(self):
            return 50
        def attack_range(self):
            return (50, 50)
        def crit_rate(self):
            return 0.0
        def crit_mult(self):
            return 1.5
    skill = {"id": "3001005", "damage": 0.92, "mob_count": 1,
             "bullet_count": 2, "mp_con": 10, "hp_con": 0, "range": 0}
    combat.spawn_arrows(P(), skill)
    assert len(combat.arrows) == 2


def test_spawn_arrows_normal_attack():
    """弓/弩普攻（skill_data=None）生成一支箭：伤害=攻击力、用普攻箭矢贴图。"""
    sentinel = object()

    class FakeAssets:
        def skill_ball_frames(self, sid):
            raise AssertionError("普攻不应取技能 ball 贴图")
        def skill_hit_frames(self, sid):
            return []
        def normal_arrow_frames(self):
            return [sentinel]
    combat = Combat(FakeAssets())

    class P:
        x, y = 0.0, 100.0
        facing_right = True
        level = 10
        def attack_value(self):
            return 50
        def attack_range(self):
            return (50, 50)
        def crit_rate(self):
            return 0.0
        def crit_mult(self):
            return 1.5
    combat.spawn_arrows(P(), None)
    assert len(combat.arrows) == 1
    assert 47 <= combat.arrows[0].dmg <= 53      # 普攻伤害带 ±5% 浮动
    assert combat.arrows[0].frames == [sentinel]


def test_update_arrows_removes_dead():
    """Combat.update_arrows 移除已消失的箭。"""
    combat = Combat(None)
    combat.arrows.append(arrow(x=-400.0, life=0.05))
    for _ in range(10):
        combat.update_arrows(1 / 60.0, [], player=None)
    assert combat.arrows == []
