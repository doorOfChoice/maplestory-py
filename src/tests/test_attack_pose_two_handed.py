"""攻击姿态选择：双手武器应命中 swingT*/stabT*，而非回退到不存在的单手姿态。"""

from __future__ import annotations

from game.render.assets import select_attack_pose


def test_two_handed_sword_uses_two_handed_swing():
    poses = ["stand1", "swingT1", "swingT2", "swingT3", "stabO1", "stabO2"]
    assert select_attack_pose("01402000", poses) == "swingT1"


def test_spear_without_swing_t1_picks_stab_t1():
    poses = ["stand1", "swingT2", "stabT1", "stabT2"]
    assert select_attack_pose("01432000", poses) == "stabT1"


def test_one_handed_sword_keeps_one_handed_swing():
    poses = ["stand1", "swingO1", "swingO2", "swingO3", "stabO1", "stabO2"]
    assert select_attack_pose("01302000", poses) == "swingO1"


def test_one_handed_weapon_with_both_pose_groups_prefers_one_handed():
    poses = ["stand1", "swingT1", "swingO1", "stabO1"]
    assert select_attack_pose("01302000", poses) == "swingO1"


def test_bow_prefers_shoot1():
    poses = ["stand1", "swingT1", "swingT3", "shoot1", "shootF"]
    assert select_attack_pose("01452002", poses) == "shoot1"


def test_crossbow_prefers_shoot2():
    poses = ["stand1", "swingT1", "stabT1", "shoot2"]
    assert select_attack_pose("01462000", poses) == "shoot2"


def test_weapon_without_any_pose_falls_back():
    assert select_attack_pose("01302000", []) == "swingO1"
