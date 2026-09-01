"""数值系统纯函数：加点 / HP·MP 公式 / 攻击区间 / 伤害结算 / 经验查表 / 穿戴门控。"""
from __future__ import annotations

import random

from game import settings
from game.stats import (
    allocate, attack, attack_range, auto_allocate, base_stats, defense,
    exp_to_next, max_hp, max_mp, roll_damage, wear_block,
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
    """远程主属性 DEX、近战主属性 STR；远程更吃 DEX。"""
    stats = {"str": 4, "dex": 104, "int": 4, "luk": 4}
    ranged = attack(stats, 25, ranged=True)
    melee = attack(stats, 25, ranged=False)
    assert ranged > melee


def test_attack_monotonic_in_main_stat():
    """主属性越高攻击力严格不减。"""
    low = attack({"str": 4, "dex": 4, "int": 4, "luk": 4}, 40, ranged=False)
    high = attack({"str": 104, "dex": 4, "int": 4, "luk": 4}, 40, ranged=False)
    assert high > low


def test_attack_range_min_le_max():
    """攻击区间 Min ≤ Max，且都随主属性增长。"""
    stats = {"str": 4, "dex": 60, "int": 4, "luk": 4}
    lo, hi = attack_range(stats, 25, ranged=True)
    assert 1 <= lo <= hi
    lo2, hi2 = attack_range({"str": 4, "dex": 120, "int": 4, "luk": 4},
                            25, ranged=True)
    assert lo2 >= lo and hi2 >= hi


def test_roll_damage_level_defense_reduction():
    """怪物高于玩家等级：伤害按等级差减免（D 越大越低）。"""
    lo, hi = attack_range({"str": 4, "dex": 104, "int": 4, "luk": 4}, 60,
                          ranged=True)
    d_same, _ = roll_damage(lo, hi, 1.0, 0, 10, 10, random.Random(9))
    d_above, _ = roll_damage(lo, hi, 1.0, 0, 10, 30, random.Random(9))
    assert d_above < d_same


def test_roll_damage_pdd_reduces():
    """怪物 PDD 越高伤害越低（同等级差、同 rng）。"""
    lo, hi = attack_range({"str": 4, "dex": 104, "int": 4, "luk": 4}, 60,
                          ranged=True)
    d_low, _ = roll_damage(lo, hi, 1.0, 0, 10, 10, random.Random(5))
    d_high, _ = roll_damage(lo, hi, 1.0, 100, 10, 10, random.Random(5))
    assert d_high < d_low


def test_roll_damage_never_below_one():
    """任何输入伤害下限 1。"""
    lo, hi = 1, 1
    assert roll_damage(lo, hi, 0.1, 9999, 10, 10, random.Random(0))[0] == 1


def test_defense_includes_dex_and_equipment():
    """防御 = 装备 PDD + DEX//10。"""
    assert defense({"str": 4, "dex": 50, "int": 4, "luk": 4}, 20) == 25


def test_exp_to_next_official_table():
    """经验查表：官方 v113 逐级值（非指数近似）。"""
    assert exp_to_next(1) == 15
    assert exp_to_next(2) == 34
    assert exp_to_next(9) == 1242
    assert exp_to_next(10) == 1242
    assert exp_to_next(20) == 3705
    assert exp_to_next(30) == 19112
    assert exp_to_next(45) == 75458


def test_exp_to_next_grows_monotonically():
    """经验需求单调不减（含表尾近似区间）。"""
    cur = 0
    for lv in range(1, 70):
        nxt = exp_to_next(lv)
        assert nxt >= cur
        cur = nxt


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
