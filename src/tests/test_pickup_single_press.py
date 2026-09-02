"""一次 Z 只拾取一件（最近的）掉落物：不整套拾取、不自动吸附（原版行为）。

拾取后物品会短暂吸附到角色身上（动画），再收入背包/金币。
"""

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


def _advance_attract(c, player, dt=0.25):
    """推进吸附动画直到完成。"""
    c.update(dt, player)


def test_one_press_picks_up_only_the_nearest_drop():
    c = Combat(None)
    drops = [_meso(-60.0, 1), _meso(30.0, 2), _meso(-10.0, 3), _meso(80.0, 4),
             _meso(5.0, 5)]
    for d in drops:
        c.drops.append(d)
    p = _player()
    assert c.pickup(p)
    _advance_attract(c, p)
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
        _advance_attract(c, p)
        assert c.meso == n
        assert len(c.drops) == 5 - n


def test_press_outside_range_picks_up_nothing():
    c = Combat(None)
    d = _meso(400.0)
    c.drops.append(d)
    assert not c.pickup(_player())
    assert len(c.drops) == 1


def test_pickup_starts_attraction_not_immediate_consumption():
    """拾取后物品进入吸附状态，不会立刻从地面消失。"""
    c = Combat(None)
    d = _meso(10.0, 5)
    c.drops.append(d)
    p = _player()
    assert c.pickup(p)
    assert d.attracting
    assert len(c.drops) == 1
    assert c.meso == 0


def test_attraction_moves_item_toward_player():
    """吸附动画期间物品向玩家位置移动。"""
    c = Combat(None)
    d = DropItem(10.0, 0.0, meso=5, ground_y=0.0)
    d.vy = 0.0
    d.vx = 0.0
    d._age = 99.0
    c.drops.append(d)
    p = _player()
    assert c.pickup(p)
    assert d.attracting
    prev_x = d.x
    c.update(0.05, p)
    assert d.x != prev_x
    assert abs(d.x - p.x) < 100.0


def test_attraction_completes_and_consumes():
    """吸附动画完成后物品被消耗。"""
    c = Combat(None)
    d = _meso(10.0, 7)
    c.drops.append(d)
    p = _player()
    assert c.pickup(p)
    assert d.attracting
    c.update(0.3, p)
    assert not d.attracting
    assert d.taken
    assert c.meso == 7
    assert d not in c.drops
