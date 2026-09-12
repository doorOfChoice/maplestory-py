"""近垂直 foothold 视为墙：不参与贴坡/落地，并挡住水平移动。

地图里存在斜率极大的 1~7px 宽斜段（如地图 105090100 的 id667 斜率 12），
它们实为墙，却被当成可行走坡面，走上去会单帧垂直瞬移。
"""

from __future__ import annotations

from game import settings
from game.core.physics import Physics

R = settings.PLAYER_BODY_HALF_W


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1):
    return {"id": fid, "layer": layer, "platform": 0,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


def make(segs):
    return Physics(segs, [])


# 地面 - 陡段(斜率10) - 上层平台：作者用链接连起来，但陡段应被当墙
STEEP = [fh(1, 0, 0, 300, 400, 300, next=2),
         fh(2, 0, 400, 300, 405, 250, prev=1, next=3),
         fh(3, 0, 405, 250, 500, 250, prev=2)]


def test_near_vertical_blocks_horizontal_walk():
    """走向近垂直段：被当作实墙挡住，不被台阶豁免放行。"""
    ph = make(STEEP)
    assert ph.wall_block(390.0, 410.0, 300.0, 300.0,
                         cur_fh=ph.by_id[1]) < 400.0


def test_near_vertical_not_a_ground_surface():
    """近垂直段不作为可站立的支撑面。"""
    ph = make(STEEP)
    assert ph.grounded_surface(402.0, 280.0) is None
    assert ph.landing_candidate(402.0, 279.0, 281.0, band=True) is None


def test_normal_steep_stair_still_walkable():
    """斜率 1.9 的普通台阶（地图常见）不受影响，照旧可贴坡。"""
    stair = [fh(1, 0, 0, 300, 100, 280, next=2),
             fh(2, 0, 100, 280, 120, 260, prev=1, next=3),   # 斜率 1.0
             fh(3, 0, 120, 260, 300, 260, prev=2)]
    ph = make(stair)
    assert ph.walk_surface(ph.by_id[1], 110.0, 1) is ph.by_id[2]
