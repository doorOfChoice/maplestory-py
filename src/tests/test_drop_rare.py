"""掉落装备随机基础属性：30% 稀有 → 2~4 条主属性浮动 +1~+5，写入 info。

纯函数 roll_drop_bonus（注入 rng）驱动；combat._take 对「怪物掉落」的装备
在拾取时并浮动值进 info；玩家自己扔出的装备不随机。装备存档携带 info，
重开读档后浮动值不变。
"""

from __future__ import annotations

import random
from types import SimpleNamespace

from game.core import equip_roll
from game.systems.combat import Combat, DropItem
from game.systems.inventory import Inventory, Item, make_item
from game import settings


class FakeAssets:
    """装备 info 用「非主属性池」的固定基础值，便于区分是否被随机过。"""
    def equip_info(self, iid):
        return {"islot": "Ri", "incPDD": 50}

    def consume_info(self, iid):
        return {"spec": {}}

    def item_name(self, iid):
        return "测试戒指"

    def item_icon(self, iid):
        return None

    def equip_icon(self, iid):
        return None

    def meso_frames(self, amount: int = 0):
        return []

    footholds = []


def _player():
    return SimpleNamespace(x=0.0, y=-20.0, inventory=type("Inv", (), {
        "equips": [], "equipped": {},
        "add": lambda self, it: (self.equips.append(it), True)[1],
    })())


def _seed_under_chance():
    """找第一个 random() < 掉率 的种子，保证稀有判定必触发（非 flaky）。"""
    for s in range(10000):
        if random.Random(s).random() < settings.DROP_RARE_CHANCE:
            return s
    raise AssertionError("找不到低于掉率的种子")


def test_roll_drop_bonus_chance_zero_never():
    """掉率为 0 → 恒不随机。"""
    assert equip_roll.roll_drop_bonus(random.Random(1), chance=0.0) == {}


def test_roll_drop_bonus_lines_values_pool():
    """必出（chance=1）时：条数 2~4、各值 +1~+5、只命中主属性池。"""
    for seed in range(30):
        bonus = equip_roll.roll_drop_bonus(random.Random(seed), chance=1.0)
        assert 2 <= len(bonus) <= 4
        assert len(bonus) == len(set(bonus))
        for key, value in bonus.items():
            assert key in settings.DROP_RARE_STATS
            assert 1 <= value <= 5


def test_roll_drop_bonus_deterministic_same_seed():
    """同种子结果确定。"""
    a = equip_roll.roll_drop_bonus(random.Random(7), chance=1.0)
    b = equip_roll.roll_drop_bonus(random.Random(7), chance=1.0)
    assert a == b


def test_take_mob_drop_equip_rolls_base_stats():
    """怪物掉落的装备，拾取后基础属性被随机并写入 info（保留非池基础值）。"""
    c = Combat(FakeAssets(), rng=random.Random(_seed_under_chance()))
    p = _player()
    c._take(DropItem(10.0, 0.0, item={"id": "01112020", "count": 1,
                                      "name": "测试戒指"},
                     ground_y=0.0, assets=FakeAssets()), p)
    got = p.inventory.equips[0]
    assert got.info.get("incPDD") == 50           # 非池词条保持原值
    assert set(got.info) & set(settings.DROP_RARE_STATS)   # 主属性被随机过


def test_take_player_drop_equip_not_randomized():
    """玩家自己扔出的装备再捡起，不随机（保留 WZ 原值）。"""
    c = Combat(FakeAssets(), rng=random.Random(random.Random(_seed_under_chance()).random()))
    p = _player()
    c._take(DropItem(10.0, 0.0, item={"id": "01112020", "count": 1,
                                      "name": "测试戒指"},
                     ground_y=0.0, assets=FakeAssets(), from_mob=False), p)
    assert p.inventory.equips[0].info == {"islot": "Ri", "incPDD": 50}


def test_player_drop_roundtrip_preserves_rolled_info():
    """玩家扔出带随机属性的装备再捡回：info/extra/tuc 必须原样保留，不得重置回 WZ 基值。"""
    assets = FakeAssets()
    c = Combat(assets, rng=random.Random(_seed_under_chance()))
    original = make_item("01112020", assets)
    original.info.update({"incPAD": 33, "incSTR": 4})   # 模拟已随机
    original.extra = {"incPAD": 2, "incXP": 5}
    original.tuc = 3
    thrown = c.drop_player_item(_player(), original)
    assert thrown.item.get("info")  # 扔出时必须携带完整属性（info/extra/tuc）
    assert thrown.item.get("extra")
    assert "tuc" in thrown.item

    picker = _player()
    c._take(thrown, picker)
    got = picker.inventory.equips[0]
    assert got.info.get("incPAD") == 33 and got.info.get("incSTR") == 4
    assert got.info.get("incPDD") == 50      # WZ 基值仍在
    assert got.extra == {"incPAD": 2, "incXP": 5}
    assert got.tuc == 3


def test_equip_info_roundtrip_preserves_roll():
    """装备存档携带 info，读档后随机值不变。"""
    inv = Inventory()
    item = Item(id="01112020", name="戒指", kind="equip",
                info={"islot": "Ri", "incPAD": 33, "incSTR": 4})
    inv.equips.append(item)
    restored = Inventory.from_dict(inv.to_dict(), FakeAssets())
    got = restored.equips[0].info
    assert got.get("incPAD") == 33 and got.get("incSTR") == 4
    assert got.get("incPDD") == 50   # WZ 基值仍在（未覆盖）


class SharedInfoAssets(FakeAssets):
    """equip_info 返回缓存同一 dict（模拟真实 assets 的共享缓存问题）。"""
    def __init__(self):
        self.cache = {}

    def equip_info(self, iid):
        if iid not in self.cache:
            self.cache[iid] = {"islot": "Ri", "incPDD": 50}
        return self.cache[iid]


def test_make_item_equip_info_not_shared():
    """两件同 id 装备的 info 各自独立：随机一件不污染另一件（缓存必须拷贝）。"""
    assets = SharedInfoAssets()
    first = make_item("01112020", assets)
    second = make_item("01112020", assets)
    assert first.info is not second.info
    first.info.update({"incPAD": 33})
    assert second.info.get("incPAD") is None
    assert assets.cache["01112020"] == {"islot": "Ri", "incPDD": 50}


def test_make_item_consume_info_not_shared():
    """消耗品 spec 同样拷贝：一件的 spec 改动不影响下一件与缓存。"""
    assets = SharedInfoAssets()
    first = make_item("2000000", assets)
    second = make_item("2000000", assets)
    assert first.info is not second.info


def test_two_mob_drops_can_have_distinct_rolls():
    """真实链路（_take）里连续两次拾取同 id 装备，随机一次后另一件保持 WZ 原值。"""
    assets = SharedInfoAssets()
    c = Combat(assets, rng=random.Random(_seed_under_chance()))
    p1, p2 = _player(), _player()
    c._take(DropItem(10.0, 0.0, item={"id": "01112020", "count": 1,
                                      "name": "测试戒指"},
                     ground_y=0.0, assets=assets), p1)
    c._take(DropItem(10.0, 0.0, item={"id": "01112020", "count": 1,
                                      "name": "测试戒指"},
                     ground_y=0.0, assets=assets), p2)
    assert assets.cache["01112020"] == {"islot": "Ri", "incPDD": 50}
