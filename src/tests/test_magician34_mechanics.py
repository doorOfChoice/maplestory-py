"""法师三/四转机制验收：召唤 mad、命中附带状态、净化、以及六项四转主动机制。

seam：core.skill_effects / core.skill_semantics 纯函数、Player 公开面板方法、
Combat.apply_mob_hits 公开行为。全部用合成 SkillDef 与替身，不依赖 WZ。
"""
from __future__ import annotations

import random

from game.core import skill_effects, skill_semantics, skill_spec
from game.core.stats import base_stats
from game.entities.player import Player
from game.systems.combat import Combat
from game.systems.inventory import Inventory, Item
from game.systems.skills import SkillBook, SkillDef


def make_skill(sid: str, lv: dict | None = None, **flags) -> SkillDef:
    return SkillDef(sid, sid, "", [dict(lv or {})], 1, **flags)


def effects(sid: str, lv: dict | None = None, **flags):
    return skill_semantics.effects(make_skill(sid, lv, **flags), 1)


# ── 数值登记（纯函数）────────────────────────────────────────────────
def test_fourth_job_buff_fields_registered():
    """冒险岛勇士→stat_pct、魔法狂暴→attack_speed、神圣祈祷→exp_bonus。"""
    assert skill_effects.buff_mods(
        "2121000", lambda k: {"x": 15}.get(k, 0)) == {"stat_pct": 15}
    assert skill_effects.buff_mods(
        "2111005", lambda k: {"x": -2}.get(k, 0)) == {"attack_speed": -2}
    assert skill_effects.buff_mods(
        "2311003", lambda k: {"x": 50}.get(k, 0)) == {"exp_bonus": 50}


def test_reflect_infinity_shield_fields_registered():
    """魔法反击→反射比例/概率、终极无限→no_mp_cost、圣灵之盾→status_immune。"""
    assert skill_effects.buff_mods(
        "2121002",
        lambda k: {"x": 200, "prop": 60}.get(k, 0)) == {
            "magic_reflect": 200, "magic_reflect_chance": 60}
    assert skill_effects.buff_mods(
        "2121004", lambda k: {"x": 1}.get(k, 0)) == {"no_mp_cost": 1}
    assert skill_effects.buff_mods(
        "2321005", lambda k: {"x": 1}.get(k, 0)) == {"status_immune": 1}


def test_magician_resistance_and_intensify_passives_registered():
    """抗性→mdmg_reduce；魔力激化→matk_pct(伤害%) 与 mp_cost_pct(耗蓝%)。"""
    assert skill_effects.passive_mods(
        "2310000", lambda k: {"x": 50}.get(k, 0)) == {"mdmg_reduce": 50}
    assert skill_effects.passive_mods(
        "2110001", lambda k: {"x": 200, "y": 140}.get(k, 0)) == {
            "matk_pct": 140, "mp_cost_pct": 200}


# ── 交付/效果语义 ────────────────────────────────────────────────────
def test_magic_summon_uses_mad_and_targets_mdef():
    """魔法召唤物（冰破魔兽）攻击力取 mad 且标记 magic；物理召唤物取 pad。"""
    magic = next(e for e in
                 effects("2121005", {"mad": 270, "time": 160}, has_summon=True)
                 if isinstance(e, skill_spec.Summon))
    assert magic.attack == 270 and magic.magic is True
    physical = next(e for e in
                    effects("3121006", {"pad": 180, "time": 120},
                            has_summon=True)
                    if isinstance(e, skill_spec.Summon))
    assert physical.attack == 180 and physical.magic is False


def _status_of(sid: str, lv: dict, **flags):
    eff = effects(sid, lv, **flags)
    dmg = next(e for e in eff if isinstance(e, skill_spec.Damage))
    assert dmg.status is not None
    return dmg.status.status


def test_attack_status_registered():
    """火毒合击→中毒；落霜冰破→冰冻；连环爆破→眩晕。"""
    assert _status_of("2111006", {"mad": 150, "time": 4, "prop": 41,
                                  "mobCount": 1},
                      has_ball=True, has_hit=True) == "poison"
    assert _status_of("2221007", {"mad": 570, "mobCount": 15, "time": 3},
                      has_hit=True, has_tile=True) == "freeze"
    assert _status_of("2121006", {"mad": 210, "time": 15, "prop": 100,
                                  "mobCount": 1}, has_hit=True) == "stun"


def test_cleanse_covers_bishop_hero_will_and_purify_not_reflect():
    """勇士的意志(2321009) 与净化(2311001) 产 Cleanse；魔法反击(2321002) 不产。"""
    hero = effects("2321009", {"mpCon": 30, "cooltime": 600, "time": 1})
    assert any(isinstance(e, skill_spec.Cleanse) for e in hero)
    purify = effects("2311001", {"mpCon": 15, "mobCount": 6, "prop": 34, "x": 1},
                     has_mob_icon=True, has_affected=True)
    assert any(isinstance(e, skill_spec.Cleanse) for e in purify)
    reflect = effects("2321002", {"mpCon": 26, "prop": 31, "time": 10, "x": 55})
    assert not any(isinstance(e, skill_spec.Cleanse) for e in reflect)


# ── Player 面板接线 ─────────────────────────────────────────────────
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
        id="01302000", name="木剑", kind="equip",
        info={"islot": "Wp", "incPAD": 25})
    self.skills = SkillBook(None, 0)
    self.quests = {}
    self.stats = base_stats()
    self.level = 50
    self.pending_skill = None
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


def make_player(monkeypatch) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _init)
    return Player(StubAssets(), 0.0, 0.0)


def _book_with_passive(sid: str, lv: dict) -> SkillBook:
    book = SkillBook(None, 2110, defs={sid: make_skill(sid, lv)})
    book.levels[sid] = 1
    return book


def test_mana_intensification_boosts_magic_and_mp_cost(monkeypatch):
    """魔力激化被动：魔法力 ×1.4（y=140）、MP 实付 ×2（x=200）。"""
    player = make_player(monkeypatch)
    base = player.magic_attack_value(with_buffs=False)
    player.skills = _book_with_passive("2110001", {"x": 200, "y": 140})
    assert player.magic_attack_value(with_buffs=False) == int(base * 1.4)
    assert player.mp_cost_rate() == 2.0
    assert player.skill_mp_cost(30) == 60


def test_magic_resistance_passive_reduces_magic_damage(monkeypatch):
    """魔法抗性被动（2310000 x=50）→ 魔法伤害减免 50%。"""
    player = make_player(monkeypatch)
    player.skills = _book_with_passive("2310000", {"x": 50})
    assert player.magic_damage_reduce() == 50


def test_infinity_buff_zeroes_skill_mp(monkeypatch):
    """终极无限 buff：持续内施法 MP 实付为 0。"""
    player = make_player(monkeypatch)
    assert player.skill_mp_cost(30) == 30
    player.buffs.apply("2121004", "终极无限", 40, {"no_mp_cost": 1})
    assert player.no_mp_cost() is True
    assert player.skill_mp_cost(30) == 0


def test_holy_symbol_exp_bonus_multiplies_gain(monkeypatch):
    """神圣祈祷 buff（exp_bonus 50%）→ 获得经验 ×1.5。"""
    player = make_player(monkeypatch)
    player.exp = 0
    player.buffs.apply("2311003", "神圣祈祷", 120, {"exp_bonus": 50})
    player.gain_exp(100)
    assert player.exp == 150


def test_magic_booster_raises_attack_speed(monkeypatch):
    """魔法狂暴 buff（attack_speed=-2）→ 攻速等级下降两级（更快）。"""
    player = make_player(monkeypatch)
    base = player.attack_speed_value()
    player.buffs.apply("2111005", "魔法狂暴", 100, {"attack_speed": -2})
    assert player.attack_speed_value() == base - 2


def test_reflect_and_shield_buff_readouts(monkeypatch):
    """魔法反击 buff 读出 (比例, 概率)；圣灵之盾 buff → status_immune。"""
    player = make_player(monkeypatch)
    player.buffs.apply("2121002", "魔法反击", 100,
                       {"magic_reflect": 150, "magic_reflect_chance": 60})
    assert player.magic_reflect() == (150, 60)
    player.buffs.apply("2321005", "圣灵之盾", 40, {"status_immune": 1})
    assert player.status_immune() is True


# ── Combat 反射 / 免疫 ───────────────────────────────────────────────
class _StatusRecorder:
    def __init__(self):
        self.applied = []

    def apply(self, kind, duration, potency=0.0):
        self.applied.append((kind, duration, potency))


class ReflectPlayer:
    x = 0.0
    y = 100.0
    level = 1

    def __init__(self, reflect=(0, 0), immune=False, magic_reduce=0):
        self._reflect = reflect
        self._immune = immune
        self._magic_reduce = magic_reduce
        self.statuses = _StatusRecorder()
        self.taken = []

    def is_invulnerable(self):
        return False

    def evasion_value(self):
        return 0

    def hurt(self, from_x):
        return True

    def defense_value(self):
        return 0

    def magic_defense_value(self):
        return 0

    def physical_damage_reduce(self):
        return 0

    def magic_damage_reduce(self):
        return self._magic_reduce

    def magic_reflect(self):
        return self._reflect

    def status_immune(self):
        return self._immune

    def take_attack_damage(self, amount):
        self.taken.append(amount)


class ReflectMob:
    max_hp = 1000
    x = 50.0
    cy = 100.0
    sprite_h = 30

    def __init__(self):
        self.hits = []

    def take_hit(self, dmg, from_x=None):
        self.hits.append(dmg)
        return False


class CombatAssets:
    def skill_ball_frames(self, sid, level=1):
        return []

    def skill_hit_frames(self, sid):
        return []


def test_magic_reflect_returns_damage_to_source():
    """魔法反击：受魔法攻击按 150% 返还，单次封顶来源 20% 最大体力。"""
    player = ReflectPlayer(reflect=(150, 100))
    mob = ReflectMob()
    hit = {"amount": 100, "acc": None, "x": 0, "magic": True,
           "level": 1, "source": mob}
    Combat(CombatAssets(), rng=random.Random(1)).apply_mob_hits(player, [hit])
    assert player.taken == [100]
    assert mob.hits == [150]


def test_magic_resistance_reduces_hit():
    """魔法抗性 50%：受到的魔法伤害减半。"""
    player = ReflectPlayer(magic_reduce=50)
    hit = {"amount": 100, "acc": None, "x": 0, "magic": True, "level": 1}
    Combat(CombatAssets(), rng=random.Random(1)).apply_mob_hits(player, [hit])
    assert player.taken == [50]


def test_status_immune_blocks_inflicted_status():
    """圣灵之盾：免疫时异常状态不入账；无免疫时正常入账。"""
    hit = {"amount": 10, "acc": None, "x": 0, "magic": False, "level": 1,
           "status_attacks": [{"kind": "poison", "duration": 5,
                               "potency": 3, "prob": 100}]}
    immune = ReflectPlayer(immune=True)
    Combat(CombatAssets(), rng=random.Random(1)).apply_mob_hits(immune, [hit])
    assert immune.statuses.applied == []
    normal = ReflectPlayer(immune=False)
    Combat(CombatAssets(), rng=random.Random(1)).apply_mob_hits(normal, [hit])
    assert normal.statuses.applied == [("poison", 5, 3)]
