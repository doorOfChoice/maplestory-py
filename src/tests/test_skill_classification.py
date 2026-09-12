"""纯 buff 技能判定：skill_buff_seconds 区分「持续时间增益」与「带计时的攻击技」。

seam：game.systems.skills.skill_buff_seconds（纯函数，合成 SkillDef）。
"""
from __future__ import annotations

from game.systems.skills import SkillDef, skill_buff_seconds


def make(lv1: dict) -> SkillDef:
    return SkillDef("9999999", "测试", "", [dict(lv1)], 1)


def test_pure_buff_returns_duration():
    """有 time、无任何攻击属性 → 返回持续秒数。"""
    assert skill_buff_seconds(make({"time": 70, "acc": 5}), 1) == 70.0


def test_attack_with_damage_is_not_buff():
    assert skill_buff_seconds(make({"time": 10, "damage": 127}), 1) == 0.0


def test_multi_hit_attack_with_attack_count_is_not_buff():
    """带 time 但 attackCount>0 的多段攻击技不得被当 buff 吞掉。"""
    assert skill_buff_seconds(make({"time": 5, "attackCount": 2}), 1) == 0.0


def test_skill_without_time_is_not_buff():
    assert skill_buff_seconds(make({"damage": 190}), 1) == 0.0


def test_attack_with_wz_hit_node_is_not_buff():
    """冰冻术：带 time（冻结时长）但有 WZ hit 节点 = 攻击技，不得当 buff。"""
    d = SkillDef("2201004", "冰冻术", "", [{"time": 1, "mad": 13}], 1,
                 has_hit=True)
    assert skill_buff_seconds(d, 1) == 0.0
