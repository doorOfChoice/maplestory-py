"""商店 / 仓库窗口行为：两栏滚动、买卖结算、仓库存取、Esc 与拖条（manager 全链路）。"""

from __future__ import annotations

import types

import pygame

from game import settings
from game.render.windows.shop import (BG_LCOL_W, BG_LCOL_X, BG_NROWS,
                                      BG_ROW_H, BG_ROW_Y0, ShopWindow)
from game.render.windows.storage import CELL, STORAGE_COLS, StorageWindow
from game.render.windows.core.services import WindowServices
from game.systems.inventory import Inventory, Item
from game.systems.shop import register_lua_shop, register_shop_profile
from tests.windows_harness import (FakeUI, draw_once, key_press, make_manager,
                                   motion, press, release, wheel)

pygame.init()

_NPC = "8800002"
_N_SHELF = 8
_N_BAG = 8


class _FakeAssets:
    """仅提供 Shop/backgrnd 合成底图，其余素材 None（fallback 绘制可切换）。"""

    def ui_surface(self, img: str, path: str):
        if path == "Shop/backgrnd":
            return [pygame.Surface((463, 339), pygame.SRCALPHA)]
        return None

    def item_name(self, item_id: str) -> str:
        return f"物品{item_id[-2:]}"

    def item_icon(self, item_id: str):
        return None

    def equip_icon(self, item_id: str):
        return None

    def item_price(self, item_id: str):
        return None

    def consume_info(self, item_id: str):
        return {}

    def equip_info(self, item_id: str):
        return None


def _shop_player() -> types.SimpleNamespace:
    inv = Inventory()
    for i in range(_N_BAG):
        inv.consumes[f"028{i:05d}"] = Item(id=f"028{i:05d}", name=f"背包{i}",
                                           kind="consume", count=1)
    return types.SimpleNamespace(inventory=inv)


def _shop_window(meso: int = 10000):
    """打开官方布局商店：注册合成店铺 + player / combat 接线 services。"""
    shelf = [(f"029{i:05d}", 100 + i) for i in range(_N_SHELF)]
    # 背包前两件也在价目表里：出售测试可拿到非零卖价
    shelf += [("02800000", 400), ("02800001", 400)]
    register_lua_shop(_NPC, ["wheelshop"])
    register_shop_profile("wheelshop", "杂货", shelf)
    player = _shop_player()
    combat = types.SimpleNamespace(meso=meso)
    svc = WindowServices(assets=_FakeAssets(), ui=FakeUI(),
                         player=lambda: player, combat=combat)
    win = ShopWindow(svc)
    win.open(_NPC)
    mgr = make_manager(win)
    draw_once(mgr)
    return win, mgr, player, combat


def _first_row_y(win: ShopWindow) -> int:
    return win.rect.y + BG_ROW_Y0 + BG_ROW_H // 2


def _shelf_x(win: ShopWindow) -> int:
    return win.rect.x + BG_LCOL_X + BG_LCOL_W // 2


def _bag_x(win: ShopWindow) -> int:
    return win.rect.x + 260 + BG_LCOL_W // 2


def _click(mgr, pos):
    press(mgr, pos)
    release(mgr, pos)


# ── 商店：滚动 ─────────────────────────────────────────────────────
def test_shop_shelf_wheel_scrolls_shelf_only():
    """光标左半滚一格：货架首行变为第 2 件，背包栏不动。"""
    win, mgr, _player, _combat = _shop_window()
    assert wheel(mgr, (_shelf_x(win), _first_row_y(win)), up=False)
    draw_once(mgr)
    assert win.shelf_rects[0][1] == 1
    assert win.bag_rects[0][1] == 0


def test_shop_wheel_clamps_at_end():
    win, mgr, _player, _combat = _shop_window()
    for _ in range(20):
        wheel(mgr, (_shelf_x(win), _first_row_y(win)), up=False)
    assert win._scroll_shelf == len(win._shelf_items()) - BG_NROWS


# ── 商店：买卖结算 ─────────────────────────────────────────────────
def test_shop_select_row_then_buy_adds_item_and_charges():
    win, mgr, player, combat = _shop_window()
    _click(mgr, (_shelf_x(win), _first_row_y(win)))
    draw_once(mgr)
    assert win.sel_shelf == 0
    _click(mgr, win.buy_rect.center)
    _type_digits(mgr, "1")
    assert key_press(mgr, pygame.K_RETURN)
    assert combat.meso < 10000
    assert any(it.name for it in player.inventory.consumes.values())
    assert mgr._toast is not None and mgr._toast[0].startswith("购入")


def test_shop_buy_without_selection_flashes_hint():
    win, mgr, _player, _combat = _shop_window()
    _click(mgr, win.buy_rect.center)
    assert mgr._toast[0] == "请先点选要购买的物品"


def test_shop_sell_selected_bag_stack_credits_meso():
    win, mgr, player, combat = _shop_window()
    rect, idx = win.bag_rects[0]
    sold_id = win._bag_entries(player)[idx][1].id
    _click(mgr, rect.center)
    assert win.sel_bag == 0
    _click(mgr, win.sell_rect.center)
    _type_digits(mgr, "1")
    assert key_press(mgr, pygame.K_RETURN)
    assert combat.meso > 10000
    assert sold_id not in player.inventory.consumes
    assert mgr._toast[0].startswith("卖出")


# ── 商店：数量输入框（原版弹框买卖）────────────────────────────────
def _type_digits(mgr, digits: str) -> None:
    for ch in digits:
        assert key_press(mgr, getattr(pygame, f"K_{ch}"))


def test_shop_buy_consumable_opens_dialog_then_confirms():
    """买消耗品：点「购买」弹数量框 → 输 3 确认 → 扣 3 倍单价、入包堆 3。"""
    win, mgr, player, combat = _shop_window()
    _click(mgr, (_shelf_x(win), _first_row_y(win)))     # 02900000 · 100 金币
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    assert win.qty_mode == "buy"
    draw_once(mgr)                                      # 弹框登记热区
    _type_digits(mgr, "3")
    assert win.qty_text == "3"
    _click(mgr, win.qty_ok_rect.center)
    assert combat.meso == 10000 - 300
    assert player.inventory.consumes["02900000"].count == 3
    assert win.qty_mode is None


def test_shop_buy_dialog_cancel_keeps_everything():
    """数量框点「取消」：关闭弹框、不成交、金币背包不动。"""
    win, mgr, player, combat = _shop_window()
    _click(mgr, (_shelf_x(win), _first_row_y(win)))
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    draw_once(mgr)
    _type_digits(mgr, "5")
    _click(mgr, win.qty_cancel_rect.center)
    assert win.qty_mode is None
    assert combat.meso == 10000
    assert "02900000" not in player.inventory.consumes


def test_shop_buy_dialog_esc_and_backspace():
    """数量框吃 Esc 收起（不关商店窗）；退格删一位数字。"""
    win, mgr, _player, combat = _shop_window()
    _click(mgr, (_shelf_x(win), _first_row_y(win)))
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    assert win.visible
    _type_digits(mgr, "12")
    assert key_press(mgr, pygame.K_BACKSPACE)
    assert win.qty_text == "1"
    assert key_press(mgr, pygame.K_ESCAPE)
    assert win.qty_mode is None
    assert win.visible
    assert combat.meso == 10000


def test_shop_buy_dialog_enter_confirms():
    """弹框内按回车等同点「确认」。"""
    win, mgr, player, combat = _shop_window()
    _click(mgr, (_shelf_x(win), _first_row_y(win)))
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    _type_digits(mgr, "2")
    assert key_press(mgr, pygame.K_RETURN)
    assert player.inventory.consumes["02900000"].count == 2
    assert combat.meso == 10000 - 200


def test_shop_buy_dialog_empty_or_zero_rejected():
    """空 / 0 确认：提示输入数量、弹框不关、不成交。"""
    win, mgr, _player, combat = _shop_window()
    _click(mgr, (_shelf_x(win), _first_row_y(win)))
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    draw_once(mgr)
    _click(mgr, win.qty_ok_rect.center)
    assert win.qty_mode == "buy"
    assert combat.meso == 10000


def test_shop_buy_unaffordable_quantity_fails_with_flash():
    """输入数量超出承受：确认失败提示、弹框收起、分文不动。"""
    win, mgr, _player, combat = _shop_window(meso=250)
    _click(mgr, (_shelf_x(win), _first_row_y(win)))     # 单价 100
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    _type_digits(mgr, "99")
    assert key_press(mgr, pygame.K_RETURN)
    assert combat.meso == 250
    assert win.qty_mode is None
    assert mgr._toast is not None


def test_shop_sell_dialog_prefills_owned_count():
    """出售弹框默认预填拥有数量：打开即 qty_text=存量，直接 Enter 整堆卖光。"""
    from game.systems import shop as shop_mod
    win, mgr, player, combat = _shop_window()
    player.inventory.consumes["02800000"].count = 5
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    draw_once(mgr)
    _click(mgr, win.sell_rect.center)
    assert win.qty_text == "5"
    assert key_press(mgr, pygame.K_RETURN)
    assert "02800000" not in player.inventory.consumes
    assert combat.meso == 10000 + 5 * shop_mod.sell_price(400)


def test_shop_sell_dialog_first_digit_replaces_default():
    """预填后首个数字键替换默认值（改数量不必先退格），其后继续追加。"""
    win, mgr, player, _combat = _shop_window()
    player.inventory.consumes["02800000"].count = 12
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    draw_once(mgr)
    _click(mgr, win.sell_rect.center)
    assert win.qty_text == "12"
    _type_digits(mgr, "3")
    assert win.qty_text == "3"
    _type_digits(mgr, "5")
    assert win.qty_text == "35"


def test_shop_delete_key_sells_selected_stack():
    """背包堆选中后按 Delete（Mac 为退格键）等同点「出售」：弹数量框并预填拥有量。"""
    win, mgr, player, _combat = _shop_window()
    player.inventory.consumes["02800000"].count = 4
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    assert key_press(mgr, pygame.K_BACKSPACE)
    assert win.qty_mode == "sell"
    assert win.qty_text == "4"
    assert key_press(mgr, pygame.K_DELETE)
    assert win.qty_mode == "sell"


def test_shop_delete_key_sells_equip_immediately():
    """散件装备选中后按 Delete：整件直接卖出，不弹数量框。"""
    win, mgr, player, combat = _shop_window()
    register_shop_profile("wheelshop", "杂货",
                          [("01452000", 5000)] + [(i, 100)
                                                  for i in win._shelf_items()[1:]])
    player.inventory.consumes.clear()
    player.inventory.equips.append(Item(id="01452000", name="铁剑",
                                        count=1, kind="equip"))
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    assert key_press(mgr, pygame.K_DELETE)
    assert win.qty_mode is None
    assert player.inventory.equips == []
    assert combat.meso == 10000 + 2500


def test_shop_delete_without_selection_not_consumed():
    """未选中任何背包行时 Delete 不被商店吃掉（留给全局按键）。"""
    win, mgr, _player, _combat = _shop_window()
    assert not win.handle_keydown(pygame.K_DELETE)


def test_shop_sell_stack_opens_dialog_partial_sell():
    """卖消耗品堆：点「出售」弹数量框 → 输 2 → 卖半堆留 3、金币按 2 件计。"""
    from game.systems import shop as shop_mod
    win, mgr, player, combat = _shop_window()
    it = player.inventory.consumes["02800000"]
    it.count = 5
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    draw_once(mgr)
    _click(mgr, win.sell_rect.center)
    assert win.qty_mode == "sell"
    _type_digits(mgr, "2")
    assert key_press(mgr, pygame.K_RETURN)
    unit = shop_mod.sell_price(400)
    assert it.count == 3
    assert combat.meso == 10000 + 2 * unit


def test_shop_sell_dialog_clamps_to_stack_count():
    """卖出数量大于堆存量：按整堆封顶全卖光。"""
    from game.systems import shop as shop_mod
    win, mgr, player, combat = _shop_window()
    player.inventory.consumes["02800000"].count = 5
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    draw_once(mgr)
    _click(mgr, win.sell_rect.center)
    _type_digits(mgr, "99")
    assert key_press(mgr, pygame.K_RETURN)
    assert "02800000" not in player.inventory.consumes
    assert combat.meso == 10000 + 5 * shop_mod.sell_price(400)


def test_shop_double_click_shelf_stack_opens_buy_dialog():
    """双击货架消耗品行：直接弹购买数量框（免点「购买」）。"""
    win, mgr, _player, _combat = _shop_window()
    pos = (_shelf_x(win), _first_row_y(win))
    _click(mgr, pos)
    assert win.qty_mode is None                # 单击只选中
    _click(mgr, pos)
    assert win.qty_mode == "buy"


def test_shop_double_click_bag_stack_opens_sell_dialog():
    """双击背包消耗品行：直接弹出售数量框。"""
    win, mgr, player, _combat = _shop_window()
    rect = win.bag_rects[0][0]
    _click(mgr, rect.center)
    assert win.qty_mode is None
    _click(mgr, rect.center)
    assert win.qty_mode == "sell"


def test_shop_double_click_equip_row_no_dialog():
    """双击装备行不弹数量框（装备走单击 +「购买」直接成交）。"""
    from game.systems.shop import register_shop_profile
    win, mgr, _player, _combat = _shop_window()
    register_shop_profile("wheelshop", "杂货",
                          [("01452000", 5000)] + [(i, 100) for i in win._shelf_items()[1:]])
    win.sel_shelf = None
    draw_once(mgr)
    pos = win.shelf_rects[0][0].center
    _click(mgr, pos)
    _click(mgr, pos)
    assert win.qty_mode is None
    assert win.sel_shelf == 0


def test_shop_slow_reclick_is_not_double_click():
    """超过双击间隔的再点只重新选中，不弹框。"""
    import time
    win, mgr, _player, _combat = _shop_window()
    pos = (_shelf_x(win), _first_row_y(win))
    _click(mgr, pos)
    time.sleep(0.4)
    _click(mgr, pos)
    assert win.qty_mode is None


def test_shop_buy_equip_skips_dialog():
    """装备不可堆叠：点购买直接按 1 件成交，不弹数量框。"""
    from game.systems.shop import register_shop_profile
    win, mgr, player, combat = _shop_window()
    register_shop_profile("wheelshop", "杂货",
                          [("01452000", 5000)] + [(i, 100) for i in win._shelf_items()[1:]])
    win.sel_shelf = None
    draw_once(mgr)
    _click(mgr, win.shelf_rects[0][0].center)
    draw_once(mgr)
    _click(mgr, win.buy_rect.center)
    assert win.qty_mode is None
    assert combat.meso == 10000 - 5000
    assert len(player.inventory.equips) == 1


# ── 商店：关闭路径 ─────────────────────────────────────────────────
def test_shop_escape_and_close_button():
    win, mgr, _player, _combat = _shop_window()
    assert mgr.handle_escape() and not win.visible
    win.open(_NPC)
    draw_once(mgr)
    _click(mgr, win.close_rect.center)
    assert not win.visible


def test_shop_thumb_drag_scrolls():
    """按住拇指拖动：滚动跟随（motion 经基类 handle_mouse_motion 钩子）。"""
    win, mgr, _player, _combat = _shop_window()
    thumb = win._shelf_bar_thumb
    assert thumb.width > 0, "货架内容不足，拇指未生成"
    press(mgr, thumb.center)
    motion_pos = (thumb.centerx, thumb.y + thumb.height + 60)
    motion(mgr, motion_pos)
    release(mgr, motion_pos)
    assert win._scroll_shelf > 0
    assert win._drag_bar is None


# ── 仓库 ───────────────────────────────────────────────────────────
def _storage_window(n_bag: int = 3):
    inv = Inventory()
    for i in range(n_bag):
        inv.add(Item(id=f"20000{i:03d}", name=f"道具{i}", kind="consume",
                     count=1))
    player = types.SimpleNamespace(inventory=inv)
    svc = WindowServices(assets=_FakeAssets(), ui=FakeUI(),
                         player=lambda: player)
    win = StorageWindow(svc)
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    return win, mgr, player


def test_storage_click_bag_row_stores_item():
    win, mgr, player = _storage_window()
    rect, idx = win.bag_rects[0]
    _click(mgr, rect.center)
    assert len(player.inventory.storage) == 1
    assert len(player.inventory.consumes) == 2


def test_storage_click_grid_row_takes_back():
    win, mgr, player = _storage_window()
    _click(mgr, win.bag_rects[0][0].center)
    draw_once(mgr)
    grid_rect, gidx = win.storage_rects[0]
    _click(mgr, grid_rect.center)
    assert player.inventory.storage == []
    assert gidx == 0


def test_storage_full_rejects_with_flash():
    win, mgr, player = _storage_window(n_bag=1)
    player.inventory.storage = [Item(id="999", name="满", kind="etc", count=1)
                                for _ in range(settings.STORAGE_CAP)]
    draw_once(mgr)
    _click(mgr, win.bag_rects[0][0].center)
    assert mgr._toast[0] == "仓库已满"
    assert len(player.inventory.consumes) == 1     # 存入失败须回滚


def test_storage_wheel_scrolls_and_clamps():
    win, mgr, _player = _storage_window(n_bag=40)
    pos = (win.rect.x + STORAGE_COLS * CELL + 60,
           win.rect.y + 100)
    for _ in range(5):
        wheel(mgr, pos, up=False)
    draw_once(mgr)
    assert win.bag_rects[0][1] == min(5, 40 - len(win.bag_rects))
