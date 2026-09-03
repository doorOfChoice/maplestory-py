"""商店面板滚轮：货架 / 背包两栏独立滚动（官方两栏布局，合成素材）。"""
from __future__ import annotations

import types

import pygame

from game.render import shop_panel as sp
from game.render.shop_panel import (
    BG_LCOL_X, BG_LCOL_W, BG_RCOL_X, BG_RCOL_W, BG_ROW_Y0, BG_ROW_H, BG_NROWS,
)
from game.systems.inventory import Inventory, Item
from game.systems.shop import register_lua_shop, register_shop_profile

pygame.font.init()

_VIEW = pygame.Surface((800, 600))
_NPC = "8800001"
_N_SHELF = 8
_N_BAG = 8


class _FakeAssets:
    """仅提供 Shop/backgrnd 合成底图，其余 UI/物品素材回 None（走兜底绘制）。"""

    def ui_surface(self, img: str, path: str):
        if path == "Shop/backgrnd":
            return [pygame.Surface((sp.BG_PANEL_W, sp.BG_PANEL_H), pygame.SRCALPHA)]
        return None

    def item_name(self, item_id: str):
        return f"物品{item_id[-2:]}"

    def item_icon(self, item_id: str):
        return None

    def item_price(self, item_id: str):
        return None

    def equip_icon(self, item_id: str):
        return None


def _make_panel():
    shelf = [(f"029{i:05d}", 10) for i in range(_N_SHELF)]
    register_lua_shop(_NPC, ["wheelshop"])
    register_shop_profile("wheelshop", "杂货", shelf)
    ui = types.SimpleNamespace(
        font=pygame.font.Font(None, 14),
        font_small=pygame.font.Font(None, 12),
        font_tiny=pygame.font.Font(None, 10),
    )
    panel = sp.ShopPanel(ui, _FakeAssets())
    panel.open(_NPC)
    inv = Inventory()
    inv.consumes = {f"028{i:05d}": Item(id=f"028{i:05d}", name=f"背包{i}",
                                        kind="consume", count=1)
                    for i in range(_N_BAG)}
    player = types.SimpleNamespace(inventory=inv)
    combat = types.SimpleNamespace(meso=10000)
    return panel, player, combat


def _wheel_and_click(panel, player, combat, cx, cy, clicks):
    for amount in clicks:
        panel.handle_wheel((cx, cy), amount, player)
        panel.draw(_VIEW, player, combat)


def _first_row_y(panel):
    return panel.rect.y + BG_ROW_Y0 + BG_ROW_H // 2


def test_shelf_wheel_scrolls_shelf():
    """光标在左栏滚一格：第一行变为第 2 件货架物品。"""
    panel, player, combat = _make_panel()
    panel.draw(_VIEW, player, combat)
    cx = panel.rect.x + BG_LCOL_X + BG_LCOL_W // 2
    _wheel_and_click(panel, player, combat, cx, _first_row_y(panel), [1])
    panel.handle_click((cx, _first_row_y(panel)), player, combat)
    assert panel.sel_shelf == 1


def test_shelf_wheel_clamped_at_end():
    """左栏连滚 99 格：钳到末尾，首行为第 4 件（8 - 5 行）。"""
    panel, player, combat = _make_panel()
    panel.draw(_VIEW, player, combat)
    cx = panel.rect.x + BG_LCOL_X + BG_LCOL_W // 2
    _wheel_and_click(panel, player, combat, cx, _first_row_y(panel), [1] * 99)
    panel.handle_click((cx, _first_row_y(panel)), player, combat)
    assert panel.sel_shelf == _N_SHELF - BG_NROWS


def test_shelf_wheel_does_not_move_bag():
    """只滚左栏不影响背包列：右栏首行仍是第 1 件背包物品。"""
    panel, player, combat = _make_panel()
    panel.draw(_VIEW, player, combat)
    lx = panel.rect.x + BG_LCOL_X + BG_LCOL_W // 2
    _wheel_and_click(panel, player, combat, lx, _first_row_y(panel), [1] * 3)
    rx = panel.rect.x + BG_RCOL_X + BG_RCOL_W // 2
    panel.handle_click((rx, _first_row_y(panel)), player, combat)
    assert panel.sel_bag == 0


def test_bag_wheel_scrolls_bag():
    """光标在右栏滚一格：第一行变为第 2 件背包物品。"""
    panel, player, combat = _make_panel()
    panel.draw(_VIEW, player, combat)
    rx = panel.rect.x + BG_RCOL_X + BG_RCOL_W // 2
    _wheel_and_click(panel, player, combat, rx, _first_row_y(panel), [1])
    panel.handle_click((rx, _first_row_y(panel)), player, combat)
    assert panel.sel_bag == 1


def test_tab_switch_resets_shelf_scroll():
    """切换页签后货架回到第一件。"""
    panel, player, combat = _make_panel()
    register_lua_shop(_NPC, ["wheelshop", "wheelshop2"])
    register_shop_profile("wheelshop2", "杂货2", [("02999999", 10)])
    panel.open(_NPC)
    panel.draw(_VIEW, player, combat)
    lx = panel.rect.x + BG_LCOL_X + BG_LCOL_W // 2
    _wheel_and_click(panel, player, combat, lx, _first_row_y(panel), [1] * 3)
    panel.handle_click((panel.rect.x + 90, panel.rect.y + 37), player, combat)
    panel.draw(_VIEW, player, combat)
    panel.handle_click((lx, _first_row_y(panel)), player, combat)
    assert panel.sel_shelf == 0
