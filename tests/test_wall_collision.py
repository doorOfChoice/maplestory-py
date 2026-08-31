"""竖直墙阻挡 = 身体盒规则的行为测试。"""
from game import settings
from game.physics import Physics

R = settings.PLAYER_BODY_HALF_W
EPS = settings.WALL_FEET_EPS


def fh(fid, layer, x1, y1, x2, y2, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": -1, "next": -1}


def make(segs, bounds=None):
    return Physics(segs, [], bounds=bounds)


# 地面 y=100 (0..200)，边缘 stub 向下 25px（= 平台右端）
EDGE = [fh(1, 0, 0, 100, 200, 100),
        fh(2, 0, 200, 100, 200, 125)]


def make_cliff():
    """地面 y=300 (0..100)；崖壁 (100,300)-(100,250)；上层平台 y=250 (100..300)。"""
    return make([fh(1, 0, 0, 300, 100, 300),
                 fh(2, 0, 100, 300, 100, 250),
                 fh(3, 1, 100, 250, 300, 250)])


def test_walk_off_edge_stub():
    """墙顶与脚底平齐的边缘 stub 不挡人，可直接走出坠落。"""
    p = make(EDGE)
    assert p.wall_block(150.0, 260.0, 100.0, 100.0) == 260.0


def test_cliff_blocks_ground_walk():
    """地面走向高出的崖壁 → 钳在墙面外。"""
    p = make_cliff()
    assert p.wall_block(50.0, 200.0, 300.0, 300.0) == 100.0 - R


def test_jump_clears_cliff():
    """脚底抬到崖顶之上（超过容差）→ 水平放行翻上去。"""
    p = make_cliff()
    assert p.wall_block(60.0, 200.0, 244.0, 244.0) == 200.0


def test_sweep_uses_feet_at_crossing():
    """同帧内从崖顶上方落到崖壁区间：按到达墙面一刻的脚底判定 → 挡住。"""
    p = make_cliff()
    # 起帧脚底 244（崖顶上方，可越过），落帧 320（崖壁区间内）
    hit = p.wall_block(60.0, 200.0, 244.0, 320.0)
    assert hit == 100.0 - R


def test_dangling_wall_walk_under():
    """墙底高于身体盒顶（悬空浮岛贴地侧不遮头）→ 从下面走过。"""
    p = make([fh(1, 0, 0, 300, 400, 300),        # 地面
              fh(2, 1, 150, 90, 250, 90),        # 浮岛顶
              fh(3, 1, 150, 90, 150, 90 + 10)])  # 浮岛左缘 stub 向下 10px
    assert p.wall_block(100.0, 200.0, 300.0, 300.0) == 200.0


def test_overhead_platform_edge_walks_under():
    """上层平台边缘 riser 垂到脚底上方（净空虽小，MS 无下蹲）→ 横向穿过。"""
    p = make([fh(1, 0, 0, 300, 400, 300),        # 玩家地面 y=300
              fh(2, 2, 150, 265, 400, 265),      # 上层地面 y=265（L2）
              fh(3, 2, 150, 265, 150, 300 - 5)]) # 上层左缘 riser 垂到 295（脚上方 5px）
    # 脚在 300，墙底 295 在脚上方 → 悬挂边缘，可走过
    assert p.wall_block(120.0, 220.0, 300.0, 300.0) == 220.0


def test_grounded_wall_blocks():
    """墙底扎到脚平面（落地实墙）→ 挡住。"""
    p = make([fh(1, 0, 0, 300, 400, 300),
              fh(2, 0, 150, 300, 150, 265),      # 落地 riser：底=脚=300，顶=265
              fh(3, 0, 150, 265, 400, 265)])
    assert p.wall_block(120.0, 220.0, 300.0, 300.0) == 150.0 - R


def test_touching_wall_for_slide():
    """前沿贴着阻挡墙 → touching_wall 返回墙面 x（贴墙下滑/蹬墙跳判定）。"""
    p = make_cliff()
    assert p.touching_wall(100.0 - R, 300.0, 1) == 100.0
    assert p.touching_wall(100.0 - R, 244.0, 1) is None  # 已高于崖顶


def test_vr_bounds_clamp():
    """没画墙的地图边界由 VR 钳制兜底。"""
    p = make(EDGE, bounds={"left": 0, "top": 0, "right": 1000, "bottom": 500})
    assert p.wall_block(980.0, 1200.0, 300.0, 300.0) == 1000.0 - R


def test_wall_chain_merge():
    """同 x 相连（间隙≤2px）的多段竖直 foothold 合并成一整面墙。"""
    p = make([fh(1, 0, 0, 400, 50, 400),
              fh(2, 0, 50, 400, 50, 350),
              fh(3, 0, 50, 348, 50, 300),   # 与上段间隙 2px → 合并
              fh(4, 0, 50, 300, 150, 300)])
    assert len(p.chains) == 1
    assert p.chains[0].ytop == 300.0 and p.chains[0].ybottom == 400.0
    # 脚在 300..400 区间（身体盒相交）→ 两侧都被挡
    assert p.wall_block(20.0, 60.0, 350.0, 350.0) == 50.0 - R
    assert p.wall_block(80.0, 40.0, 350.0, 350.0) == 50.0 + R
