"""一次 Z 只拾取一件（最近的）掉落物：不整套拾取、不自动吸附（原版行为）。"""

from types import SimpleNamespace

from game.systems.combat import Combat, DropItem


def _player():
    return SimpleNamespace(x=0.0, y=-20.0, inventory=None)


def _meso(x: float, value: int = 1) -> DropItem:
    d = DropItem(x, 0.0, meso=value, ground_y=0.0)
    d.vy = 0.0
    d.vx = 0.0
    d._age = 99.0
    return d


def test_one_press_picks_up_only_the_nearest_drop():
    c = Combat(None)
    drops = [_meso(-60.0, 1), _meso(30.0, 2), _meso(-10.0, 3), _meso(80.0, 4),
             _meso(5.0, 5)]
    for d in drops:
        c.drops.append(d)
    p = _player()
    assert c.pickup(p)
    assert c.meso == 5                  # 只进最近的一件（x=5），不是整套
    assert len(c.drops) == 4


def test_repeated_presses_pick_up_one_each_time():
    """附近 5 件需按 5 次 Z 才捡完，每次恰好一件。"""
    c = Combat(None)
    for i in range(5):
        c.drops.append(_meso(6.0 + i * 5.0, 1))
    p = _player()
    for n in range(1, 6):
        c.pickup(p)
        assert c.meso == n
        assert len(c.drops) == 5 - n


def test_press_outside_range_picks_up_nothing():
    c = Combat(None)
    d = _meso(400.0)
    c.drops.append(d)
    assert not c.pickup(_player())
    assert len(c.drops) == 1
