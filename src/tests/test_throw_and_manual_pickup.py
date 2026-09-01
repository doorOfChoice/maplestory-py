"""玩家扔物轨迹与手动拾取：从人物中心竖直上抛；拾取只在按 ↑ 时发生。"""

from types import SimpleNamespace

from game import settings
from game.combat import Combat, DropItem
from game.inventory import Inventory, Item


class FakeAssets:
    def consume_info(self, iid):
        return {"spec": {}}

    def item_name(self, iid):
        return "红药"

    def item_icon(self, iid):
        return None

    def equip_icon(self, iid):
        return None

    def meso_frames(self):
        return []

    footholds = []


def _player():
    return SimpleNamespace(x=0.0, y=-20.0, inventory=Inventory())


def test_player_drop_launches_straight_up_from_body_center():
    c = Combat(FakeAssets())
    p = _player()
    d = c.drop_player_item(p, Item(id="2000000", name="红药", count=1, kind="consume"))
    assert d.x == p.x
    assert d.y == p.y
    assert d.vx == 0.0
    assert d.vy < 0.0


def test_pickup_ignores_drops_outside_range():
    c = Combat(FakeAssets())
    p = _player()
    d = DropItem(settings.PICKUP_RANGE + 40.0, p.y, meso=5, ground_y=p.y)
    d._age = 99.0
    c.drops.append(d)
    assert not c.pickup(p)
    assert not d.taken


def test_pickup_collects_drop_within_range():
    c = Combat(FakeAssets())
    p = _player()
    d = DropItem(10.0, p.y, meso=5, ground_y=p.y)
    d._age = 99.0
    c.drops.append(d)
    assert c.pickup(p)
    assert c.meso == 5


def test_attracted_drop_is_collected_without_manual_pickup():
    """吸附中的掉落物飞到身上即自动入包，无需再按 ↑。"""
    c = Combat(FakeAssets())
    p = _player()
    d = DropItem(30.0, p.y, meso=5, ground_y=p.y)
    d.attracted = True
    d._age = 99.0
    c.drops.append(d)
    for _ in range(60):
        c.update(1 / 60, p)
        if not c.drops:
            break
    assert c.meso == 5
