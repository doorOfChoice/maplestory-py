"""落地判定的方向语义：单向平台只在下落（或面追上来）时接人，
从下方上升掠过不得被吸附。"""
from __future__ import annotations

from game.core.physics import Physics

BOUNDS = {"left": -2000, "top": -2000, "right": 2000, "bottom": 2000}


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1):
    return {"id": fid, "layer": layer, "platform": 0,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


def make(segs):
    return Physics(segs, [], bounds=BOUNDS)


def test_rising_from_below_edge_does_not_land():
    """从平台下方上升掠过其边缘（脚仍在面下）：不得落地。"""
    ph = make([fh(1, 0, 100, 100, 300, 100)])
    # 上帧脚在面下 0.8px、本帧升到面下 0.2px，均未穿到面上方
    assert ph.landing_candidate(105.0, 100.8, 100.2,
                                prev_x=95.0, band=False) is None


def test_falling_onto_platform_lands():
    """下落穿过平台：正常接住（方向修正不得误伤）。"""
    ph = make([fh(1, 0, 100, 100, 300, 100)])
    assert ph.landing_candidate(105.0, 99.0, 101.0, prev_x=95.0) is ph.by_id[1]


def test_upslope_overtakes_rising_player_lands():
    """上坡面抬升快过上升的脚（受击大横位移情形）→ 仍应接住。"""
    ph = make([fh(1, 0, 100, 100, 200, 0)])   # 45° 上坡：x=100→200, y=100→0
    # 上帧 x=120 脚在面上（y=80）、本帧 x=130 脚升到 75（面在 70）→ 面追上来
    assert ph.landing_candidate(130.0, 80.0, 75.0,
                                prev_x=120.0, band=False) is ph.by_id[1]
