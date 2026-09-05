"""击杀结算接入官方掉落表：有数据的怪按 drop_data 掷骰，无数据的怪走旧启发式。"""

from __future__ import annotations

import random

import pygame

from game.systems.combat import Combat
from game.systems.drops import OfficialDropTable


class _Mob:
    x, cy, sprite_h, level, pd = 10.0, 100.0, 30, 1, 0
    dead = False
    exp = 10
    mob_id = "210100"

    def __init__(self, roll_result=None):
        self._roll_result = roll_result

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x - 15), int(self.cy - 30), 30, 30)

    def take_hit(self, damage: int, from_x=None) -> bool:
        return True

    def roll_drop(self):
        return self._roll_result


class _Player:
    x, y = 0.0, 100.0
    level = 10
    attack_hit_applied = False
    pending_skill = None

    def attack_rect(self) -> pygame.Rect:
        return pygame.Rect(-10, 60, 60, 60)

    def attack_range(self):
        return (50, 50)

    def crit_rate(self) -> float:
        return 0.0

    def crit_mult(self) -> float:
        return 1.5


class _Assets:
    footholds: list = []

    def skill_hit_frames(self, sid):
        return []

    def item_name(self, item_id):
        return f"物品{item_id}"

    def item_icon(self, item_id):
        return pygame.Surface((8, 8))

    def equip_icon(self, item_id):
        return None


def _kill(combat, mob):
    combat.player_attack(_Player(), [mob])


def _table(chance=1_000_000):
    return OfficialDropTable.from_dict({
        "210100": [
            {"item": "0", "min": 8, "max": 12, "chance": chance},
            {"item": "4000000", "min": 2, "max": 4, "chance": chance},
        ],
    })


def test_kill_with_official_table_drops_scripted_meso_and_item():
    """官方表命中的怪：金币按官方区间、物品带官方 id 与数量。"""
    c = Combat(_Assets(), drop_table=_table())
    _kill(c, _Mob())
    meso_drops = [d for d in c.drops if d.is_meso]
    item_drops = [d for d in c.drops if not d.is_meso]
    assert len(meso_drops) == 1 and 8 <= meso_drops[0].meso <= 12
    assert len(item_drops) == 1
    assert item_drops[0].item["id"] == "4000000"
    assert 2 <= item_drops[0].item["count"] <= 4


def test_kill_with_official_table_rolls_each_drop_per_chance():
    """官方表下掉率 0 的行不生成掉落：全 0 时一堆都不出。"""
    c = Combat(_Assets(), drop_table=_table(chance=0))
    _kill(c, _Mob())
    assert c.drops == []


def test_kill_without_official_data_falls_back_to_legacy():
    """表里没有的怪：金币仍按经验启发式必掉，物品走旧 WZ 掉落池。"""
    c = Combat(_Assets(), drop_table=OfficialDropTable.from_dict({}))
    mob = _Mob(roll_result={"id": "4000004", "name": "绿液球"})
    mob.mob_id = "9999999"
    _kill(c, mob)
    meso_drops = [d for d in c.drops if d.is_meso]
    item_drops = [d for d in c.drops if not d.is_meso]
    assert len(meso_drops) == 1 and meso_drops[0].meso >= mob.exp * 3
    assert [d.item["id"] for d in item_drops] == ["4000004"]


def test_mob_id_with_leading_zero_matches_official_table():
    """WZ 怪 id 带前导零（0210100）：与 SQL 数字 id 归一后同表命中。"""
    c = Combat(_Assets(), drop_table=_table())
    mob = _Mob()
    mob.mob_id = "0210100"
    _kill(c, mob)
    assert len(c.drops) == 2   # 金币 + 物品，官方路径而非回退


def test_quest_row_drops_only_with_active_quest():
    """任务限定行：玩家进行中任务含该行 quest 才掉，否则按缺行处理。"""
    table = OfficialDropTable.from_dict({
        "210100": [
            {"item": "2000000", "min": 1, "max": 1, "chance": 1_000_000},
            {"item": "4031273", "min": 1, "max": 1, "chance": 1_000_000,
             "quest": 2104},
        ],
    })

    class _Quests:
        def __init__(self, active):
            self._active = active

        def on_kill(self, mob_id):
            pass

        def active_quests(self):
            return self._active

    player = _Player()
    player.quests = _Quests({"2104"})
    c = Combat(_Assets(), drop_table=table)
    c.player_attack(player, [_Mob()])
    assert [d.item["id"] for d in c.drops if not d.is_meso] == \
        ["2000000", "4031273"]

    c2 = Combat(_Assets(), drop_table=table)
    player2 = _Player()
    player2.quests = _Quests(set())
    c2.player_attack(player2, [_Mob()])
    assert [d.item["id"] for d in c2.drops if not d.is_meso] == ["2000000"]


def test_item_row_without_icon_is_not_spawned():
    """图标解析不出（如 8 位商城道具）的行不生成看不见的掉落。"""
    class _NoIconAssets(_Assets):
        def item_icon(self, item_id):
            return None

        def equip_icon(self, item_id):
            return None

    c = Combat(_NoIconAssets(), drop_table=_table())
    _kill(c, _Mob())
    assert [d for d in c.drops if d.is_meso] and \
        not [d for d in c.drops if not d.is_meso]
