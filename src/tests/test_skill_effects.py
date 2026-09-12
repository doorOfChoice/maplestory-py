"""技能字段语义映射：WZ level 表字段 → buff/被动 mod 词条（纯函数，合成数值）。

seam：game.core.skill_effects.buff_mods / passive_mods；
所有技能 mod 为平坦加值，speed/jump 为百分比点，crit/crit_mult/stat_pct 为百分比。
"""
from __future__ import annotations

from game.core.skill_effects import buff_mods, passive_mods


def stat_of(table: dict):
    return lambda key: int(table.get(key, 0))


def test_buff_generic_fields_map_to_flat_mods():
    """主动 buff 的通用字段（pad/mad/pdd/mdd/acc/eva/speed/jump/hp/mp/四维）逐项转平坦 mod。"""
    mods = buff_mods("9999999", stat_of({
        "pad": 5, "mad": 3, "pdd": 30, "mdd": 15, "acc": 4, "eva": 2,
        "speed": 8, "jump": 1, "hp": 50, "mp": 20, "dex": 6}))
    assert mods == {"atk": 5, "matk": 3, "def": 30, "mdef": 15,
                    "acc_flat": 4, "eva_flat": 2, "speed": 8, "jump": 1,
                    "hp": 50, "mp": 20, "dex": 6}


def test_buff_zero_fields_omitted():
    """数值为 0 的字段不入 mods，避免堆积死词条。"""
    assert buff_mods("9999999", stat_of({"pad": 0, "mad": 5})) == {"matk": 5}


def test_buff_summon_and_unimplemented_skills_give_no_player_mods():
    """召唤类（pad=召唤物攻击）/未实装技能：不得把字段当玩家增益。"""
    assert buff_mods("3121006", stat_of({"pad": 550, "x": 200})) == {}
    assert buff_mods("3111005", stat_of({"pad": 300})) == {}
    assert buff_mods("3101002", stat_of({"x": -2})) == {}


def test_buff_maple_blessing_maps_x_to_all_stat_pct():
    """楓葉祝福(3121000)：x=15（全属性 %）→ stat_pct。"""
    assert buff_mods("3121000", stat_of({"x": 15})) == {"stat_pct": 15}


def test_buff_sharp_eyes_maps_xy_to_crit():
    """會心之眼(3121002)：x=15 暴击率、y=140 暴伤。"""
    assert buff_mods("3121002", stat_of({"x": 15, "y": 140})) == \
        {"crit": 15, "crit_mult": 140}


def test_buff_magic_guard_maps_x_to_redirect():
    """魔法盾(2001002)：x=80（伤害转 MP 比例）→ magic_guard。"""
    assert buff_mods("2001002", stat_of({"x": 80, "time": 600})) == \
        {"magic_guard": 80}


def test_buff_magic_armor_uses_generic_pdd():
    """魔法铠甲(2001003)：通用字段 pdd → def。"""
    assert buff_mods("2001003", stat_of({"pdd": 40, "time": 400})) == {"def": 40}


def test_passive_curated_field_semantics():
    """逐技能被动：霸王箭 prop/damage、疾風步 speed、精準之弓 mastery/x、百步穿楊 range。"""
    assert passive_mods("3000001", stat_of({"prop": 40, "damage": 200})) == \
        {"crit": 40, "crit_mult": 200}
    assert passive_mods("3110000", stat_of({"speed": 30})) == {"speed": 30}
    assert passive_mods("3100000", stat_of({"mastery": 10, "x": 20})) == \
        {"mastery": 10, "acc": 20}
    assert passive_mods("3120005", stat_of({"mastery": 16, "x": 10})) == \
        {"mastery": 16, "acc": 10}
    assert passive_mods("3000002", stat_of({"range": 120})) == {"range": 120}


def test_passive_final_attack_has_no_effect():
    """終極之弓(3100001) 是触发式追击，未实现 → 不产出 crit/crit_mult 等错误词条。"""
    assert passive_mods("3100001", stat_of({"prop": 60, "damage": 250})) == {}


def test_passive_magic_mp_boost_maps_x_to_mp():
    """魔力强化(2000001)：x=20（MaxMP 提升）→ mp。"""
    assert passive_mods("2000001", stat_of({"x": 20, "y": 10})) == {"mp": 20}


def test_passive_mp_recovery_maps_mp_regen():
    """魔力恢复(2000000)：合成 mp_regen（0.1/s 点数，满级 32 → +3.2/s）。"""
    assert passive_mods("2000000", stat_of({"mp_regen": 32})) == {"mp_regen": 32}


def test_passive_unregistered_falls_back_to_generic_flat_fields():
    """未登记被动回退通用字段（pad→atk、pdd→def）。"""
    assert passive_mods("1111000", stat_of({"pad": 5, "pdd": 10})) == \
        {"atk": 5, "def": 10}
