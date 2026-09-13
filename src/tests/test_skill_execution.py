"""技能效果执行：Proc 触发、怪物状态施加、召唤物出手、地面区域结算。

seam：Combat._roll_procs / apply_status_to_mob / Summon / FieldEffect；
全部用合成 Player/Mob，不依赖 WZ 与 pygame 显示。
"""
from __future__ import annotations

import random
from types import SimpleNamespace

import pygame

from game.core.skill_spec import Proc
from game.systems.combat import Combat, FieldEffect, Summon


class FakeMob:
    def __init__(self, hp: int = 1000):
        self.x = 0.0
        self.cy = 0.0
        self.sprite_h = 10.0
        self.pd = 0
        self.mdd = 0
        self.eva = 0
        self.level = 1
        self.dead = False
        self.hp = hp
        self.max_hp = hp
        self.hits: list = []
        self.statuses: list = []

    def rect(self):
        return pygame.Rect(0, 0, 10, 10)

    def take_hit(self, damage, from_x=None):
        self.hits.append(damage)
        self.hp = max(0, self.hp - damage)
        return False        # 永不判死，避免触发掉落链路

    def apply_status(self, kind, duration, potency=0.0):
        self.statuses.append((kind, duration, potency))


class FakeSkills:
    def __init__(self, procs):
        self._procs = procs

    def combat_procs(self):
        return list(self._procs)


class FakePlayer:
    def __init__(self, procs=()):
        self.level = 1
        self.x = 0.0
        self.y = 0.0
        self.hp = 100
        self.max_hp = 100
        self.skills = FakeSkills(procs)

    def attack_range(self):
        return (100, 100)

    def crit_rate(self):
        return 0.0

    def crit_mult(self):
        return 1.5

    def accuracy_value(self):
        return 9999


def make_combat() -> Combat:
    return Combat(assets=None, drop_table=object(), rng=random.Random(0))


def test_roll_procs_final_attack_only_on_basic():
    """终极追击只由普攻触发：技能起手不触发，普攻触发并造成附加伤害。"""
    c = make_combat()
    player = FakePlayer([Proc("final_attack", chance=100, mult=2.0)])
    mob = FakeMob()
    c._roll_procs(player, mob, is_basic=False)
    assert mob.hits == []
    c._roll_procs(player, mob, is_basic=True)
    assert len(mob.hits) == 1


def test_roll_procs_critical_applies_to_skills():
    """暴击系 Proc 对技能攻击也生效。"""
    c = make_combat()
    player = FakePlayer([Proc("critical", chance=100, mult=1.5)])
    mob = FakeMob()
    c._roll_procs(player, mob, is_basic=False)
    assert len(mob.hits) == 1


def test_roll_procs_deadly_kills_below_threshold():
    """必杀：目标 HP% 低于阈值时按概率造成致命一击（伤害=当前 HP+1）。"""
    c = make_combat()
    proc = Proc("deadly", chance=100, mult=1.0, threshold=50)
    player = FakePlayer([proc])
    mob = FakeMob(hp=100)
    mob.hp = 30
    c._roll_procs(player, mob, is_basic=True)
    assert mob.hits == [31]

    mob2 = FakeMob(hp=100)
    mob2.hp = 80              # 高于阈值：不触发
    c._roll_procs(player, mob2, is_basic=True)
    assert mob2.hits == []


def test_apply_status_to_mob_dispatches():
    """状态施加优先走 apply_status，传入 (kind, duration, potency)。"""
    c = make_combat()
    mob = FakeMob()
    c.apply_status_to_mob(mob, "seal", 5.0, 0)
    assert mob.statuses == [("seal", 5.0, 0.0)]


def test_summon_attacks_nearest_within_range():
    """召唤物在半径内取最近怪出手，造成基于自身攻击力的伤害。"""
    c = make_combat()
    player = FakePlayer()
    mob = FakeMob()
    summon = Summon("3111005", 0.0, 0.0, attack=50, duration=5.0,
                    interval=0.2, frames={}, facing_right=True)
    summon._timer = 0.0
    summon.update(0.01, player, c, [mob])
    assert mob.hits and mob.hits[0] >= 1


def test_summon_expires_after_duration():
    c = make_combat()
    player = FakePlayer()
    summon = Summon("3111005", 0.0, 0.0, attack=10, duration=0.3,
                    interval=1.0, frames={}, facing_right=True)
    summon.update(0.31, player, c, [])
    assert summon._dying > 0 and not summon.dead
    summon.update(1.0, player, c, [])
    assert summon.dead


def test_field_ticks_damage_on_targets_in_area():
    """地面区域按间隔对框内目标结算伤害。"""
    c = make_combat()
    player = FakePlayer()
    mob = FakeMob()
    field = FieldEffect(0.0, 0.0, area=((-50, -50), (50, 50)), duration=5.0,
                        interval=1.0, layers=[],
                        payload={"damage": 1.0, "element": ""})
    field.update(1.1, player, c, [mob])
    assert mob.hits and mob.hits[0] >= 1


class NullAssets:
    def skill_summon_frames(self, skill_id, action="stand"):
        return []


def test_recast_summon_replaces_instead_of_stacking():
    """召唤共用一个槽位：重复施放（含换技）都替换，不得叠加。"""
    c = Combat(assets=NullAssets(), drop_table=object(), rng=random.Random(0))
    player = FakePlayer()
    hawk = {"id": "3111005",
            "summon": {"attack": 50, "duration": 100, "interval": 1.0}}
    phoenix = {"id": "3121006",
               "summon": {"attack": 550, "duration": 200, "interval": 1.0}}
    c.cast_summon(player, hawk)
    c.cast_summon(player, hawk)
    assert len(c.summons) == 1
    c.cast_summon(player, phoenix)
    assert len(c.summons) == 1 and c.summons[0].skill_id == "3121006"


def test_summon_records_total_and_name_for_hud():
    """召唤物带 total（灰蒙层倒计时用）与技能名（缺图标时的替身字）。"""
    c = Combat(assets=NullAssets(), drop_table=object(), rng=random.Random(0))
    player = FakePlayer()
    skill = {"id": "3111005", "def": SimpleNamespace(name="银鹰召唤"),
             "summon": {"attack": 50, "duration": 7.0, "interval": 1.0}}
    c.cast_summon(player, skill)
    s = c.summons[0]
    assert (s.total, s.name) == (7.0, "银鹰召唤")
    assert s.remaining == 7.0



def test_arrow_spawns_field_at_impact_point():
    """带地面载荷的弹道命中时，在落点生成区域（烈火箭燃烧对齐落点）。"""
    from game.systems.combat import Arrow
    c = make_combat()
    player = FakePlayer()
    mob = FakeMob()
    mob.x = 0.0
    arrow = Arrow(
        x=-0.0, y=0.0, vx=0.0, vy=0.0, frames=[], hit_frames=[],
        dmg=0, mob_count=1, life=0.1,
        atk_lo=10, atk_hi=10, mult=1.0, player_level=1,
        field_payload={"id": "3111003", "damage": 0.5,
                       "field": {"area": ((-50, -50), (50, 50)),
                                 "duration": 3.0, "interval": 1.0}})
    arrow.update(0.05, [mob], c, player)
    assert len(c.fields) == 1
    assert c.fields[0].x == 0.0 and c.fields[0].y == 0.0

