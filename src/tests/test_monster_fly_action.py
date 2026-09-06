"""无 stand/move 帧的怪（如蝙蝠只有 fly）：降级选可用动作，不再空白 Invisible。"""

from __future__ import annotations

from game.entities.monster import Monster
from tests.test_monster import CHAIN, FakeAssets, make


class FlyOnlyAssets(FakeAssets):
    """只给 fly/hit1/die1 帧，仿蝙蝠等在 WZ 里没有 stand/move 的怪。"""

    def mob_frames(self, mob_id, action, flip=False):
        return [(self._surf, 100)] * 2 if action in ("fly", "hit1", "die1") else []


def spawn(assets):
    return Monster(assets, {"id": "2300100", "x": 210, "y": 0, "cy": 0,
                            "rx0": 0, "rx1": 450}, 0, make(CHAIN))


def test_fly_only_mob_is_visible_at_spawn():
    """出生即加载 fly：有帧可画，不是一团空气。"""
    mob = spawn(FlyOnlyAssets())
    assert mob.action == "fly"
    assert mob.anim.frames


def test_fly_only_mob_keeps_flying_while_wandering():
    """漫游全程用 fly（走与停同一动作），任何时刻都有帧。"""
    mob = spawn(FlyOnlyAssets())
    for _ in range(200):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        assert mob.action == "fly"
        assert mob.anim.frames


def test_fly_only_mob_chases_with_fly():
    """追击段同样加载 fly，而不是回落到空的 move/stand。"""
    mob = spawn(FlyOnlyAssets())
    mob.take_hit(5, from_x=100)
    mob.update(0.3, player_x=100, player_y=0, mobs=[])
    mob.update(0.05, player_x=100, player_y=0, mobs=[])
    assert mob.state == "chase"
    assert mob.action == "fly"
    assert mob.anim.frames
