"""玩家扔出的整堆物品：有拾取锁不会瞬间捡回，锁解除后按原数量捡回。"""

from types import SimpleNamespace

from game.systems.combat import Combat
from game.systems.inventory import Inventory, Item


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


def test_fresh_player_drop_not_immediately_pickable():
    c = Combat(FakeAssets())
    p = _player()
    c.drop_player_item(p, Item(id="2000000", name="红药", count=3, kind="consume"))
    assert not c.pickup(p)


def test_drop_then_pickup_keeps_full_count():
    c = Combat(FakeAssets())
    p = _player()
    d = c.drop_player_item(p, Item(id="2000000", name="红药", count=12, kind="consume"))
    d._age = d.pickup_lock + 0.1
    d.x = p.x
    d.y = p.y
    assert c.pickup(p)
    c.update(0.25, p)
    total = sum(i.count for i in p.inventory.consumes.values())
    assert total == 12
