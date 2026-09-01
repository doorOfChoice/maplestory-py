"""链接续段行走模型：台阶跟走 / 前景坡道横跨 / 开放边缘。"""
from game import settings
from game.core.physics import Physics

R = settings.PLAYER_BODY_HALF_W
SU = settings.PLAYER_STEP_UP


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


def make(segs, bounds=None):
    return Physics(segs, [], bounds=bounds)


# ── 一级台阶（真实 Henesys 结构：平台 - 竖直riser - 平台）────────────
# L0/P2: #31 (174,425)-(186,425) next=#32; #32 V riser next=#25; #25 (186,395)-(225,395)
STAIR = [fh(31, 0, 174, 425, 186, 425, prev=30, next=32),
         fh(32, 0, 186, 425, 186, 395, prev=31, next=25),   # 一级 riser 30px
         fh(25, 0, 186, 395, 225, 395, prev=32, next=14)]


def test_linked_stair_continuation_skips_riser():
    """从矮台沿 next 穿过竖直 riser 找到高台。"""
    p = make(STAIR)
    lower, riser, upper = p.by_id[31], p.by_id[32], p.by_id[25]
    assert p.linked_continuation(lower, True) is upper
    assert p.linked_continuation(upper, False) is lower


def test_walk_up_stair_no_block():
    """走上一级台阶：riser 墙链被豁免，不把人挡在墙外。"""
    p = make(STAIR)
    lower = p.by_id[31]
    # 站在矮台(feet=425)，向右迈过 x=186 的 riser
    x = p.wall_block(180.0, 200.0, 425.0, 425.0, cur_fh=lower)
    assert x == 200.0  # 未被挡在 186-R


def test_walk_up_stair_follows_up():
    """越过 riser 后脚底抬到高台高度。"""
    p = make(STAIR)
    lower = p.by_id[31]
    surf = p.walk_surface(lower, 195.0, 1)  # 已越过低台右端(186)
    assert surf is not None and surf.fid == 25
    assert surf.y_at(195.0) == 395.0  # 抬升 30px


# ── 前景坡道横跨路面（无链接）：人应留在原地面 ─────────────────────
# 主路 y=455 (L1)；前景矮条 y=425 (L0) 在 x 上重叠，但两者无 prev/next 关系
ROAD = [fh(161, 1, 90, 455, 180, 455, prev=171, next=164),
        fh(164, 1, 180, 455, 270, 455, prev=161, next=168),
        fh(30, 0, 96, 425, 174, 425, prev=29, next=31)]  # 前景条,独立链


def test_foreground_ramp_does_not_capt():
    """前景独立面覆盖脚上方，但不参与贴坡：人留在地面链。"""
    p = make(ROAD)
    road = p.by_id[161]
    surf = p.walk_surface(road, 130.0, 1)   # x=130 有前景条(425)横在上方
    assert surf is road                     # 仍在 road 上，不被吸到 425
    assert surf.y_at(130.0) == 455.0


def test_walk_surface_stays_while_covered():
    """cur 覆盖 x 时永远续命自身。"""
    p = make(ROAD)
    road = p.by_id[164]
    assert p.walk_surface(road, 220.0, 1) is road


# ── 开放边缘：越过端点且无续段链接 → None（转坠落）──────────────────
def test_open_edge_falls():
    edge = [fh(1, 0, 0, 100, 200, 100, prev=0, next=0)]  # 两端无链接
    p = make(edge)
    assert p.walk_surface(p.by_id[1], 260.0, 1) is None


# ── 高落差不自动上步：>STEP_UP 的 riser 仍需跳 ──────────────────────
def test_tall_riser_not_steppable():
    tall = [fh(1, 0, 0, 500, 100, 500, next=2),
            fh(2, 0, 100, 500, 100, 400, prev=1, next=3),  # 100px riser
            fh(3, 0, 100, 400, 300, 400, prev=2)]
    p = make(tall)
    lower = p.by_id[1]
    assert p.walk_surface(lower, 120.0, 1) is None         # 高差 100 > 36
    assert p.wall_block(95.0, 130.0, 500.0, 500.0, lower) < 100  # 被挡
