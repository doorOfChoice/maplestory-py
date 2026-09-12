"""命中/回避实战结算：玩家攻怪按 命中 vs 怪回避 roll，怪打工按 怪命中 vs 玩家回避 roll。"""
from __future__ import annotations

import random

import pygame

from game.core.physics import Physics
from game.entities.monster import Monster
from game.systems.combat import Combat


class _Mob:
    x, cy, sprite_h, level, pd = 10.0, 100.0, 30, 1, 0
    dead = False
    exp = 0
    mob_id = "100101"
    name = "蓝蜗牛"
    acc = 30
    eva = 0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def take_hit(self, damage: int, from_x=None) -> bool:
        self.hp_lost = getattr(self, "hp_lost", 0) + damage
        return False

    def roll_drop(self):
        return None


class _Player:
    x, y = 0.0, 100.0
    level = 10
    luk = 0
    attack_hit_applied = False
    pending_skill = None

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-10, 60, 60, 60)

    def attack_range(self):
        return (50, 50)

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


def test_melee_miss_when_roll_exceeds_hit_chance():
    """命中概率极低 + rng 掷高：怪不掉血，飘 0 点 Miss 数字。"""
    c = Combat(_Assets(), rng=random.Random(2))   # 首次 random() ≈ 0.954
    mob = _Mob()
    mob.eva = 9900                                 # 概率 100/10000 → 极低
    c.player_attack(_Player(), [mob])
    assert getattr(mob, "hp_lost", 0) == 0
    assert [n.amount for n in c.numbers] == [0]


def test_melee_hits_when_no_evasion():
    """怪回避为 0 → 命中概率到 95% 天花板，低骰必中掉血。"""
    c = Combat(_Assets(), rng=random.Random(1))   # 首次 random() ≈ 0.134
    mob = _Mob()
    c.player_attack(_Player(), [mob])
    assert mob.hp_lost > 0
    assert all(n.amount > 0 for n in c.numbers)


def test_arrow_miss_shows_miss_and_deals_no_damage():
    """箭矢接触判定：掷骰超过命中概率 → 怪不掉血、飘 Miss、箭仍被消耗。"""
    from game.systems.combat import Arrow
    c = Combat(_Assets(), rng=random.Random(2))       # 首次 random() ≈ 0.954
    mob = _Mob()
    mob.eva = 9900
    a = Arrow(x=0.0, y=100.0, vx=0.0, vy=0.0, frames=[], hit_frames=[],
              dmg=10)
    a.update(1 / 60.0, [mob], c, player=_Player())
    assert getattr(mob, "hp_lost", 0) == 0
    assert [n.amount for n in c.numbers] == [0]
    assert a.dead


def test_arrow_hits_when_no_evasion():
    """怪回避为 0 的箭（95% 天花板）低骰必中：掉血 + 正常伤害数字。"""
    from game.systems.combat import Arrow
    c = Combat(_Assets(), rng=random.Random(1))
    mob = _Mob()
    a = Arrow(x=0.0, y=100.0, vx=0.0, vy=0.0, frames=[], hit_frames=[],
              dmg=10)
    a.update(1 / 60.0, [mob], c, player=_Player())
    assert mob.hp_lost > 0
    assert a.dead                                   # 单发命中后照常回收


class _HitPlayer:
    """受击侧假玩家：记录实际扣血，回避/防御可控。"""

    x, y = 100.0, 100.0
    level = 10

    def __init__(self, evasion: int = 0):
        self.evasion = evasion
        self.dealt: list = []

    def hurt(self, from_x) -> bool:
        return True

    def damage(self, amount: int) -> None:
        self.dealt.append(amount)

    def defense_value(self) -> int:
        return 0

    def magic_defense_value(self) -> int:
        return 0

    def evasion_value(self) -> int:
        return self.evasion


def test_player_evades_mob_contact_when_evasion_overwhelming():
    """玩家回避远高于怪命中 + rng 掷高：不掉血、飘蓝色 Miss。"""
    c = Combat(None, rng=random.Random(2))          # 首次 random() ≈ 0.954
    player = _HitPlayer(evasion=10 ** 6)
    c.apply_mob_hits(player, [{"x": 0.0, "amount": 20, "acc": 30}])
    assert player.dealt == []
    assert [(n.amount, n.kind) for n in c.numbers] == [(0, "blue")]


def test_mob_contact_hits_player_when_no_evasion():
    """怪必中骰（等级差 0、玩家回避 0 → 95% 天花板）低骰命中：照常掉血。"""
    c = Combat(None, rng=random.Random(1))
    player = _HitPlayer(evasion=0)
    c.apply_mob_hits(player, [{"x": 0.0, "amount": 20, "acc": 30}])
    assert player.dealt == [20]
    assert c.numbers == [] or all(n.amount > 0 for n in c.numbers)


def test_contact_hit_without_acc_field_always_lands():
    """hit 未带 acc（旧契约/Lua 来源）：不做回避判定，必中。"""
    c = Combat(None, rng=random.Random(2))
    player = _HitPlayer(evasion=10 ** 6)
    c.apply_mob_hits(player, [{"x": 0.0, "amount": 20}])
    assert player.dealt == [20]


class _DefPlayer(_HitPlayer):
    """可控双防的受击假玩家。"""

    def __init__(self, defense: int, mdef: int):
        super().__init__(evasion=0)
        self.defense, self.mdef = defense, mdef

    def defense_value(self) -> int:
        return self.defense

    def magic_defense_value(self) -> int:
        return self.mdef


def test_magic_hit_reduced_by_magic_defense_not_physical():
    """magic 标记的接触伤害：只吃魔法防御，物理防御 300 不掺和。"""
    c = Combat(None, rng=random.Random(1))          # 低骰保证判定命中
    player = _DefPlayer(defense=300, mdef=0)
    c.apply_mob_hits(player, [{"x": 0.0, "amount": 20, "acc": 30,
                               "magic": True}])
    assert player.dealt == [20]


def test_physical_hit_still_reduced_by_physical_defense():
    """无 magic 标记：照旧由物理防御减免。"""
    c = Combat(None, rng=random.Random(1))
    player = _DefPlayer(defense=300, mdef=0)
    c.apply_mob_hits(player, [{"x": 0.0, "amount": 20, "acc": 30}])
    assert player.dealt == [5]


# ── 怪物侧：魔攻高于物攻的怪用魔法接触伤害 ──────────────────────────
def _mob_hit(stats: dict) -> dict:
    """合成怪贴身打玩家一次，回传接触伤害 hit。"""

    class _A:
        def mob_info(self, _id):
            return {"name": "T", "stats": stats, "drops": []}

        def mob_frames(self, _id, action, flip=False):
            return [(pygame.Surface((12, 12)), 100)] \
                if action in ("stand", "move") else []

        def mob_origin(self, _id, action):
            return (0, 0)

    seg = {"id": 1, "layer": 0, "platform": 0, "x1": 0, "y1": 0,
           "x2": 500, "y2": 0, "prev": -1, "next": -1}
    ph = Physics([seg], [], bounds={"left": -1000, "right": 2000,
                                    "top": -500, "width": 3000,
                                    "height": 2000})
    mob = Monster(_A(), {"id": "0100101", "x": 100, "y": 0, "cy": 0,
                         "rx0": 0, "rx1": 500}, 0, ph)
    hits: list = []
    for _ in range(30):
        mob.update(0.05, player_x=mob.x + 10, player_y=0, mobs=hits)
        if hits:
            break
    assert hits, "贴身更新应产生一次接触伤害"
    return hits[-1]


def test_magic_mob_contact_uses_mad_and_flags_magic():
    """MAD > PAD 的怪：接触伤害以魔攻计（±10%）并带 magic 标记。"""
    hit = _mob_hit({"hp": 50, "exp": 0, "weaponAttack": 10,
                    "magicAttack": 40, "accuracy": 30})
    assert hit["magic"] is True
    assert 36 <= hit["amount"] <= 44                # 40 ±10%
    assert hit["acc"] == 30


def test_physical_mob_contact_not_magic():
    """物攻不低于魔攻的怪：普通物理接触、无 magic 标记。"""
    hit = _mob_hit({"hp": 50, "exp": 0, "weaponAttack": 10, "accuracy": 30})
    assert hit["magic"] is False
    assert 9 <= hit["amount"] <= 11


# ── 近战命中特效朝向：素材朝左，按攻击者朝向镜像 ────────────────────
def _skill_hit_assets() -> "_Assets":
    class _HitAssets(_Assets):
        def skill_hit_frames(self, sid):
            return [(pygame.Surface((4, 4)), (2, 4), 100)]

    return _HitAssets()


def _melee_player(facing_right: bool) -> "_Player":
    p = _Player()
    p.pending_skill = {"id": "3111004", "damage": 1.0, "mob_count": 1}
    p.facing_right = facing_right
    return p


def test_melee_hit_effect_flips_when_facing_right():
    """面向右近战命中：命中特效镜像，冲击朝右。"""
    c = Combat(_skill_hit_assets(), rng=random.Random(1))
    c.player_attack(_melee_player(True), [_Mob()])
    assert c.effects[-1].flip is True


def test_melee_hit_effect_unflipped_when_facing_left():
    """面向左近战命中：命中特效保持素材原样（朝左）。"""
    c = Combat(_skill_hit_assets(), rng=random.Random(1))
    c.player_attack(_melee_player(False), [_Mob()])
    assert c.effects[-1].flip is False
