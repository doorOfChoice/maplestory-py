"""掉出地图底部判定：必须用 WZ 世界坐标的 bounds.bottom，而非相对高度。

bounds.top 非零的图（如 102010000 top=1285）若拿 y 与 height 比较，
站得好好的也会每帧误判坠落扣血、进图即死。
"""
from __future__ import annotations

from game.world import fell_out_of_map


def test_standing_on_high_y_map_is_not_fall_out():
    bounds = {"left": -1371, "top": 1285, "right": 2361, "bottom": 2512,
              "height": 1227}
    assert not fell_out_of_map(1891, bounds)


def test_below_bottom_margin_counts_as_fall_out():
    bounds = {"left": -1371, "top": 1285, "right": 2361, "bottom": 2512,
              "height": 1227}
    assert fell_out_of_map(2512 + 81, bounds)
