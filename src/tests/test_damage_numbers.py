"""官方伤害数字：数字集选择（小/大号、Miss）、颜色映射与原版动画曲线。"""
from __future__ import annotations

from game.combat import DamageNumber


def test_small_digits_below_thousand():
    """三位数伤害用官方小号数字集（NoRed0）。"""
    n = DamageNumber(0, 0, 350)
    assert n.set_name == "NoRed0"
    assert n.digits == ["3", "5", "0"]


def test_large_digits_at_thousand():
    """四位数及以上伤害换大号数字集（NoRed1）。"""
    n = DamageNumber(0, 0, 1000)
    assert n.set_name == "NoRed1"
    assert n.digits == ["1", "0", "0", "0"]


def test_kind_maps_to_official_sets():
    """技能紫→NoViolet、受击蓝→NoBlue，与原版配色一致。"""
    assert DamageNumber(0, 0, 10, kind="violet").set_name == "NoViolet0"
    assert DamageNumber(0, 0, 5000, kind="blue").set_name == "NoBlue1"


def test_zero_amount_shows_miss():
    """0 点伤害显示 Miss 贴图。"""
    n = DamageNumber(0, 0, 0)
    assert n.digits == ["Miss"]


def test_motion_holds_then_rises_and_fades():
    """动画曲线：前 400ms 原地全亮，之后 600ms 上升 30px 并淡出。"""
    n = DamageNumber(0, 0, 100)
    n.update(0.2)
    assert n.alpha == 1.0 and n.rise == 0.0
    n.update(0.2)                      # 累计 0.4s：仍停在原位
    assert n.alpha == 1.0 and n.rise == 0.0
    n.update(0.3)                      # 累计 0.7s：淡出中段
    assert 0.0 < n.alpha < 1.0
    assert 10.0 < n.rise < 20.0
    assert n.update(0.4) is False      # 累计 1.1s：寿命结束


def test_fully_faded_at_end_of_life():
    """寿命终点：alpha 归零、上升距离恰为 30px。"""
    n = DamageNumber(0, 0, 100)
    n.update(1.0)
    assert n.alpha == 0.0
    assert n.rise == 30.0
