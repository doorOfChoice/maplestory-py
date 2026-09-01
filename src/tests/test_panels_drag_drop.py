"""背包拖拽扔东西：拖出来源窗口即扔；双击才使用/穿戴/脱下。"""

from types import SimpleNamespace

import pygame

from game.systems.inventory import Inventory, Item
from game.render.panels import Panels


class FakeUI:
    font = None
    font_small = None
    font_tiny = None


class FakeAssets:
    def ui_surface(self, img, path):
        return None

    def item_icon(self, iid):
        return None

    def equip_icon(self, iid):
        return None


def make_panels():
    pygame.init()
    p = SimpleNamespace(inventory=Inventory(), refresh_equips=lambda: None,
                        hp=10, max_hp=50, mp=10, max_mp=50)
    p.inventory.add(Item(id="2000000", name="红药", count=12, kind="consume",
                         info={"spec": {"hp": 50}}))
    pan = Panels(FakeUI(), FakeAssets())
    pan.inv_visible = True
    pan.equip_visible = True
    pan._cell_rects = [(pygame.Rect(40, 100, 36, 34), "consume", 0)]
    pan._slot_rects = []
    pan._tab_rects = []
    pan._inv_rect = pygame.Rect(4, 50, 175, 307)
    pan._equip_rect = pygame.Rect(181, 50, 175, 304)
    return pan, p


def test_drag_out_of_home_window_drops_item():
    pan, p = make_panels()
    pan.handle_mouse_down((58, 117), p)
    pan.handle_mouse_motion((500, 300))
    got = pan.handle_mouse_up((500, 300), p)
    assert got is not None and got.count == 12
    assert p.inventory.consumes == {}


def test_release_over_other_window_still_drops():
    """从背包拖出、松手在纸娃娃窗口上：也应扔出，不该误触发使用。"""
    pan, p = make_panels()
    pan.handle_mouse_down((58, 117), p)
    pan.handle_mouse_motion((250, 200))
    got = pan.handle_mouse_up((250, 200), p)
    assert got is not None
    assert p.inventory.consumes == {}


def test_drag_back_into_home_window_cancels():
    pan, p = make_panels()
    pan.handle_mouse_down((58, 117), p)
    pan.handle_mouse_motion((500, 300))
    got = pan.handle_mouse_up((58, 117), p)
    assert got is None
    assert p.inventory.consumes["2000000"].count == 12


def test_single_click_does_not_use():
    pan, p = make_panels()
    pan.handle_mouse_down((58, 117), p)
    pan.handle_mouse_up((58, 117), p)
    assert p.inventory.consumes["2000000"].count == 12
    assert p.hp == 10


def test_double_click_uses_consume():
    pan, p = make_panels()
    for _ in range(2):
        pan.handle_mouse_down((58, 117), p)
        pan.handle_mouse_up((58, 117), p)
    assert p.inventory.consumes["2000000"].count == 11
    assert p.hp == 50    # 10 + 50 被 max_hp 截断
