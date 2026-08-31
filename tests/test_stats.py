"""数值系统纯函数：加点 / HP·MP 公式 / 攻防伤害 / 穿戴门控。"""
from __future__ import annotations

import random

from game import settings
from game.stats import (
    allocate, attack, auto_allocate, base_stats, defense, max_hp, max_mp,
    roll_damage, wear_block,
)


def test_allocate_adds_stat_and_consumes_ap():
    """加点：属性增加、AP 等量扣减。"""
    stats, ap = allocate(base_stats(), 5, "dex", 3)
    assert stats["dex"] == 4 + 3
    assert ap == 2


def test_allocate_insufficient_ap_noop():
    """AP 不足时加点不生效。"""
    stats, ap = allocate(base_stats(), 1, "dex", 3)
    assert stats["dex"] == 4
    assert ap == 1


def test_allocate_unknown_stat_noop():
    """未知属性名不生效。"""
    stats, ap = allocate(base_stats(), 5, "vit", 1)
    assert stats == base_stats()
    assert ap == 5


def test_auto_allocate_all_to_job_stat():
    """一键自动分配：弓箭手全进 DEX。"""
    stats, ap = auto_allocate(base_stats(), 20, {"dex": 5})
    assert stats["dex"] == 24
    assert stats["str"] == 4
    assert ap == 0


def test_auto_allocate_cycles_multi_weights():
    """多维权重按轮转分配，全部 AP 用完。"""
    stats, ap = auto_allocate(base_stats(), 3, {"str": 1, "dex": 1})
    assert stats["str"] + stats["dex"] == 8 + 3
    assert ap == 0


def test_max_hp_mp_formula():
    """HP/MP = 基础 + 等级×职业成长 + 装备词条。"""
    assert max_hp(1, 15, 0) == settings.HP_BASE + 15
    assert max_hp(10, 20, 30) == settings.HP_BASE + 200 + 30
    assert max_mp(1, 10, 0) == settings.MP_BASE + 10


def test_attack_uses_dex_for_ranged_and_str_for_melee():
    """远程主属性 DEX、近战主属性 STR；副属性取另一维。"""
    stats = {"str": 4, "dex": 104, "int": 4, "luk": 4}
    ranged = attack(stats, 25, ranged=True)
    melee = attack(stats, 25, ranged=False)
    assert ranged > melee


def test_attack_monotonic_in_main_stat():
    """主属性越高攻击力严格不减。"""
    low = attack({"str": 4, "dex": 4, "int": 4, "luk": 4}, 40, ranged=False)
    high = attack({"str": 104, "dex": 4, "int": 4, "luk": 4}, 40, ranged=False)
    assert high > low


def test_roll_damage_bounds():
    """伤害 = atk×倍率×rand(0.95~1.05) − 怪物PDD×(1−LUK/100)，下限 1。"""
    rng = random.Random(7)
    for _ in range(50):
        d = roll_damage(100, 1.9, 30, 4, rng)
        assert 100 * 1.9 * 0.95 - 30 <= d <= 100 * 1.9 * 1.05
    assert roll_damage(1, 0.1, 9999, 0, rng) == 1


def test_roll_damage_luk_reduces_mitigation():
    """LUK 越高，怪物 PDD 减免越多（同随机种子对比）。"""
    d_low = roll_damage(100, 1.0, 50, 0, random.Random(5))
    d_high = roll_damage(100, 1.0, 50, 100, random.Random(5))
    assert d_high > d_low


def test_defense_includes_dex_and_equipment():
    """防御 = 装备 PDD + DEX//10。"""
    assert defense({"str": 4, "dex": 50, "int": 4, "luk": 4}, 20) == 25


def test_wear_block_level_and_stats():
    """穿戴门控：等级与四维需求逐项检查，满足则放行。"""
    info = {"reqLevel": 10, "reqSTR": 0, "reqDEX": 25, "reqINT": 0, "reqLUK": 0}
    assert wear_block(info, 9, base_stats()) is not None
    assert "10" in wear_block(info, 9, base_stats())
    assert wear_block(info, 10, base_stats()) is not None
    assert "敏捷" in wear_block(info, 10, {"str": 4, "dex": 24, "int": 4, "luk": 4})
    assert wear_block(info, 10, {"str": 4, "dex": 25, "int": 4, "luk": 4}) is None


def test_wear_block_no_requirements():
    """无需求装备永远可穿。"""
    assert wear_block({}, 1, base_stats()) is None
