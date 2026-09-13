"""技能分面模型：交付方式 + 效果子句的结构默认与声明式例外（纯合成 SkillDef）。

seam：game.core.skill_semantics（delivery/targeting/cost/effects/is_passive）
与 SkillDef.spec（core.skill_spec.SkillSpec）。
"""
from __future__ import annotations

from game.core import skill_semantics as sem
from game.core.skill_spec import (Buff, Cleanse, Damage, Debuff, Field, Proc,
                                  Summon, TARGET_AREA, TARGET_PARTY,
                                  TARGET_SINGLE)
from game.systems.skills import SkillDef


def make(sid: str, name: str = "技能", **lv1) -> SkillDef:
    d = SkillDef(sid, name, "", [dict(lv1)], 1)
    return d


def flagged(sid: str, name: str, table: dict, **flags) -> SkillDef:
    return SkillDef(sid, name, "", [dict(table)], 1, **flags)


# ── 交付方式（结构默认 + 例外）────────────────────────────────────────
def test_summon_node_beats_hit_node():
    """summon 节点优先于 hit：银鹰召唤不得被当玩家瞬发攻击。"""
    d = flagged("3111005", "银鹰召唤", {"mpCon": 32, "time": 103, "pad": 23},
                has_summon=True, has_hit=True, has_mob_icon=True)
    assert sem.delivery(d, 1) == "summon"


def test_mob_node_with_time_is_mob_status_not_buff():
    """mob 节点 + time（击退箭）是对怪状态，不是自身 buff。"""
    d = flagged("3121007", "击退箭",
                {"mpCon": 12, "time": 35, "x": -2, "prop": 11, "y": 5},
                has_mob_icon=True)
    assert sem.delivery(d, 1) == "mob_status"
    debuff = next(e for e in sem.effects(d, 1) if isinstance(e, Debuff))
    assert debuff.status == "slow" and debuff.potency == -2


def test_multishot_without_ball_is_projectile():
    """二连射：无 ball 但 bulletCount>1，结构上仍是弹道，不退化近战。"""
    d = flagged("3001005", "二连射",
                {"mpCon": 10, "damage": 92, "bulletCount": 2}, has_hit=True)
    assert sem.delivery(d, 1) == "projectile"
    dmg = next(e for e in sem.effects(d, 1) if isinstance(e, Damage))
    assert dmg.shots == 2


def test_affected_without_hit_is_aura():
    """affected 无命中 → 团队增益（aura），非普通 buff。"""
    d = flagged("2321005", "祝福",
                {"mpCon": 20, "time": 60, "pad": 10},
                has_affected=True)
    assert sem.delivery(d, 1) == "aura"
    assert sem.targeting(d, 1) == TARGET_PARTY
    buff = next(e for e in sem.effects(d, 1) if isinstance(e, Buff))
    assert buff.party is True


def test_skill_type_three_is_final_attack_passive():
    """skillType=3 → 终极追击被动，产出 final_attack Proc（非攻击）。"""
    d = flagged("3100001", "终极弓", {"prop": 60, "damage": 250},
                skill_type=3, has_hit=True)
    assert sem.delivery(d, 1) == "passive"
    procs = [e for e in sem.effects(d, 1) if isinstance(e, Proc)]
    assert procs and procs[0].kind == "final_attack"
    assert procs[0].chance == 60 and procs[0].mult == 2.5


def test_no_mp_no_marker_is_structural_passive():
    """无 mpCon、无交付节点、无持续/伤害 → 结构默认被动。"""
    d = make("9990001", "假动作", prop=30)
    assert sem.is_passive(d) is True
    assert sem.delivery(d, 1) == "passive"


def test_mp_only_with_range_is_move():
    """仅耗 MP 且有 range → 位移技（快速移动变体）。"""
    d = make("12101003", "快速移动", mpCon=13, range=130)
    assert sem.delivery(d, 1) == "move"


# ── 效果子句 ─────────────────────────────────────────────────────────
def test_damage_clause_collects_wz_fields():
    """伤害子句聚合 damage/mobCount/attackCount/bulletCount/lt-rb/element。"""
    d = flagged("2201005", "雷电术",
                {"mpCon": 21, "mad": 55, "mobCount": 6, "attackCount": 2,
                 "lt": (-150, -50), "rb": (150, 50)},
                has_hit=True, element="l")
    dmg = next(e for e in sem.effects(d, 1) if isinstance(e, Damage))
    assert dmg.magic is True and dmg.skill_mad == 55
    assert dmg.max_targets == 6 and dmg.hits == 2
    assert dmg.area == ((-150, -50), (150, 50))
    assert sem.targeting(d, 1) == TARGET_AREA


def test_attack_status_becomes_damage_status():
    """冰冻术：命中附带状态进 Damage.status（冻结时长取 time）。"""
    d = flagged("2201004", "冰冻术", {"mpCon": 12, "mad": 13, "time": 1},
                has_hit=True)
    dmg = next(e for e in sem.effects(d, 1) if isinstance(e, Damage))
    assert dmg.status is not None and dmg.status.status == "freeze"
    assert dmg.status.duration == 1.0


def test_tile_clause_coexists_with_damage():
    """地面技：Field 子句与 Damage 子句正交共存（如火牢/毒雾）。"""
    d = flagged("12111005", "火牢术屏障",
                {"mpCon": 34, "damage": 60, "time": 6, "lt": (-100, -80),
                 "rb": (100, 80), "mobCount": 6},
                has_hit=True, has_tile=True)
    kinds = {type(e).__name__ for e in sem.effects(d, 1)}
    assert "Field" in kinds and "Damage" in kinds


def test_summon_clause_exposes_attack_and_duration():
    """召唤子句：攻击力取 pad、持续取 time。"""
    d = flagged("3121006", "火凤凰",
                {"mpCon": 42, "time": 113, "pad": 305, "x": 1},
                has_summon=True, has_hit=True)
    summon = next(e for e in sem.effects(d, 1) if isinstance(e, Summon))
    assert summon.attack == 305 and summon.duration == 113.0


def test_cleanse_clause_for_hero_will():
    """勇士的意志：产出 Cleanse 子句（解除诱惑）。"""
    d = make("3121009", "勇士的意志", mpCon=30, cooltime=600, time=1)
    cleanses = [e for e in sem.effects(d, 1) if isinstance(e, Cleanse)]
    assert cleanses and "seduce" in cleanses[0].kinds


def test_cost_reads_wz_level_fields():
    """代价：mpCon/hpCon/itemConNo/cooltime 全部来自 level 表。"""
    d = flagged("3111005", "银鹰召唤",
                {"mpCon": 32, "hpCon": 5, "time": 103, "pad": 23,
                 "itemCon": 4006001, "itemConNo": 1, "cooltime": 2},
                has_summon=True)
    c = sem.cost(d, 1)
    assert c.mp == 32 and c.hp == 5 and c.cooldown == 2.0
    assert c.item_id == "4006001" and c.item_count == 1


def test_attack_control_status_mapped_for_hit_mob_skill():
    """强弓（hit+mob+prop+time）：命中附带 stun，概率/时长取 WZ 字段。"""
    d = flagged("3101003", "强弓",
                {"mpCon": 8, "damage": 105, "mobCount": 2, "prop": 13,
                 "time": 3, "range": 130},
                has_hit=True, has_mob_icon=True)
    dmg = next(e for e in sem.effects(d, 1) if isinstance(e, Damage))
    assert dmg.status is not None and dmg.status.status == "stun"
    assert dmg.status.chance == 13 and dmg.status.duration == 3.0


def test_attack_control_status_gets_default_duration_without_time():
    """控制状态无 WZ time 时给默认时长，避免 duration=0 导致不生效。"""
    from game import settings
    d = flagged("3101003", "强弓", {"mpCon": 8, "damage": 105, "prop": 13},
                has_hit=True, has_mob_icon=True)
    dmg = next(e for e in sem.effects(d, 1) if isinstance(e, Damage))
    assert dmg.status.status == "stun"
    assert dmg.status.duration == settings.ATTACK_STATUS_DEFAULT_DURATION


def test_spec_targets_single_for_plain_attack():
    d = flagged("3001004", "断魂箭", {"mpCon": 7, "damage": 190},
                has_ball=True, has_hit=True)
    assert d.spec.kind == "projectile"
    assert d.spec.targeting == TARGET_SINGLE
