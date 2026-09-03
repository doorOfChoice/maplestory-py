"""背包 / 技能窗滚轮滚动：超出一屏时按行滚动、越界夹紧。

测试层透过 Panels.handle_wheel / 绘制时的格子索引来验证行为，不需要 WZ 素材
（用合成玩家建构）。背包一屏 24 格（4 列 × 6 行），技能窗一屏 SKL_ROWS 行。
"""

from types import SimpleNamespace

import pygame

from game.systems.inventory import Inventory, Item
from game.render.panels import Panels, INV_SLOTS, INV_COLS, SKL_ROWS


class FakeUI:
    font = font_small = font_tiny = None


class FakeAssets:
    def ui_surface(self, img, path):
        return None

    def item_icon(self, iid):
        return None

    def equip_icon(self, iid):
        return None

    def skill_icon(self, sid):
        return None


class FakeSkills:
    """最小技能书替身：只提供面板滚动路径用到的公开接口。"""
    def __init__(self, n: int):
        self.job = 3000
        self.defs = {f"s{i}": SimpleNamespace(id=f"s{i}", name=f"技{i}", desc="",
                                              max_level=1, char_level=1,
                                              invisible=False,
                                              stat=lambda lv, k, d=0: d)
                     for i in range(n)}
        self.levels = {}
        self.sp_by_job = {}

    @property
    def total_sp(self):
        return 0

    def sp_for_group(self, group):
        return 0

    def skills_for_group(self, group):
        return sorted(self.defs)

    def learnable(self, owner_group=None):
        return sorted(self.defs)


def make_player(n_consumes: int = 0, n_skills: int = 0):
    skill_item = FakeSkills(n_skills)
    p = SimpleNamespace(
        inventory=Inventory(),
        refresh_equips=lambda: None,
        skills=skill_item,
    )
    for i in range(n_consumes):
        p.inventory.add(Item(id=f"20000{i:03d}", name=f"药{i}", count=1,
                             kind="consume"))
    return p


def make_panels():
    pygame.init()
    pan = Panels(FakeUI(), FakeAssets())
    pan._inv_rect = pygame.Rect(4, 50, 175, 307)
    pan._skill_rect = pygame.Rect(4, 50, 175, 289)
    return pan


def test_inventory_wheel_below_cap_does_not_scroll():
    """物品不满 24 时，滚轮被消费但 scroll 恒为 0（一屏装得下）。"""
    pan = make_panels()
    pan.inv_visible = True
    p = make_player(n_consumes=5)
    assert pan.handle_wheel((10, 60), 1, p)
    assert pan._inv_scroll.get("consume", 0) == 0


def test_inventory_wheel_scrolls_by_one_row():
    """超过 24 种物品后向下滚一行（INV_COLS 格），并在范围内夹紧。"""
    pan = make_panels()
    pan.inv_visible = True
    p = make_player(n_consumes=40)
    assert pan.handle_wheel((10, 60), 1, p)
    assert pan._inv_scroll["consume"] == INV_COLS
    assert pan.handle_wheel((10, 60), 1, p)
    assert pan._inv_scroll["consume"] == INV_COLS * 2


def test_inventory_wheel_clamps_at_bottom():
    """滚到末屏后继续下滚不再越界。"""
    pan = make_panels()
    pan.inv_visible = True
    p = make_player(n_consumes=30)
    for _ in range(20):
        pan.handle_wheel((10, 60), 1, p)
    assert pan._inv_scroll["consume"] == 30 - INV_SLOTS


def test_inventory_wheel_up_never_negative():
    """上滚不越过首屏（scroll 不为负）。"""
    pan = make_panels()
    pan.inv_visible = True
    p = make_player(n_consumes=30)
    pan.handle_wheel((10, 60), 1, p)
    assert pan.handle_wheel((10, 60), -1, p)
    assert pan._inv_scroll["consume"] == 0


def test_skill_wheel_below_cap_does_not_scroll():
    """技能数不超一屏时滚轮被消费但不动。"""
    pan = make_panels()
    pan.skill_visible = True
    p = make_player(n_skills=3)
    assert pan.handle_wheel((10, 60), 1, p)
    assert pan._skill_scroll == 0


def test_skill_wheel_scrolls_and_clamps():
    """技能超过一屏后滚动，末屏夹紧。"""
    pan = make_panels()
    pan.skill_visible = True
    p = make_player(n_skills=SKL_ROWS + 3)
    assert pan.handle_wheel((10, 60), 1, p)
    assert pan._skill_scroll == 1
    for _ in range(10):
        pan.handle_wheel((10, 60), 1, p)
    assert pan._skill_scroll == 3


def test_wheel_outside_window_is_not_consumed():
    """滚轮不在背包/技能窗口上时不消费，返回 False。"""
    pan = make_panels()
    pan.inv_visible = True
    p = make_player(n_consumes=30)
    assert not pan.handle_wheel((500, 500), 1, p)
