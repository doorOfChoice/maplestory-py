"""快速移动（瞬移）：落点只在玩家当前 layer 上找，不跨层、不嵌墙、不穿地。"""

from __future__ import annotations

import types

import pygame

from game import settings
from game.core.physics import Physics
from game.entities.player import Player

R = settings.PLAYER_BODY_HALF_W


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1):
    return {"id": fid, "layer": layer, "platform": 0,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


class StubAssets:
    swim = False


def _stub_init(self, assets, quest_defs=None):
    self.inventory = {}
    self.skills = None
    self.quests = {}


def make_player(monkeypatch, ph, x, y, layer=0, cur=None, on_ground=True):
    monkeypatch.setattr(Player, "_load_anim",
                        lambda self, pose, flip=None: setattr(self, "pose", pose))
    monkeypatch.setattr(Player, "_init_new_game", _stub_init)
    p = Player(StubAssets(), x, y)
    p.on_ground = on_ground
    p.cur_fh = cur
    p.ground_layer = layer
    p.facing_right = True
    return p


def at(fid, ph):
    return ph.by_id[fid]


# ── 垂直瞬移：取 range 内最近的平台（layer 无关）─────────────────────
def test_vertical_up_lands_on_nearest_platform(monkeypatch):
    """↑ 取脚底上方最近的平台（同高前后景平台也算可行走面），并同步 layer。"""
    ph = Physics([fh(1, 0, 0, 300, 400, 300),      # 玩家地面 L0
                  fh(2, 1, 0, 260, 400, 260),      # 上方最近的平台 L1
                  fh(3, 0, 0, 220, 400, 220)], [])  # 更远的本层平台 L0
    p = make_player(monkeypatch, ph, 200, 300 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(130, ph, up=True) is True
    assert p.ground_layer == 1 and p.cur_fh.fid == 2
    assert p.y + settings.FEET_OFFSET == 260.0


def test_vertical_up_without_platform_stays(monkeypatch):
    """↑ range 内没有任何平台 → 原地不动并返回 False（不扣 MP 的依据）。"""
    ph = Physics([fh(1, 0, 0, 300, 400, 300)], [])
    p = make_player(monkeypatch, ph, 200, 300 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    before = (p.x, p.y)
    assert p.teleport(130, ph, up=True) is False
    assert (p.x, p.y) == before and p.on_ground is True


def test_vertical_down_lands_on_nearest_platform(monkeypatch):
    """↓ 取脚底下方最近的平台，并同步 layer。"""
    ph = Physics([fh(1, 0, 0, 100, 400, 100),
                  fh(2, 1, 0, 150, 400, 150),      # 下方最近的平台 L1
                  fh(3, 0, 0, 200, 400, 200)], [])
    p = make_player(monkeypatch, ph, 200, 100 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(130, ph, down=True) is True
    assert p.ground_layer == 1 and p.cur_fh.fid == 2
    assert p.y + settings.FEET_OFFSET == 150.0


def test_vertical_down_without_platform_stays(monkeypatch):
    """↓ 下方无平台 → 原地不动，避免掉出世界。"""
    ph = Physics([fh(1, 0, 0, 100, 400, 100)], [])
    p = make_player(monkeypatch, ph, 200, 100 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    before = (p.x, p.y)
    assert p.teleport(130, ph, down=True) is False
    assert (p.x, p.y) == before


def test_vertical_down_onto_stair_riser_not_embedded(monkeypatch):
    """竖直下瞬移恰好落在台阶下层、身体压在 riser 上时，应被推到墙外，不嵌墙。"""
    ph = Physics([fh(1, 0, 0, 200, 400, 200),        # 下层地面
                  fh(2, 0, 0, 100, 400, 100),        # 上层地面
                  fh(3, 0, 200, 200, 200, 150)], [])  # 台阶 riser（落地实墙）
    p = make_player(monkeypatch, ph, 206, 100 - settings.FEET_OFFSET,
                    layer=0, cur=at(2, ph))
    assert p.teleport(300, ph, down=True) is True
    assert p.on_ground is True
    assert p.y + settings.FEET_OFFSET == 200.0
    assert p.x >= 200.0 + R - 0.01          # 身体在 riser 右侧，不嵌入


# ── 水平瞬移：方向以按键为准 / 同层吸附 / 撞墙 / 落点必在平台 ────────
def test_horizontal_snaps_to_same_layer_slope(monkeypatch):
    """水平落在同层「更低一段」的坡面（小落差）→ 吸附贴地，不悬空。"""
    ph = Physics([fh(1, 0, 0, 200, 100, 200),
                  fh(2, 0, 100, 210, 400, 210)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(130, ph, direction=1) is True
    assert p.on_ground is True and p.cur_fh.fid == 2
    assert p.y + settings.FEET_OFFSET == 210.0


def test_horizontal_direction_follows_left_key(monkeypatch):
    """水平方向以按下的方向键为准：面朝右按 ← 也向左位移，并转向。"""
    ph = Physics([fh(1, 0, 0, 200, 400, 200)], [])
    p = make_player(monkeypatch, ph, 300, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(130, ph, direction=-1) is True
    assert abs(p.x - 170.0) < 1e-6
    assert p.facing_right is False


def test_horizontal_without_direction_stays(monkeypatch):
    """未按方向键（direction=0）→ 不位移，即使落点在平台上也不触发。"""
    ph = Physics([fh(1, 0, 0, 200, 400, 200)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    before = (p.x, p.y)
    assert p.teleport(130, ph, direction=0) is False
    assert (p.x, p.y) == before


def test_teleport_on_rope_stays(monkeypatch):
    """挂在绳/梯上时不能快速移动 → 原地不动，即使落点在平台上。"""
    ph = Physics([fh(1, 0, 0, 200, 400, 200)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    p.climbing = True
    before = (p.x, p.y)
    assert p.teleport(130, ph, direction=1) is False
    assert (p.x, p.y) == before


def test_horizontal_lands_on_overlapping_layer_ground(monkeypatch):
    """本层前方无地面、但相邻 layer 有同高地面（叠层可行走面）→ 吸附并同步 layer。"""
    ph = Physics([fh(1, 0, 0, 200, 100, 200),
                  fh(2, 1, 100, 200, 400, 200)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(130, ph, direction=1) is True
    assert p.on_ground is True and p.cur_fh.fid == 2
    assert p.ground_layer == 1


def test_horizontal_blocked_by_wall_not_embedded(monkeypatch):
    """水平撞同层实墙 → 钳在墙外（身体边缘贴墙），不嵌进墙体。"""
    ph = Physics([fh(1, 0, 0, 200, 400, 200),
                  fh(2, 0, 250, 200, 250, 100),     # 落地实墙
                  fh(3, 0, 250, 100, 400, 100)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(300, ph, direction=1) is True
    assert p.x == 250.0 - R
    assert p.on_ground is True and p.y + settings.FEET_OFFSET == 200.0


def test_horizontal_over_gap_lands_on_lower_platform(monkeypatch):
    """水平瞬移到缺口上方、下方有更低的平台 → 吸附到低平台落下，不以悬空结束。"""
    ph = Physics([fh(1, 0, 0, 200, 100, 200),
                  fh(2, 0, 150, 500, 400, 500)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(300, ph, direction=1) is True
    assert p.on_ground is True and p.x == 350.0
    assert p.y + settings.FEET_OFFSET == 500.0


def test_horizontal_over_void_stays(monkeypatch):
    """水平瞬移到下方无任何地面的深渊上方 → 原地不动，不掉出世界。"""
    ph = Physics([fh(1, 0, 0, 200, 100, 200)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    before = (p.x, p.y)
    assert p.teleport(300, ph, direction=1) is False
    assert (p.x, p.y) == before and p.on_ground is True


def test_airborne_horizontal_lands_on_adjacent_platform(monkeypatch):
    """悬空水平瞬移落到相邻（同高容差内）平台 → 落地，不平移悬空。"""
    ph = Physics([fh(1, 0, 0, 200, 400, 200)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=None, on_ground=False)
    assert p.teleport(100, ph, direction=1) is True
    assert p.on_ground is True and abs(p.x - 150.0) < 1e-6
    assert p.y + settings.FEET_OFFSET == 200.0


def test_airborne_horizontal_only_platform_out_of_range_stays(monkeypatch):
    """悬空水平瞬移终点的平台超出瞬移范围 → 不触发、不平移掉落。"""
    ph = Physics([fh(1, 0, 0, 200, 100, 200),
                  fh(2, 0, 150, 500, 400, 500)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=None, on_ground=False)
    before = (p.x, p.y)
    assert p.teleport(200, ph, direction=1) is False
    assert (p.x, p.y) == before and p.on_ground is False


def test_horizontal_lands_on_far_higher_platform(monkeypatch):
    """水平瞬移终点无同高平台、但范围内有更高平台 → 落到高平台，不以悬空结束。"""
    ph = Physics([fh(1, 0, 0, 200, 100, 200),
                  fh(2, 0, 150, 100, 400, 100)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(300, ph, direction=1) is True
    assert p.on_ground is True and p.x == 350.0
    assert p.y + settings.FEET_OFFSET == 100.0


def test_airborne_horizontal_lands_on_far_higher_platform(monkeypatch):
    """悬空水平瞬移终点有范围内更高平台 → 落到高平台，不以悬空结束。"""
    ph = Physics([fh(1, 0, 150, 100, 400, 100)], [])
    p = make_player(monkeypatch, ph, 50, 200 - settings.FEET_OFFSET,
                    layer=0, cur=None, on_ground=False)
    assert p.teleport(300, ph, direction=1) is True
    assert p.on_ground is True and p.x == 350.0
    assert p.y + settings.FEET_OFFSET == 100.0


def test_horizontal_follows_linked_stairs(monkeypatch):
    """水平瞬移沿链接阶梯爬山（累计落差远超吸附容差）→ 逐段跟随、不埋进坡体。"""
    segs = [fh(1, 0, 0, 200, 25, 180, next=2),
            fh(2, 0, 25, 180, 50, 160, prev=1, next=3),
            fh(3, 0, 50, 160, 75, 140, prev=2, next=4),
            fh(4, 0, 75, 140, 100, 120, prev=3, next=5),
            fh(5, 0, 100, 120, 150, 100, prev=4)]
    ph = Physics(segs, [])
    p = make_player(monkeypatch, ph, 5, 196 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(130, ph, direction=1) is True
    assert abs(p.x - 135.0) < 1.0
    assert p.on_ground is True and p.cur_fh.fid == 5
    assert abs((p.y + settings.FEET_OFFSET) - ph.by_id[5].y_at(p.x)) < 1.0


def test_horizontal_slope_wall_stops_outside(monkeypatch):
    """沿斜坡瞬移爬到坡顶实墙前：身体停在墙外，不因「爬高后墙才生效」而嵌墙。"""
    segs = [fh(1, 0, 0, 200, 100, 160),          # 上坡
            fh(2, 0, 100, 160, 100, 150),        # 坡顶矮 riser（实墙）
            fh(3, 0, 100, 150, 300, 150)]        # 墙后上层
    ph = Physics(segs, [])
    p = make_player(monkeypatch, ph, 20, ph.by_id[1].y_at(20) - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(140, ph, direction=1) is True
    assert p.x <= 100.0 - R + 0.01
    assert p.on_ground is True and p.cur_fh.fid == 1


def test_horizontal_edge_wall_not_tunneled(monkeypatch):
    """链续段同高的边缘实体墙不被「台阶豁免」误放行：落点被推回墙面外。"""
    segs = [fh(1, 0, 0, 200, 100, 200, next=2),      # 地面，右端 x=100
            fh(2, 0, 100, 200, 300, 200, prev=1),     # 同高续段
            fh(3, 0, 100, 200, 100, 150)]             # 边缘实体墙
    ph = Physics(segs, [])
    p = make_player(monkeypatch, ph, 95, 200 - settings.FEET_OFFSET,
                    layer=0, cur=at(1, ph))
    assert p.teleport(8, ph, direction=1) is True
    assert p.x <= 100.0 - R + 0.01

