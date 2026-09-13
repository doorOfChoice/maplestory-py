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
        self.taken = []

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - self.w / 2), int(self.cy - self.h),
                           self.w, self.h)

    def take_hit(self, damage: int, from_x=None) -> bool:
        self.hits += 1
        self.taken.append(damage)
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
        def skill_ball_frames(self, sid, level=1):
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
        def skill_ball_frames(self, sid, level=1):
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
    assert combat.arrows[0].atk_hi == 50         # 普攻倍率 1.0、面板上限 50
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
        def skill_ball_frames(self, sid, level=1):
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
    near = FakeTarget(x=150.0, cy=162.0, h=80)   # 中心 (150,122) 在下方、扇形内
    far = FakeTarget(x=230.0, cy=92.0, h=80)      # 中心 (230,52) 在上方、扇形内但更远
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


def test_spawn_arrows_ignores_mob_outside_fan():
    """圈内但夹角超出瞄准扇形（几乎正上方）的怪：不瞄，直射。"""
    combat = combat_with_balls()
    # 身体中心 (40, -68)：距手点(0,92) 约 165 < 360，但与水平夹角约 76° > 30°
    mob = FakeTarget(x=40.0, cy=-28.0, h=80)
    combat.spawn_arrows(AimP(), None, [mob])
    assert combat.arrows[0].vy == 0.0


def test_spawn_arrows_aims_at_mob_in_fan_edge():
    """扇形边缘内（约 10° 斜上方）的怪仍会被瞄。"""
    combat = combat_with_balls()
    mob = FakeTarget(x=200.0, cy=97.0, h=80)    # 身体中心 (200, 57)，俯角约 10° < 15°
    combat.spawn_arrows(AimP(), None, [mob])
    assert combat.arrows[0].vy < 0.0


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


def test_skill_arrow_noncrit_hit_uses_red_numbers():
    """技能箭非暴击命中：飘字用普攻红字（NoRed），只有暴击才染紫。"""
    combat = combat_with_balls()
    mob = FakeTarget(x=120.0, cy=110.0)
    skill = {"id": "3001005", "damage": 0.92, "mob_count": 1,
             "bullet_count": 1, "mp_con": 10, "hp_con": 0, "range": 0}
    combat.spawn_arrows(AimP(), skill, [mob])
    for _ in range(60):
        combat.update_arrows(1 / 60.0, [mob], player=None)
    assert len(combat.numbers) == 1
    n = combat.numbers[0]
    assert n.kind == "red" and n.big is False


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


# ── 命中伤害与近战统一：走 stats.roll_damage（等级差 + 怪防 + 逐次暴击）──
import random as _random


def aimed_arrow(target, **kw) -> tuple[Arrow, Combat]:
    params = dict(x=-20.0, y=100.0, vx=900.0, vy=0.0, frames=[], hit_frames=[],
                  dmg=0, atk_lo=100, atk_hi=100, mult=1.0, player_level=1,
                  crit_rate=0.0, life=0.3)
    params.update(kw)
    a = Arrow(**params)
    combat = Combat(None, rng=_random.Random(0))
    for _ in range(20):
        a.update(1 / 60.0, [target], combat, player=None)
    return a, combat


def test_arrow_damage_falls_with_level_difference():
    """越级命中：怪等级远高于玩家时，箭伤按等级差衰减（与近战同公式）。"""
    same = FakeTarget(x=0.0, cy=100.0)
    higher = FakeTarget(x=0.0, cy=100.0)
    higher.level = 50
    _, c1 = aimed_arrow(same)
    _, c2 = aimed_arrow(higher)
    assert c2.numbers[0].amount < c1.numbers[0].amount


def test_arrow_damage_reduced_by_mob_defense():
    """怪防生效：高 weaponDefense 的目标挨的箭伤更低。"""
    soft = FakeTarget(x=0.0, cy=100.0)
    armored = FakeTarget(x=0.0, cy=100.0)
    armored.pd = 100
    _, c1 = aimed_arrow(soft)
    _, c2 = aimed_arrow(armored)
    assert c2.numbers[0].amount < c1.numbers[0].amount


def test_arrow_attack_count_strikes_multiple_times():
    """attackCount=3：单箭对同一目标结算三段伤害。"""
    mob = FakeTarget(x=0.0, cy=100.0)
    aimed_arrow(mob, attack_count=3)
    assert mob.hits == 3
    assert len(mob.taken) == 3


def test_spawn_arrows_rolls_crit_per_hit_not_per_arrow():
    """多支箭各自命中时分别判暴击（暴击率 100% 时每段都暴击染紫）。"""
    combat = combat_with_balls()
    mob = FakeTarget(x=120.0, cy=110.0)

    class CritP(AimP):
        def crit_rate(self):
            return 100.0

    skill = {"id": "3001005", "damage": 1.0, "mob_count": 1,
             "bullet_count": 2, "mp_con": 10, "hp_con": 0, "range": 0}
    combat.spawn_arrows(CritP(), skill, [mob])
    for _ in range(60):
        combat.update_arrows(1 / 60.0, [mob], player=None)
    assert combat.numbers and all(n.kind == "violet" for n in combat.numbers)


# ── 命中特效朝向：素材朝左，按弹道方向镜像 ──────────────────────────
def _hit_frame() -> tuple:
    return (pygame.Surface((4, 4)), (2, 4), 100)


def test_arrow_hit_effect_flips_when_flying_right():
    """向右飞的箭命中：命中特效镜像，冲击朝右。"""
    combat = Combat(None)
    mob = FakeTarget(x=0.0, cy=110.0)
    a = Arrow(x=-40.0, y=100.0, vx=900.0, vy=0.0, frames=[],
              hit_frames=[_hit_frame()], dmg=10)
    for _ in range(20):
        a.update(1 / 60.0, [mob], combat, player=None)
    assert combat.effects[-1].flip is True


def test_arrow_hit_effect_unflipped_when_flying_left():
    """向左飞的箭命中：命中特效保持素材原样（朝左）。"""
    combat = Combat(None)
    mob = FakeTarget(x=0.0, cy=110.0)
    a = Arrow(x=40.0, y=100.0, vx=-900.0, vy=0.0, frames=[],
              hit_frames=[_hit_frame()], dmg=10)
    for _ in range(20):
        a.update(1 / 60.0, [mob], combat, player=None)
    assert combat.effects[-1].flip is False


# ── 弹道贴图朝向：素材朝左，按飞行方向镜像，箭头指向飞行方向 ─────────
class _Camera:
    """把世界 x 平移到屏幕 +10，避免 2px 贴图被画布边缘裁掉。"""

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        return (int(x) + 10, int(y))


def _dir_arrow(vx: float) -> tuple[Arrow, pygame.Surface]:
    surf = pygame.Surface((2, 1), pygame.SRCALPHA)
    surf.set_at((0, 0), (255, 0, 0, 255))     # 素材左端 = 箭头（朝左）
    surf.set_at((1, 0), (0, 0, 255, 255))
    a = Arrow(x=0.0, y=0.0, vx=vx, vy=0.0,
              frames=[(surf, (1, 0), 100)], hit_frames=[], dmg=1)
    canvas = pygame.Surface((20, 1))
    canvas.fill((0, 0, 0))
    a.draw(canvas, _Camera())
    return a, canvas


def test_arrow_flips_to_point_right_when_flying_right():
    """向右飞：素材朝左 → 镜像，箭头（红）落到右侧。"""
    _, canvas = _dir_arrow(900.0)
    assert canvas.get_at((11, 0))[:3] == (255, 0, 0)


def test_arrow_keeps_left_when_flying_left():
    """向左飞：素材朝左 → 不镜像，箭头（红）留在左侧。"""
    _, canvas = _dir_arrow(-900.0)
    assert canvas.get_at((9, 0))[:3] == (255, 0, 0)


class _CenterCamera:
    """世界原点映射到画布中心的相机桩。"""

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        return (60, 60)


def test_arrow_diagonal_rotation_points_along_travel():
    """斜射（右上）：素材朝左，旋转后箭头（红）应偏向飞行方向的右上。"""
    surf = pygame.Surface((9, 3), pygame.SRCALPHA)
    pygame.draw.rect(surf, (255, 0, 0, 255), (0, 0, 3, 3))     # 头（左端）
    pygame.draw.rect(surf, (0, 0, 255, 255), (6, 0, 3, 3))     # 尾
    a = Arrow(x=0.0, y=0.0, vx=900.0, vy=-900.0,
              frames=[(surf, (4, 1), 100)], hit_frames=[], dmg=1)
    canvas = pygame.Surface((120, 120))
    canvas.fill((0, 0, 0))
    a.draw(canvas, _CenterCamera())

    xs, ys = [], []
    for x in range(120):
        for y in range(120):
            r, _g, b, *_ = canvas.get_at((x, y))
            if r > 150 and b < 100:
                xs.append(x)
                ys.append(y)
    assert xs and sum(xs) / len(xs) > 60 and sum(ys) / len(ys) < 60
