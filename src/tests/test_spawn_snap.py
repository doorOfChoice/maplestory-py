"""出生点贴地：portal 标注 y 常略高于/低于地面线，需双向吸附防穿地。"""
from game import settings
from game.core.physics import Physics


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


FLAT = [fh(1, 0, 0, 100, 100, 100)]


def test_spawn_snap_from_below_ground_line():
    """脚底在地面线下方数 px（WZ portal 常见）：吸附上来而不是穿地。"""
    p = Physics(FLAT, [])
    surf = p.spawn_surface(50, 104.0)
    assert surf is not None and surf.fid == 1


def test_spawn_snap_from_above_ground_line():
    """脚底悬在地面线上方（容差内）：吸附到脚下地面。"""
    p = Physics(FLAT, [])
    surf = p.spawn_surface(50, 60.0)
    assert surf is not None and surf.fid == 1


def test_spawn_snap_rejects_distant_surface():
    """超出吸附容差的面不参与（真掉出地图时保留坠落判定）。"""
    p = Physics(FLAT, [])
    assert p.spawn_surface(50, 100.0 + settings.SPAWN_SNAP_TOL + 1) is None
    assert p.spawn_surface(50, 100.0 - settings.SPAWN_SNAP_TOL - 1) is None


def test_spawn_snap_prefers_nearest_surface():
    """多层各有面时取离脚底最近的一条。"""
    p = Physics(FLAT + [fh(2, 1, 0, 60, 100, 60)], [])
    surf = p.spawn_surface(50, 104.0)
    assert surf.fid == 1
