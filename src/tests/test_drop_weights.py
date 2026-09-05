"""掉落率：逐件独立掷骰（原版模型），常见「其他」类高频掉、装备极稀有、可能全不中。"""

import pygame

from game import settings
from game.core.physics import Physics
from game.entities.monster import Monster


class DropAssets:
    """最小资产桩：只提供指定掉落表。"""

    def __init__(self, drops):
        self._drops = drops
        self._surf = pygame.Surface((12, 12))

    def mob_info(self, mob_id):
        return {"name": "T", "stats": {"hp": 10, "exp": 1,
                                       "weaponAttack": 1, "speed": 0},
                "drops": self._drops}

    def mob_frames(self, mob_id, action, flip=False):
        return [(self._surf, 100)]

    def mob_origin(self, mob_id, action):
        return (0, 0)


def make_mob(drops):
    seg = [{"id": 1, "layer": 0, "platform": 0, "x1": 0, "y1": 0,
            "x2": 500, "y2": 0, "prev": -1, "next": -1}]
    ph = Physics(seg, [], bounds={"left": 0, "right": 500,
                                  "top": 0, "width": 500, "height": 100})
    return Monster(DropAssets(drops), {"id": "210100", "x": 210, "y": 0,
                                       "cy": 0, "rx0": 0, "rx1": 500}, 0, ph)


def roll_ids(mob, n):
    return [d["id"] if d is not None else None
            for d in (mob.roll_drop() for _ in range(n))]


def test_etc_item_drops_about_its_category_rate():
    """单件「其他」(4xxxxxx)的实测频率应接近其配置掉率，而非必掉。"""
    mob = make_mob([{"id": "4000004", "name": "绿液球"}])
    rate = settings.DROP_ITEM_RATE["4"]
    hits = sum(1 for i in roll_ids(mob, 20000) if i == "4000004")
    observed = hits / 20000
    assert rate * 0.5 < observed < min(1.0, rate * 1.7), \
        f"实测 {observed:.1%} 偏离配置 {rate:.1%}"


def test_kill_can_drop_nothing():
    """只有极稀有装备的表：绝大多数击杀什么都不掉（金币之外的）。"""
    mob = make_mob([{"id": "1002019", "name": "白頭巾"}])
    none_count = sum(1 for i in roll_ids(mob, 5000) if i is None)
    assert none_count / 5000 > 0.9


def test_equipment_rarer_than_etc_in_same_table():
    """装备与其他同表时，装备实测频率应远低于「其他」（数量级差异）。"""
    mob = make_mob([{"id": "1002019", "name": "白頭巾"},
                    {"id": "4000004", "name": "绿液球"}])
    n = 20000
    ids = roll_ids(mob, n)
    equip = sum(1 for i in ids if i == "1002019")
    etc = sum(1 for i in ids if i == "4000004")
    assert etc > n * 0.05
    assert equip < etc * 0.1


def test_unknown_category_still_droppable():
    """未登记类别（如 9xxxxxxx）走兜底掉率，仍应有机会掉出。"""
    mob = make_mob([{"id": "9000000", "name": "未知"}])
    hits = sum(1 for i in roll_ids(mob, 2000) if i == "9000000")
    assert hits > 0
