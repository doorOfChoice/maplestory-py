"""被动技能到面板/物理的接线：mastery、speed、range、hp（合成 SkillDef，不依赖 WZ）。

seam：Player.attack_mastery / move_speed / attack_range_bonus / attack_rect / recalc_vitals。
"""
from __future__ import annotations

import pytest

from game import settings
from game.core.jobs import JobDef
from game.core.stats import base_stats
from game.entities.player import Player
from game.systems.inventory import Inventory, Item
from game.systems.skills import SkillBook, SkillDef, apply_synthesized


class StubAssets:
    job = 0

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
    self.level = 1
    self.pending_skill = None
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


def make_player(monkeypatch, defs: dict, passive_ids: list) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    monkeypatch.setattr(Player, "_init_new_game", _init)
    player = Player(StubAssets(), 0.0, 0.0)
    player.skills = SkillBook(None, 3000, defs=defs)
    player.skills.on_advance(JobDef(code=3000, name="测试", passive_ids=passive_ids))
    return player


def passive(sid: str, name: str, lv1: dict) -> SkillDef:
    return SkillDef(sid, name, "", [dict(lv1)], 1)


def test_mastery_passive_raises_damage_floor(monkeypatch):
    """精準之弓 mastery=5 → 熟练度 0.95（默认 0.9 + 5 点）。"""
    player = make_player(monkeypatch, {
        "3100000": passive("3100000", "精準之弓", {"mastery": 5, "x": 0}),
    }, [3100000])
    assert player.attack_mastery() == pytest.approx(0.95)


def test_speed_passive_raises_move_speed(monkeypatch):
    """疾風步 speed=30 → 移速 ×1.30、面板 130%。"""
    player = make_player(monkeypatch, {
        "3110000": passive("3110000", "疾風步", {"speed": 30}),
    }, [3110000])
    assert player.move_speed() == settings.MOVE_SPEED * 1.30
    assert player.move_speed_display() == 130


def test_range_passive_extends_attack_rect(monkeypatch):
    """百步穿楊 range=120 → 命中框向前多出 120px。"""
    player = make_player(monkeypatch, {
        "3000002": passive("3000002", "百步穿楊", {"range": 120}),
    }, [3000002])
    assert player.attack_range_bonus() == 120
    assert player.start_attack() is True
    rect = player.attack_rect()
    expected = settings.ATTACK_RANGE + 120
    assert rect.width == int(expected)


def test_hp_passive_raises_max_hp(monkeypatch):
    """带 hp 平坦词的被动：重算上限后 max_hp 增加 50。"""
    plain = make_player(monkeypatch, {}, [])
    plain.recalc_vitals()
    boosted = make_player(monkeypatch, {
        "9999999": passive("9999999", "生命强化", {"hp": 50}),
    }, [9999999])
    boosted.recalc_vitals()
    assert boosted.max_hp == plain.max_hp + 50


def test_mp_passive_raises_max_mp(monkeypatch):
    """魔力强化 x=20 → mp 词条 +20，重算上限后 max_mp 增加 20。"""
    plain = make_player(monkeypatch, {}, [])
    plain.recalc_vitals()
    boosted = make_player(monkeypatch, {
        "2000001": passive("2000001", "魔力强化", {"x": 20}),
    }, [2000001])
    boosted.recalc_vitals()
    assert boosted.max_mp == plain.max_mp + 20


def test_mp_recovery_passive_learned_with_sp_raises_regen(monkeypatch):
    """魔力恢復需花 SP 学；合成每级 +2 点(0.1/s)，12 级 → 自然回蓝基础 +2.4/s。"""
    player = make_player(monkeypatch, {
        "2000000": passive("2000000", "魔力恢復", {"mp_regen": 2}),
    }, [])
    assert "2000000" in player.skills.learnable()
    player.skills.add_sp(200, 12)
    for _ in range(12):
        player.skills.learn("2000000", 1)
    assert player.mp_regen() == pytest.approx(settings.SKILL_MP_REGEN + 2.4)


def test_apply_synthesized_fills_magic_recovery_levels():
    """魔力恢復(2000000) 合成表：满级(16) mp_regen=32，覆盖 WZ 的空 hs 表。"""
    defs = {"2000000": SkillDef("2000000", "魔力恢復", "", [{"hs": "h1"}], 1)}
    apply_synthesized(defs, 2000)
    d = defs["2000000"]
    assert d.max_level == 16
    assert d.stat(16, "mp_regen") == 32


def test_crit_rate_capped_at_100(monkeypatch):
    """多被动叠加暴击率超过 100 时封顶 100。"""
    player = make_player(monkeypatch, {
        "3000001": passive("3000001", "霸王箭", {"prop": 40, "damage": 200}),
        "3110001": passive("3110001", "致命箭", {"prop": 90, "damage": 250}),
    }, [3000001, 3110001])
    assert player.crit_rate() == 100.0
