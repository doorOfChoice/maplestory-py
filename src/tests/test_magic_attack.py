"""魔法攻击接线：玩家魔法区间公式 + 技能标记 + 战斗结算（合成资产，不依赖 WZ）。"""
from __future__ import annotations

import random

import pygame

from game import settings
from game.entities.player import Player
from game.systems.combat import Combat
from game.systems.inventory import Inventory, Item
from game.systems.skills import SkillBook, SkillDef


class StubAssets:
    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def _init(self, assets, quest_defs=None):
    self.inventory = Inventory()
    self.inventory.equipped["weapon"] = Item(
        id="01372005", name="木制短杖", kind="equip",
        info={"islot": "Wp", "incMAD": 23})
    self.skills = SkillBook(None, 2000)
    self.quests = {}
    self.stats = {"str": 4, "dex": 4, "int": 100, "luk": 10}
    self.level = 10
    self.job = 0
    self.pending_skill = None
    self.max_hp = 100
    self.max_mp = 100
    self.hp = 100
    self.mp = 100


def make_player(monkeypatch) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _init)
    return Player(StubAssets(), 0.0, 0.0)


def test_magic_attack_range_uses_weapon_mad(monkeypatch):
    """魔法区间上限 = (2×INT+LUK)×武器MAD/100；下限为基础熟练度比例。"""
    p = make_player(monkeypatch)
    lo, hi = p.magic_attack_range()
    assert hi == int((2 * 100 + 10) * 23 / 100.0)
    assert lo == int(hi * settings.MAGIC_BASE_MASTERY)


def test_magic_attack_range_folds_skill_mad_and_mastery(monkeypatch):
    """技能 mad 并入武器 MAD；技能 mastery 抬高下限（基础 10% + 10 点 = 20%）。"""
    p = make_player(monkeypatch)
    lo, hi = p.magic_attack_range(skill_mad=20, skill_mastery=10)
    assert hi == int((2 * 100 + 10) * 43 / 100.0)
    assert lo == int(hi * 0.20)


def test_magic_attack_range_never_below_one(monkeypatch):
    """无装备 MAD 时区间仍 ≥1，不出现 0 伤害。"""
    p = make_player(monkeypatch)
    p.inventory.equipped["weapon"] = Item(id="01302000", kind="equip",
                                          info={"islot": "Wp"})
    assert p.magic_attack_range() == (1, 1)


# ── 技能施放：魔法攻击技标记 ────────────────────────────────────────
def magic_book(skill_id: str, level_table: dict,
               has_ball: bool = False) -> SkillBook:
    d = SkillDef(skill_id, "魔法弹", "", [dict(level_table)], 1,
                 has_ball=has_ball)
    return SkillBook(None, settings.MAGICIAN_JOB, defs={skill_id: d})


MAGIC_BOLT_L1 = {"mpCon": 6, "mad": 20, "mastery": 1}


def test_cast_magic_bolt_marks_magic_projectile():
    """魔法弹（有 ball 节点）cast：标记 magic/projectile，用魔法弹速度。"""
    book = magic_book("2001004", MAGIC_BOLT_L1, has_ball=True)
    book.add_sp(200, 1)
    assert book.learn("2001004", 10)
    data = book.cast("2001004", 10)
    assert data["magic"] is True
    assert data["projectile"] is True
    assert data["skill_mad"] == 20
    assert data["skill_mastery"] == 1
    assert data["damage"] == 1.0            # 无 damage 字段 → 100%
    assert data["speed"] == settings.MAGIC_BALL_SPEED
    assert data["life"] == settings.MAGIC_BALL_LIFETIME


def test_cast_magic_claw_is_two_hit_instant_magic():
    """魔法双击（无 ball 节点）：标记 magic、attackCount=2，但不生成弹道。"""
    book = magic_book("2001005", {"mpCon": 10, "mad": 11, "mastery": 1,
                                  "attackCount": 2})
    book.add_sp(200, 1)
    assert book.learn("2001005", 10)
    data = book.cast("2001005", 10)
    assert data["magic"] is True
    assert data["attack_count"] == 2
    assert not data.get("projectile")
    assert data.get("cone_attack") is True     # 瞬发扇形，无弹道


def test_cast_magic_armor_buff_not_marked_magic_attack():
    """魔法铠甲（带 time 的 buff）：不被当成魔法攻击、不生成弹道。"""
    book = magic_book("2001003", {"mpCon": 8, "time": 54, "pdd": 2})
    book.add_sp(200, 1)
    assert book.learn("2001003", 10)
    data = book.cast("2001003", 10)
    assert data["magic"] is False
    assert "projectile" not in data


# ── 战斗结算：魔法技能用魔法区间（弹道/瞬发皆然）────────────────────
class _Mob:
    """高物防、零魔防的合成怪：只有魔法结算才可能打出 >1。"""

    x, cy, sprite_h, level = 10.0, 100.0, 30, 1
    pd = 5000
    mdd = 0
    eva = 0
    dead = False
    exp = 0
    mob_id = "9999999"

    def __init__(self, x: float = 10.0, cy: float = 100.0):
        self.x = x
        self.cy = cy

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def take_hit(self, damage: int, from_x=None) -> bool:
        return False

    def roll_drop(self):
        return None


class _CombatAssets:
    def __init__(self):
        self.ball = [(pygame.Surface((8, 8)), (4, 4), 100)]

    def skill_ball_frames(self, sid):
        return self.ball if sid == "2001004" else []

    def skill_hit_frames(self, sid):
        return []


class _RangePlayer:
    x, y = 0.0, 100.0
    facing_right = True
    level = 10
    attack_hit_applied = False
    pending_skill = None

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-10, 60, 60, 60)

    def attack_range(self):
        return (1, 1)                     # 物理区间极小：若误用物理必为 1

    def magic_attack_range(self, skill_mad=0, skill_mastery=0):
        return (100, 100)

    def crit_rate(self):
        return 0.0

    def crit_mult(self):
        return 1.5

    def accuracy_value(self):
        return 100


def _bolt_skill() -> dict:
    return {"id": "2001004", "damage": 1.0, "mob_count": 1,
            "bullet_count": 1, "attack_count": 1, "magic": True,
            "skill_mad": 20, "skill_mastery": 1, "projectile": True,
            "speed": settings.MAGIC_BALL_SPEED,
            "life": settings.MAGIC_BALL_LIFETIME}


def test_melee_magic_skill_uses_magic_attack_range():
    """魔法技能命中：伤害取自 magic_attack_range，而非物理 attack_range。"""
    combat = Combat(_CombatAssets(), rng=random.Random(1))
    player = _RangePlayer()
    player.pending_skill = _bolt_skill()
    combat.player_attack(player, [_Mob()])
    assert combat.numbers[-1].amount > 1


def test_spawn_magic_arrow_uses_magic_attack_range():
    """魔法弹弹道：atk 区间取自 magic_attack_range，带 magic 标记。"""
    combat = Combat(_CombatAssets(), rng=random.Random(1))
    combat.spawn_arrows(_RangePlayer(), _bolt_skill())
    assert len(combat.arrows) == 1
    a = combat.arrows[0]
    assert (a.atk_lo, a.atk_hi) == (100, 100)
    assert a.magic is True


def test_magic_claw_instant_fan_hits_front_targets_no_projectile():
    """魔法双击瞬发：命中朝向前方扇形内的怪（每只 attackCount 段），身后/超程不中。"""
    combat = Combat(_CombatAssets(), rng=random.Random(1))
    player = _RangePlayer()
    player.attack_hit_applied = False
    player.pending_skill = {"id": "2001005", "damage": 1.0, "mob_count": 2,
                            "bullet_count": 1, "attack_count": 2, "magic": True,
                            "skill_mad": 11, "skill_mastery": 1,
                            "cone_attack": True}
    near, far, behind = _Mob(200.0), _Mob(260.0, cy=110.0), _Mob(-200.0)
    out_of_range = _Mob(settings.ARROW_AIM_RADIUS + 300.0)
    combat.player_attack(player, [behind, near, far, out_of_range])
    assert combat.arrows == []
    assert {n.x for n in combat.numbers} == {200.0, 260.0}
    assert len(combat.numbers) == 4                       # 2 目标 × attackCount 2
    assert all(n.amount > 1 for n in combat.numbers)      # 用魔法区间而非物理


# ── 魔法盾：伤害转 MP ───────────────────────────────────────────────
def _guard_player(monkeypatch, hp: int, mp: int, pct: int):
    p = make_player(monkeypatch)
    p.hp, p.mp = hp, mp
    p.buffs.apply("2001002", "魔法盾", 60.0, {"magic_guard": pct})
    return p


def test_magic_guard_redirects_damage_to_mp(monkeypatch):
    """魔法盾 80%：50 伤害 → 扣 MP 40、扣 HP 10。"""
    p = _guard_player(monkeypatch, hp=100, mp=100, pct=80)
    assert p.take_attack_damage(50) == (10, 40)
    assert (p.hp, p.mp) == (90, 60)


def test_magic_guard_falls_back_to_hp_when_mp_empty(monkeypatch):
    """MP 不足以承担转扣部分：缺口回落扣 HP。"""
    p = _guard_player(monkeypatch, hp=100, mp=5, pct=80)
    assert p.take_attack_damage(50) == (45, 5)
    assert (p.hp, p.mp) == (55, 0)


def test_without_magic_guard_all_damage_to_hp(monkeypatch):
    """无魔法盾 buff：伤害全部扣 HP，MP 不变。"""
    p = make_player(monkeypatch)
    p.hp, p.mp = 100, 100
    assert p.take_attack_damage(30) == (30, 0)
    assert (p.hp, p.mp) == (70, 100)
