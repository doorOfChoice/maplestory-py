"""职业注册表纯函数：技能图定位、远程武器判定、转职门控。"""
from __future__ import annotations

from types import SimpleNamespace

from game.jobs import JOBS, can_advance, is_ranged_weapon, resolve_skill_img


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
