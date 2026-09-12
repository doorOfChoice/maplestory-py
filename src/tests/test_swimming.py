"""水中泳态：info/swim=1 的水图里无重力、8 向游动、fly 姿态（合成数据，不依赖 WZ）。"""

from __future__ import annotations

from game import settings
from game.core.physics import Physics
from game.entities.player import Player


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


def make() -> Physics:
    """水底 454（横贯全图）+ VR 边界；水中无重力，靠边界/水底兜底。"""
    return Physics(
        [fh(1, 0, 0, 454, 800, 454)],
        [], bounds={"left": 0, "top": -600, "right": 800, "bottom": 600})


class Keys:
    up = down = left = right = jump = attack = False


def _stub_init(self, assets, quest_defs=None):
    """最小初始化：只补 update 循环用到的状态字段，避免依赖 WZ。"""
    from game.systems.inventory import Inventory
    self.inventory = Inventory()
    self.skills = _StubSkills()
    self.quests = {}
    self.max_hp = 100
    self.max_mp = 50
    self.hp = 100
    self.mp = 50


class _StubSkills:
    def tick(self, dt):
        pass


class StubAssets:
    def __init__(self, swim: bool = True):
        self.swim = swim
        self.bounds = {"left": 0, "top": -600, "right": 800, "bottom": 600}

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, *a, **k):
        return "swingO1"


def make_player(monkeypatch, ph: Physics, x: float, y: float,
                swim: bool = True) -> Player:
    """泳态测试专用 Player：桩掉动画/新档初始化，仅测移动状态机。"""
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: setattr(self, "pose", pose))
    monkeypatch.setattr(Player, "_init_new_game", _stub_init)
    return Player(StubAssets(swim), x, y)


def test_water_has_no_gravity(monkeypatch):
    """水中不按重力自由落体：半秒内只缓慢下沉，不会瞬间坠到水底。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    k = Keys()
    for _ in range(30):
        p.update(0.016, k, ph)
    assert p.y < 220.0             # 重力下应早已落地；泳态仅下沉 ~43px
    assert p.on_ground is False


def test_up_key_does_nothing_while_swimming(monkeypatch):
    """水中 ↑ 不产生任何作用：持续按 ↑ 不会上浮（只会缓慢下沉）。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    k = Keys()
    k.up = True
    for _ in range(30):
        p.update(0.016, k, ph)
    assert p.y >= 100.0


def test_jump_gives_upward_impulse(monkeypatch):
    """水中按跳跃键给一次略大于游速的向上冲量：navel y 明显上移。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    p.jump()
    assert p.vy <= -settings.SWIM_SPEED     # 冲量大于水平/下潜游速
    for _ in range(10):
        p.update(0.016, Keys(), ph)
    assert p.y < 100.0


def test_jump_while_moving_sideways_still_rises(monkeypatch):
    """边横向游动边按跳跃：向上冲量不能被水平输入清零，仍要上浮。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    k = Keys()
    k.right = True
    p.update(0.016, k, ph)
    y_before = p.y
    p.jump()
    assert p.vy <= -settings.SWIM_SPEED
    for _ in range(10):
        p.update(0.016, k, ph)
    assert p.y < y_before


def test_drop_through_does_nothing_in_water(monkeypatch):
    """水中没有下跳穿平台语义：站在水底按↓+跳不会穿下去。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 454.0 - settings.FEET_OFFSET)
    p.update(0.016, Keys(), ph)
    assert p.on_ground is True
    p.drop_through(ph)
    assert p.on_ground is True


def test_down_dives_downward(monkeypatch):
    """按↓下潜：navel y 增大。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    k = Keys()
    k.down = True
    p.update(0.016, k, ph)
    assert p.y > 100.0


def test_horizontal_swims_and_faces(monkeypatch):
    """按方向水平游动并转向。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    k = Keys()
    k.right = True
    p.update(0.016, k, ph)
    assert p.x > 400.0
    assert p.facing_right is True


def test_swim_uses_fly_pose(monkeypatch):
    """泳态使用 fly 姿态（资产无 swim sprite 时的替代）。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    p.update(0.016, Keys(), ph)
    assert p.pose == "fly"


def test_settles_on_seabed_then_stands(monkeypatch):
    """持续下潜落到水底 foothold 上后，恢复站立（on_ground + stand 姿态）。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 100)
    k = Keys()
    k.down = True
    for _ in range(200):
        p.update(0.016, k, ph)
    assert p.y == 454.0 - settings.FEET_OFFSET
    assert p.on_ground is True
    p.update(0.016, Keys(), ph)     # 常规步行逻辑刷新姿态
    assert p.pose == "stand1"


def test_walks_on_seabed(monkeypatch):
    """站在水底地面时像陆地一样可行走，保持 on_ground。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 454.0 - settings.FEET_OFFSET)
    k = Keys()
    p.update(0.016, k, ph)
    assert p.on_ground is True
    k.right = True
    for _ in range(10):
        p.update(0.016, k, ph)
    assert p.x > 400.0
    assert p.on_ground is True
    assert p.pose == "walk1"


def test_swims_again_after_leaving_seabed(monkeypatch):
    """从水底平台边缘走出去（前方是水域缺口）后重新进入泳态。"""
    ph = Physics([fh(1, 0, 0, 454, 300, 454),
                  fh(2, 0, 600, 454, 800, 454)], [],
                 bounds={"left": 0, "top": -600, "right": 800, "bottom": 600})
    p = make_player(monkeypatch, ph, 290, 454.0 - settings.FEET_OFFSET)
    k = Keys()
    p.update(0.016, k, ph)
    assert p.on_ground is True
    k.right = True
    for _ in range(30):
        p.update(0.016, k, ph)
    assert p.on_ground is False
    assert p.pose == "fly"


def test_leaving_water_restores_gravity(monkeypatch):
    """切到非水图后恢复正常物理：重力生效开始下落。"""
    ph = make()
    p = make_player(monkeypatch, ph, 400, 300)
    k = Keys()
    p.update(0.016, k, ph)          # 先在水里
    p.assets.swim = False
    p.update(0.016, k, ph)
    assert p.vy > 0.0               # 恢复重力加速度
