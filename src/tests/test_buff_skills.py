"""Buff 技能施放接线：cast 出含 time 字段的技能 → player.buffs 生效、属性变化。"""
from __future__ import annotations

from game.systems.inventory import Inventory
from game.entities.player import Player
from game.systems.skills import SkillBook, SkillDef
from game.core.stats import base_stats


class StubAssets:
    """最小资产桩：只补 Player 构造用到的 WZ 无关接口。"""

    def __init__(self):
        self.equips = None
        self.job = 0

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def _buff_init(self, assets, quest_defs=None):
    """最小新档初始化：真实 Inventory/SkillBook（attack_value 需要）。"""
    self.inventory = Inventory()
    self.skills = SkillBook(None, 0)
    self.quests = {}
    self.stats = base_stats()
    self.level = 1
    self.pending_skill = None
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


def make_player(monkeypatch) -> Player:
    """构造 buff 接线专用的 Player：桩掉动画与新档初始化。"""
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _buff_init)
    return Player(StubAssets(), 0.0, 0.0)


def make_buff_skill(sid: str = "3001003", **lv1) -> SkillDef:
    levels = [dict(lv1) or {"time": 70}]
    return SkillDef(sid, "疾風步", "", levels, 1)


def make_cast(sid: str = "3001003", d: SkillDef | None = None) -> dict:
    skill = d or make_buff_skill()
    return {"id": sid, "def": skill, "level": 1, "mp_con": 8, "hp_con": 0,
            "damage": 1.0, "range": 0, "mob_count": 1, "bullet_count": 1}


def test_cast_buff_skill_applies_mods_and_raises_attack(monkeypatch):
    """施放带 time/attack/dex/criticalrate 的技能 → buffs 生效且 attack_value 提升。"""
    player = make_player(monkeypatch)
    before = player.attack_value()
    data = make_cast(d=make_buff_skill(time=70, attack=5, dex=10, criticalrate=15))
    assert player.start_attack(data) is True
    assert player.buffs.mod_sum("atk") == 5
    assert player.buffs.mod_sum("dex") == 10
    assert player.buffs.mod_sum("crit") == 15
    # atk +5 直接进面板；dex +10 作为副属性按主属性权重计入
    assert player.attack_value() == before + 7


def test_cast_buff_skill_consumes_mp_without_entering_attack(monkeypatch):
    """Buff 施放只扣 MP、不进入攻击状态（不挥击不产生 pending_skill）。"""
    player = make_player(monkeypatch)
    mp_before = player.mp
    assert player.start_attack(make_cast()) is True
    assert player.mp == mp_before - 8
    assert not player.attacking
    assert player.pending_skill is None


def test_cast_damage_skill_does_not_apply_buff(monkeypatch):
    """无 time 字段的技能照常攻击，不产生 buff。"""
    player = make_player(monkeypatch)
    d = SkillDef("3001004", "斷魂箭", "", [{"damage": 190}], 1)
    data = {"id": "3001004", "def": d, "level": 1, "mp_con": 7, "hp_con": 0,
            "damage": 1.9, "range": 0, "mob_count": 1, "bullet_count": 1}
    assert player.start_attack(data) is True
    assert player.buffs.active() == []
    assert player.attacking


def test_cast_buff_skill_zero_time_is_normal_attack(monkeypatch):
    """time=0（如技能表无 time 字段）按普通技能处理，不产生 buff。"""
    player = make_player(monkeypatch)
    data = make_cast(d=make_buff_skill(time=0, attack=5))
    assert player.start_attack(data) is True
    assert player.buffs.active() == []
    assert player.attacking


def test_attack_skill_with_time_field_still_attacks(monkeypatch):
    """带持续计时但含攻击属性的技能（烈火箭 damage+time）必须进攻击流程。"""
    player = make_player(monkeypatch)
    d = SkillDef("3111003", "烈火箭", "", [{"damage": 127, "time": 10}], 1)
    data = {"id": "3111003", "def": d, "level": 1, "mp_con": 25, "hp_con": 0,
            "damage": 1.27, "range": 0, "mob_count": 5, "bullet_count": 1}
    assert player.start_attack(data) is True
    assert player.attacking
    assert player.pending_skill is data
    assert player.buffs.active() == []


def test_multi_target_skill_with_time_field_still_attacks(monkeypatch):
    """无 damage 字段但有 mobCount 的多体技能（炸弹箭）同样不得被 buff 吞掉。"""
    player = make_player(monkeypatch)
    d = SkillDef("3101005", "炸弹箭", "", [{"mobCount": 5, "time": 4}], 1)
    data = {"id": "3101005", "def": d, "level": 1, "mp_con": 28, "hp_con": 0,
            "damage": 1.0, "range": 0, "mob_count": 5, "bullet_count": 1}
    assert player.start_attack(data) is True
    assert player.attacking
    assert player.buffs.active() == []
