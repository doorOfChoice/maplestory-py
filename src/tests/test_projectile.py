"""远程箭矢弹道：直线飞行、命中结算、mobCount 上限、bulletCount 支数、寿命消失。"""
from __future__ import annotations

import pygame
import pytest

from game.systems.combat import Arrow, Combat

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
        self.pd = 0
        self.level = 0
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


# ── 原版式瞄准：射程圈内朝向上的最近怪，箭沿其方向斜射 ──────────────
import math


class AimP:
    x, y = 0.0, 100.0
    facing_right = True
    level = 10
    def attack_range(self):
        return (50, 50)
    def crit_rate(self):
        return 0.0
    def crit_mult(self):
        return 1.5


def combat_with_balls() -> Combat:
    class FakeAssets:
        def skill_ball_frames(self, sid):
            return []
        def skill_hit_frames(self, sid):
            return []
        def normal_arrow_frames(self):
            return []
    return Combat(FakeAssets())


def test_spawn_arrows_aims_at_mob_above():
    """圈内上方有怪：朝其中心斜射，合速仍为 ARROW_SPEED。"""
    from game import settings
    combat = combat_with_balls()
    mob = FakeTarget(x=200.0, cy=110.0, h=80)   # 身体中心 (200, 70) 在手点(16,92)上方
    combat.spawn_arrows(AimP(), None, [mob])
    a = combat.arrows[0]
    assert a.vx > 0 and a.vy < 0                # 上方怪 → 向上斜射
    assert math.isclose(math.hypot(a.vx, a.vy), settings.ARROW_SPEED, rel_tol=1e-3)


def test_spawn_arrows_aim_prefers_nearest():
    """圈内有两只怪：瞄准更近的那只方向。"""
    combat = combat_with_balls()
    near = FakeTarget(x=150.0, cy=210.0, h=80)   # 中心 (150,170) 在下方
    far = FakeTarget(x=230.0, cy=60.0, h=80)      # 中心 (230,20) 在上方
    combat.spawn_arrows(AimP(), None, [far, near])
    assert combat.arrows[0].vy > 0               # 近怪在下 → 向下射


def test_spawn_arrows_ignores_mob_behind():
    """身后的怪不瞄：保持水平直射。"""
    combat = combat_with_balls()
    mob = FakeTarget(x=-200.0, cy=140.0, h=80)
    combat.spawn_arrows(AimP(), None, [mob])
    assert combat.arrows[0].vy == 0.0


def test_spawn_arrows_out_of_radius_fires_straight():
    """超出瞄准圈的怪：直射。"""
    from game import settings
    combat = combat_with_balls()
    mob = FakeTarget(x=settings.ARROW_AIM_RADIUS + 300.0, cy=140.0, h=80)
    combat.spawn_arrows(AimP(), None, [mob])
    assert combat.arrows[0].vy == 0.0


def test_spawn_arrows_all_bullets_aim_same_target():
    """多支箭（双发类技能）瞄向同一最近目标。"""
    combat = combat_with_balls()
    mob = FakeTarget(x=180.0, cy=160.0, h=80)
    skill = {"id": "3001005", "damage": 0.92, "mob_count": 1,
             "bullet_count": 2, "mp_con": 10, "hp_con": 0, "range": 0}
    combat.spawn_arrows(AimP(), skill, [mob])
    assert len(combat.arrows) == 2
    assert combat.arrows[0].vy > 0 and combat.arrows[1].vy > 0
    assert abs(combat.arrows[0].vx - combat.arrows[1].vx) < 10.0  # 近平行同目标


def test_aimed_arrow_flies_straight_line():
    """斜射箭沿直线匀速前进（无重力）。"""
    combat = combat_with_balls()
    mob = FakeTarget(x=200.0, cy=110.0, h=80)
    combat.spawn_arrows(AimP(), None, [mob])
    a = combat.arrows[0]
    sx, sy, ratio = a.x, a.y, a.vy / a.vx
    for _ in range(10):
        a.update(1 / 60.0, [], combat, player=None)   # 怪移开：不转向、保持直线
    assert math.isclose((a.y - sy) / (a.x - sx), ratio, rel_tol=1e-6)
