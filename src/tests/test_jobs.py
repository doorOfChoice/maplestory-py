"""职业注册表纯函数：技能图定位、远程武器判定、转职门控。"""
from __future__ import annotations

from types import SimpleNamespace

from game.core.jobs import (JOBS, can_advance, is_ranged_weapon, job_chain,
                            job_for_trainer, job_sp_group, resolve_skill_img,
                            sp_group_of_skill)


def test_resolve_skill_img_by_length():
    """7 位技能 id 取前 3 位为图名，8 位取前 4 位。"""
    assert resolve_skill_img("3001004") == "300.img"
    assert resolve_skill_img("10001004") == "1000.img"


def test_is_ranged_weapon():
    """弓(145)/弩(146)为远程武器，单手剑(130)不是。"""
    assert is_ranged_weapon("1452000") is True
    assert is_ranged_weapon("1462000") is True
    assert is_ranged_weapon("1302000") is False


def test_can_advance_requires_level():
    """新手 Lv9 不能转职，Lv10 可以。"""
    bowman = JOBS[3000]
    assert can_advance(SimpleNamespace(job=0, level=9), bowman) is False
    assert can_advance(SimpleNamespace(job=0, level=10), bowman) is True


def test_can_advance_wrong_prejob():
    """已是弓箭手（job=3000）不能再转。"""
    assert can_advance(SimpleNamespace(job=3000, level=30), JOBS[3000]) is False


def test_hunter_is_bowman_second_job():
    """猎人 3100：前置弓箭手 3000、需 Lv30、技能树 310.img。"""
    hunter = JOBS[3100]
    assert hunter.prejob == 3000
    assert hunter.advance_lv == 30
    assert hunter.tree_imgs == ["310.img"]
    assert can_advance(SimpleNamespace(job=3000, level=29), hunter) is False
    assert can_advance(SimpleNamespace(job=3000, level=30), hunter) is True
    assert can_advance(SimpleNamespace(job=0, level=30), hunter) is False


def test_bowmaster_is_hunter_third_job():
    """神射手 3110：前置猎人 3100、需 Lv70、技能树 311.img。"""
    bowmaster = JOBS[3110]
    assert bowmaster.prejob == 3100
    assert bowmaster.advance_lv == 70
    assert bowmaster.tree_imgs == ["311.img"]
    assert can_advance(SimpleNamespace(job=3100, level=69), bowmaster) is False
    assert can_advance(SimpleNamespace(job=3100, level=70), bowmaster) is True
    assert can_advance(SimpleNamespace(job=3000, level=70), bowmaster) is False


def test_job_for_trainer_resolves_chain_by_current_job():
    """同一导师赫丽娜：按玩家当前职业回传下一步转职目标职业。"""
    assert job_for_trainer(1012100, player_job=0) is JOBS[3000]
    assert job_for_trainer(1012100, player_job=3000) is JOBS[3100]
    assert job_for_trainer(1012100, player_job=3100) is JOBS[3110]


def test_job_for_trainer_terminal_and_unknown():
    """已是最高阶（神射手）或无关职业/导师 → None。"""
    assert job_for_trainer(1012100, player_job=3110) is None
    assert job_for_trainer(1012100, player_job=1000) is None
    assert job_for_trainer(9999999, player_job=0) is None


def test_job_chain_orders_from_first_to_current():
    """职业链：旧→新，猎人 → [新手, 弓箭手, 猎人]，神射手含全部四阶。"""
    assert [j.code for j in job_chain(3100)] == [0, 3000, 3100]
    assert [j.code for j in job_chain(3110)] == [0, 3000, 3100, 3110]
    assert [j.code for j in job_chain(3000)] == [0, 3000]


def test_job_chain_newbie_has_snail_tree():
    """新手有树（1000.img 蜗牛投掷）→ 链含新手。"""
    assert [j.code for j in job_chain(0)] == [0]


def test_sp_group_of_skill_and_job():
    """技能所属组取图名前 3 位；职业组取代码除 10（一转/二转/三转各自成池）。"""
    assert sp_group_of_skill("3001004") == 300
    assert sp_group_of_skill("3101005") == 310
    assert sp_group_of_skill("3110000") == 311
    assert job_sp_group(3000) == 300
    assert job_sp_group(3110) == 311
    assert job_sp_group(0) == 100          # 新手组对齐 1000.img 前缀
    assert sp_group_of_skill("10001000") == 100
