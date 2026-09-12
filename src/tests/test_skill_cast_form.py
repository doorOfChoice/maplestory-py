"""施法形态分类：由 WZ 顶层节点结构推导「怎么放」，而非硬编码技能 id。

seam：纯函数 skills.cast_form（输入合成 SkillDef，输出形态字符串）；不依赖 WZ。
"""
from __future__ import annotations

from game.systems.skills import SkillDef, cast_form


def make(sid: str, name: str = "技能", **lv1) -> SkillDef:
    return SkillDef(sid, name, "", [dict(lv1)], 1)


def test_ball_node_is_projectile():
    """有 ball 节点（魔法弹/火焰箭）→ 弹道技。"""
    d = SkillDef("2001004", "魔法弹", "", [{"mpCon": 6, "mad": 20}], 1,
                 has_ball=True, has_hit=True)
    assert cast_form(d, 1) == "projectile"


def test_time_without_hit_is_buff_even_if_ball_present():
    """有 time 且无 hit（无形箭：带 ball 但也带 time）→ 纯 buff，不是弹道。"""
    d = SkillDef("3101004", "无形箭", "", [{"time": 60, "x": 1}], 1,
                 has_ball=True)
    assert cast_form(d, 1) == "buff"


def test_hit_without_area_is_instant():
    """有 hit 无 lt/rb（魔法双击/冰冻术）→ 瞬发命中。"""
    d = SkillDef("2001005", "魔法双击", "", [{"mad": 11, "attackCount": 2}], 1,
                 has_hit=True)
    assert cast_form(d, 1) == "instant"


def test_hit_with_area_is_aoe():
    """有 hit 且有 lt/rb（雷电术/箭雨）→ 自身范围 AOE。"""
    d = SkillDef("2201005", "雷电术", "", [{"mad": 2, "mobCount": 6}], 1,
                 has_hit=True)
    d.levels[0]["lt"] = (-150, -50)
    d.levels[0]["rb"] = (150, 50)
    assert cast_form(d, 1) == "aoe"


def test_mob_icon_without_damage_is_mob_status():
    """有 mob 状态图标且无伤害（缓速术）→ 怪物 debuff。"""
    d = SkillDef("2201003", "缓速术", "", [{"x": -2, "time": 2, "mobCount": 6}], 1,
                 has_mob_icon=True)
    assert cast_form(d, 1) == "mob_status"


def test_mob_icon_with_hit_stays_attack():
    """同时有 mob 与 hit（银鹰召唤）→ 仍按攻击处理，不误判为 debuff。"""
    d = SkillDef("3111005", "银鹰召唤", "", [{"time": 10, "pad": 100}], 1,
                 has_mob_icon=True, has_hit=True)
    assert cast_form(d, 1) == "instant"


def test_only_range_is_teleport():
    """只有 range/mpCon（快速移动）→ 已登记瞬移技，按方向键位移。"""
    d = make("2201002", mpCon=13, range=130)
    assert cast_form(d, 1) == "teleport"


def test_registered_passive_is_passive():
    """已登记被动（魔力吸收 2200000）→ passive，不可落键施放。"""
    d = make("2200000", prop=11, x=21)
    assert cast_form(d, 1) == "passive"
