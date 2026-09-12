"""法师二转机制验收：属性克制、群体治愈、毒雾术、神之保护、三系魔力吸收、瞬移。

seam：Combat 公开行为（player_attack / apply_mob_hits / _absorb_mp / _apply_poison）
与 Player.teleport（合成 foothold，不依赖 WZ）。
"""
from __future__ import annotations

import math
import random

import pygame

from game import settings
from game.core import elements
from game.core.physics import Physics
from game.entities.player import Player
from game.systems.combat import Combat
from game.systems.skills import SkillBook, SkillDef


# ── 替身 ────────────────────────────────────────────────────────────
class Mob:
    level = 1
    eva = 0
    pd = 0
    mdd = 0
    dead = False
    exp = 0
    boss = False
    mob_id = "9999999"
    sprite_h = 30

    def __init__(self, x=100.0, cy=100.0, mp=0, max_mp=0,
                 max_hp=100, undead=False, elem=""):
        self.x = x
        self.cy = cy
        self.mp = mp
        self.max_mp = max_mp
        self.max_hp = max_hp
        self.undead = undead
        self.elem = elements.parse_elem_attr(elem)
        self.hits: list = []
        self.poison: list = []
        self.slow: list = []

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def element_multiplier(self, element) -> float:
        return elements.element_multiplier(self.elem, element)

    def take_hit(self, damage, from_x=None) -> bool:
        self.hits.append(damage)
        return False

    def take_dot(self, damage) -> bool:
        self.hits.append(damage)
        return False

    def apply_poison(self, dps, seconds) -> None:
        self.poison.append((dps, seconds))

    def apply_slow(self, mult, seconds) -> None:
        self.slow.append((mult, seconds))

    def roll_drop(self):
        return None


class FakePlayer:
    x = 0.0
    y = 100.0
    facing_right = True
    level = 30
    attack_hit_applied = False
    pending_skill = None

    def __init__(self):
        self.mp = 5
        self.max_mp = 999
        self.hp = 40
        self.max_hp = 100
        self.luk = 10
        self.skills = None

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-400, -400, 800, 800)

    def attack_range(self):
        return (1, 1)

    def attack_range_bonus(self):
        return 0.0

    def magic_attack_range(self, skill_mad=0, skill_mastery=0):
        return (100, 100)

    def total_stats(self):
        return {"int": 100}

    def magic_attack_value(self):
        return 100

    def crit_rate(self):
        return 0.0

    def crit_mult(self):
        return 1.5

    def accuracy_value(self):
        return 100


class Assets:
    def skill_ball_frames(self, sid):
        return []

    def skill_hit_frames(self, sid):
        return []


# ── 属性克制 ────────────────────────────────────────────────────────
def test_weak_target_takes_more_and_immune_takes_min_one():
    """火克弱火怪（×1.5）、免疫怪只吃 1 点，中性不变。"""
    from game.core import stats as stats_mod
    weak = Mob(elem="F3")
    immune = Mob(elem="F1")
    neutral = Mob()
    dmg = lambda mob: stats_mod.roll_damage(
        200, 200, 1.0, 0, 1, 1, random.Random(7),
        elem_mult=mob.element_multiplier("f"))[0]
    assert dmg(weak) > dmg(neutral)
    assert dmg(immune) == 1


def test_skill_element_reaches_melee_damage():
    """瞬发魔法带 elemAttr 时，弱火怪受到的伤害高于中性怪。"""
    skill = {"id": "2101004", "damage": 1.0, "mob_count": 1, "magic": True,
             "cone_attack": True, "skill_mad": 100, "skill_mastery": 1,
             "attack_count": 1, "element": "f"}
    out = []
    for elem in ("F3", ""):
        p = FakePlayer()
        p.pending_skill = dict(skill)
        mob = Mob(elem=elem)
        Combat(Assets(), rng=random.Random(3)).player_attack(p, [mob])
        out.append(mob.hits[0])
    assert out[0] > out[1]


# ── 群体治愈 ────────────────────────────────────────────────────────
def test_heal_restores_self_and_only_damages_undead():
    combat = Combat(Assets(), rng=random.Random(1))
    player = FakePlayer()
    player.pending_skill = {
        "id": "2301002", "form": "heal", "damage": 1.0, "mob_count": 6,
        "attack_count": 1, "magic": False, "heal_pct": 300,
        "area": ((-300, -200), (300, 200))}
    undead = Mob(undead=True)
    living = Mob(x=120.0)
    combat.player_attack(player, [undead, living])
    assert player.hp == 100          # 40 + 300%×100 → 封顶
    assert len(undead.hits) == 1
    assert living.hits == []


# ── 毒雾术 ──────────────────────────────────────────────────────────
def test_poison_dps_is_maxhp_over_70_minus_level():
    combat = Combat(Assets(), rng=random.Random(1))
    mob = Mob(max_hp=400)
    combat._apply_poison(mob, 40.0, 30)
    assert mob.poison == [(math.ceil(400 / 40), 40.0)]


# ── 魔力吸收（三系 + 上限按最大 MP 百分比）─────────────────────────
def _book(sid: str) -> SkillBook:
    return SkillBook(None, 2200, defs={
        sid: SkillDef(sid, "魔力吸收", "", [{"prop": 100, "x": 10}], 1)})


def test_absorb_uses_percent_of_max_mp_and_three_branch_ids():
    """吸收量 = 怪最大 MP × x%，且三系（210/220/230）任一均已接线。"""
    for sid in ("2100000", "2200000", "2300000"):
        combat = Combat(Assets(), rng=random.Random(1))
        player = FakePlayer()
        player.skills = _book(sid)
        player.skills.levels[sid] = 1
        player.pending_skill = {
            "id": "2001004", "damage": 1.0, "mob_count": 1, "magic": True,
            "cone_attack": True, "skill_mad": 20, "skill_mastery": 1,
            "attack_count": 1}
        player.attack_hit_applied = False
        mob = Mob(mp=500, max_mp=1000)
        combat.player_attack(player, [mob])
        assert (mob.mp, player.mp) == (400, 105)


# ── 神之保护（物理减伤）────────────────────────────────────────────
class DefPlayer:
    x = 0.0
    y = 100.0
    level = 30

    def __init__(self, reduce_pct=30):
        self.reduce_pct = reduce_pct
        self.taken: list = []

    def is_invulnerable(self):
        return False

    def hurt(self, x):
        return True

    def defense_value(self):
        return 0

    def magic_defense_value(self):
        return 0

    def physical_damage_reduce(self):
        return self.reduce_pct

    def take_attack_damage(self, amount):
        self.taken.append(amount)

    def on_dodge(self):
        pass

    def evasion_value(self):
        return 0


def test_invincible_reduces_physical_but_not_magic():
    hit = {"amount": 100, "acc": None, "x": 0, "magic": False, "level": 30}
    combat = Combat(Assets(), rng=random.Random(1))
    p = DefPlayer(30)
    combat.apply_mob_hits(p, [dict(hit)])
    assert p.taken == [70]

    p2 = DefPlayer(30)
    Combat(Assets(), rng=random.Random(1)).apply_mob_hits(
        p2, [dict(hit, magic=True)])
    assert p2.taken == [100]


# ── 快速移动（瞬移）──────────────────────────────────────────────────
def fh(fid, layer, x1, y1, x2, y2):
    return {"id": fid, "layer": layer, "platform": 0, "x1": x1, "y1": y1,
            "x2": x2, "y2": y2, "prev": -1, "next": -1}


def make_physics():
    return Physics([fh(1, 0, 0, 100, 400, 100),
                    fh(2, 0, 500, 100, 900, 100),
                    fh(3, 0, 0, 60, 400, 60)],
                   [], bounds={"left": -100, "right": 1000,
                               "top": 0, "width": 1200, "height": 500})


def _make_player(monkeypatch) -> Player:
    def _init(self, assets, quest_defs=None):
        self.skills = SkillBook(None, 0)
        self.quests = {}
        self.inventory = None
        self.stats = {"str": 4, "dex": 4, "int": 4, "luk": 4}
        self.level = 30
        self.job = 2200
        self.mp = 100
        self.max_mp = 100
        self.hp = 100
        self.max_hp = 100
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _init)
    p = Player(Assets(), 200.0, 100.0 - settings.FEET_OFFSET)
    p.on_ground = True
    p.ground_layer = 0
    return p


def test_teleport_horizontal_snaps_to_platform(monkeypatch):
    p = _make_player(monkeypatch)
    ph = make_physics()
    p.cur_fh = ph.surface_under(p.x, p.y + settings.FEET_OFFSET)
    assert p.teleport(150, ph) is True
    assert abs(p.x - 350.0) < 1e-6
    assert p.on_ground and abs(p.y - (100 - settings.FEET_OFFSET)) < 1e-6


def test_teleport_up_lands_on_upper_platform(monkeypatch):
    p = _make_player(monkeypatch)
    ph = make_physics()
    assert p.teleport(50, ph, up=True) is True
    assert abs(p.y - (60 - settings.FEET_OFFSET)) < 1e-6
    assert p.on_ground


def test_teleport_horizontal_over_void_stays(monkeypatch):
    """水平瞬移到无底缺口上方 → 原地不动，不掉出世界（return False）。"""
    p = _make_player(monkeypatch)
    p.x = 380.0
    ph = make_physics()
    p.cur_fh = ph.surface_under(p.x, p.y + settings.FEET_OFFSET)
    before_x = p.x
    assert p.teleport(60, ph) is False
    assert p.x == before_x and p.on_ground is True
