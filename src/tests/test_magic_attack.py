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
    def character_frames(self, equips, pose, flip=False):
        return [("frame", 100)] if pose == "alert2" else []

    def character_navel_px(self, equips, pose, flip=False):
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


def test_magic_power_is_int_plus_weapon_mad(monkeypatch):
    """面板魔法力（旧版 Magic）= 总 INT + 武器 M.ATK。"""
    p = make_player(monkeypatch)
    assert p.magic_attack_value() == 100 + 23


def test_magic_attack_range_follows_old_spell_formula(monkeypatch):
    """技能 mad 作为 Basic 乘数：Magic=123、INT=100、Basic=35 → term=138.129。

    Max=(138.129/30+0.5)×35=178.65→178；基础 10% 熟练下限=33.615→33。
    """
    p = make_player(monkeypatch)
    lo, hi = p.magic_attack_range(skill_mad=35, skill_mastery=0)
    assert (lo, hi) == (33, 178)


def test_skill_mastery_raises_magic_lower_bound(monkeypatch):
    """技能 mastery 只抬下限、不改上限：满 10 点 → 下限比例 0.60。"""
    p = make_player(monkeypatch)
    lo0, hi0 = p.magic_attack_range(skill_mad=35, skill_mastery=0)
    lo1, hi1 = p.magic_attack_range(skill_mad=35, skill_mastery=10)
    assert hi1 == hi0
    assert lo1 > lo0
    term = 123 * 123 / 1000.0 + 123
    assert lo1 == int((term * 0.60 / 30 + 100 / 200) * 35)


def test_magic_attack_range_never_below_one(monkeypatch):
    """无技能 Basic（mad=0）时区间为 (1,1)，不出现 0 伤害。"""
    p = make_player(monkeypatch)
    assert p.magic_attack_range() == (1, 1)


# ── 技能施放：魔法攻击技标记 ────────────────────────────────────────
def magic_book(skill_id: str, level_table: dict,
               has_ball: bool = False, has_hit: bool = False,
               has_mob_icon: bool = False) -> SkillBook:
    d = SkillDef(skill_id, "魔法弹", "", [dict(level_table)], 1,
                 has_ball=has_ball, has_hit=has_hit,
                 has_mob_icon=has_mob_icon)
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


def test_cast_magic_exposes_wz_area_box():
    """雷电术（hit + lt/rb）：cast 判为 aoe，暴露 area 矩形（供自身 AOE 结算）。"""
    book = magic_book("2201005", {"mpCon": 20, "mad": 2, "mastery": 1,
                                  "lt": (-150, -50), "rb": (150, 50),
                                  "mobCount": 6}, has_hit=True)
    book.add_sp(220, 1)
    assert book.learn("2201005", 30)
    data = book.cast("2201005", 30)
    assert data["form"] == "aoe"
    assert data["magic"] is True
    assert data.get("cone_attack") is True
    assert data["area"] == ((-150, -50), (150, 50))


def test_cast_magic_without_box_has_no_area():
    """魔法双击无 lt/rb：area 为 None，仍走瞄准扇形。"""
    book = magic_book("2001005", {"mpCon": 10, "mad": 11, "mastery": 1,
                                  "attackCount": 2})
    book.add_sp(200, 1)
    assert book.learn("2001005", 10)
    data = book.cast("2001005", 10)
    assert data["area"] is None


def test_cast_cold_beam_is_magic_attack_with_freeze():
    """冰冻术：带 time 但 WZ 有 hit 节点 → 魔法攻击，time 记为冻结秒数。"""
    book = magic_book("2201004", {"mpCon": 12, "mad": 13, "mastery": 1,
                                  "x": -100, "time": 1}, has_hit=True)
    book.add_sp(220, 1)
    assert book.learn("2201004", 30)
    data = book.cast("2201004", 30)
    assert data["magic"] is True
    assert data.get("cone_attack") is True
    assert data["freeze"] == 1.0


def test_cast_slow_skill_is_area_debuff_not_attack():
    """缓速术：WZ 带 mob 节点且无伤害 → 怪物 debuff 形态，带范围与减速幅度/时长。"""
    book = magic_book("2201003", {"mpCon": 8, "x": -20, "time": 20,
                                  "lt": (-200, -150), "rb": (200, 150),
                                  "mobCount": 6}, has_mob_icon=True)
    book.add_sp(220, 1)
    assert book.learn("2201003", 30)
    data = book.cast("2201003", 30)
    assert data.get("form") == "mob_status"
    assert data["status"] == "slow"
    assert data["magic"] is False
    assert data["area"] == ((-200, -150), (200, 150))
    assert data["slow_x"] == -20
    assert data["duration"] == 20


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


def test_magic_area_box_hits_both_sides_not_limited_to_facing():
    """带 area 的瞬发魔法：按角色周围 WZ 矩形结算（左右两侧都中），矩形外不中。"""
    combat = Combat(_CombatAssets(), rng=random.Random(1))
    player = _RangePlayer()
    player.attack_hit_applied = False
    player.pending_skill = {"id": "2201005", "damage": 1.0, "mob_count": 6,
                            "bullet_count": 1, "attack_count": 1, "magic": True,
                            "skill_mad": 2, "skill_mastery": 1,
                            "cone_attack": True,
                            "area": ((-150, -50), (150, 50))}
    front = _Mob(100.0, cy=100.0)
    behind = _Mob(-100.0, cy=100.0)
    too_far = _Mob(400.0, cy=100.0)
    combat.player_attack(player, [front, behind, too_far])
    assert {n.x for n in combat.numbers} == {100.0, -100.0}


def test_magic_area_box_respects_mob_count():
    """area 命中数受 mobCount 限制，按距离取最近。"""
    combat = Combat(_CombatAssets(), rng=random.Random(1))
    player = _RangePlayer()
    player.attack_hit_applied = False
    player.pending_skill = {"id": "2201005", "damage": 1.0, "mob_count": 2,
                            "bullet_count": 1, "attack_count": 1, "magic": True,
                            "skill_mad": 2, "skill_mastery": 1,
                            "cone_attack": True,
                            "area": ((-150, -50), (150, 50))}
    combat.player_attack(player, [_Mob(40.0), _Mob(80.0), _Mob(120.0)])
    assert {n.x for n in combat.numbers} == {40.0, 80.0}


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


# ── WZ action：官方施法动作 ─────────────────────────────────────────
def _live_pose_player(monkeypatch) -> Player:
    """构造真跑 _load_anim 的 Player（只把 pose 记下，不合成像素）。"""
    p = make_player(monkeypatch)
    monkeypatch.setattr(
        Player, "_load_anim",
        lambda self, pose, flip=None: setattr(self, "pose", pose))
    return p


def _slow_data(action: str) -> dict:
    d = SkillDef("2201003", "缓速术", "", [{"mobCount": 6, "time": 2, "x": -2}], 1,
                 has_mob_icon=True)
    return {"id": "2201003", "def": d, "level": 1, "action": action,
            "form": "mob_status", "mp_con": 0, "hp_con": 0, "damage": 1.0,
            "range": 0, "mob_count": 6, "bullet_count": 1, "attack_count": 1}


def test_skill_wz_action_overrides_weapon_attack_pose(monkeypatch):
    """技能声明 WZ action（缓速术 alert2）且身体含该姿态时，出手用官方施法动作。"""
    p = _live_pose_player(monkeypatch)
    assert p.start_attack(_slow_data("alert2")) is True
    assert p.pose == "alert2"


def test_missing_action_falls_back_to_weapon_pose(monkeypatch):
    """身体不含该 action（StubAssets 只认 alert2）时回退武器攻击姿态。"""
    p = _live_pose_player(monkeypatch)
    assert p.start_attack(_slow_data("nonexistent")) is True
    assert p.pose == "swingO1"
