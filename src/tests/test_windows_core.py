"""WindowManager 基座行为：chrome / z 序 / 事件分发 / 坐标缩放 / 拖扔与双击。"""

from __future__ import annotations

import pygame

from game import settings
from game.systems.inventory import Item
from game.render.windows.core import widgets
from game.render.windows.core.manager import to_view_pos
from game.render.windows.core.window import Window
from tests.windows_harness import (BoxWindow, close_button_pos, draw_once,
                                   key_press, make_manager, make_services,
                                   motion, press, release, wheel)


# ── 开关与 chrome ──────────────────────────────────────────────────
def test_toggle_flips_visibility():
    win = BoxWindow(make_services())
    assert not win.visible
    win.toggle()
    assert win.visible
    win.toggle()
    assert not win.visible


def test_close_button_consumes_and_closes_only_its_window():
    a, b = BoxWindow(make_services(), key="a", at=(10, 10)), \
        BoxWindow(make_services(), key="b", at=(300, 10))
    a.visible = b.visible = True
    mgr = make_manager(a, b)
    draw_once(mgr)
    assert press(mgr, close_button_pos(a))
    release(mgr, close_button_pos(a))
    assert not a.visible and b.visible


def test_drag_title_moves_window_and_clamps_to_view():
    win = BoxWindow(make_services(), at=(10, 10))
    win.visible = True
    mgr = make_manager(win)
    draw_once(mgr)
    assert press(mgr, (win.title_rect.centerx, win.title_rect.centery))
    motion(mgr, (210, 110))
    release(mgr, (210, 110))
    assert win.rect.topleft == (210 - 50, 110 - 10)   # 跟随抓取点偏移
    # 拖出画面外 → 限幅在视口内
    press(mgr, win.title_rect.center)
    motion(mgr, (settings.VIEW_W + 500, -500))
    release(mgr, (settings.VIEW_W + 500, -500))
    draw_once(mgr)
    assert win.rect.right <= settings.VIEW_W and win.rect.top >= 0


# ── 命中与 z 序 ────────────────────────────────────────────────────
def test_overlapping_topmost_window_exclusively_gets_click():
    low = BoxWindow(make_services(), key="low", at=(10, 10), size=(120, 80))
    high = BoxWindow(make_services(), key="high", at=(40, 30), size=(120, 80))
    low.visible = high.visible = True
    low.buttons = [(pygame.Rect(40, 40, 60, 40), "low_btn")]
    high.buttons = [(pygame.Rect(40, 40, 60, 40), "high_btn")]
    mgr = make_manager(low, high)
    draw_once(mgr)
    assert press(mgr, (60, 60))
    assert high.clicked == ["high_btn"] and low.clicked == []


def test_click_brings_window_to_top():
    low = BoxWindow(make_services(), key="low", at=(10, 10), size=(120, 80))
    high = BoxWindow(make_services(), key="high", at=(40, 30), size=(120, 80))
    low.visible = high.visible = True
    mgr = make_manager(low, high)
    draw_once(mgr)
    press(mgr, (20, 20))     # 只碰到低窗口的区域
    assert mgr.windows[-1] is low


def test_wheel_only_reaches_hit_window():
    a = BoxWindow(make_services(), key="a", at=(10, 10))
    b = BoxWindow(make_services(), key="b", at=(300, 10))
    a.visible = b.visible = True
    mgr = make_manager(a, b)
    draw_once(mgr)
    assert wheel(mgr, (320, 30), up=True)
    assert wheel(mgr, (600, 500), up=True) is False   # 空白处穿透
    assert a.wheeled == [] and b.wheeled == [-1]


def test_click_on_empty_area_is_not_consumed():
    win = BoxWindow(make_services())
    win.visible = True
    mgr = make_manager(win)
    draw_once(mgr)
    assert not press(mgr, (700, 500))


# ── 键盘与 Esc ─────────────────────────────────────────────────────
def test_dispatch_key_goes_to_visible_windows_top_down():
    plain = BoxWindow(make_services(), key="plain")
    typer = BoxWindow(make_services(), key="typer", at=(200, 0))
    typer.visible = True
    mgr = make_manager(plain, typer)
    assert key_press(mgr, pygame.K_5)
    assert typer.keys_seen == [pygame.K_5] and plain.keys_seen == []


def test_escape_closes_topmost_only_if_flagged():
    inv = BoxWindow(make_services(), key="inv", at=(10, 10))
    kc = BoxWindow(make_services(), key="kc", at=(300, 10))
    kc.escape_closes = True
    inv.visible = kc.visible = True
    mgr = make_manager(inv, kc)
    assert mgr.handle_escape()
    assert kc.visible is False and inv.visible is True
    assert not mgr.handle_escape()      # 无可关窗口 → 不消费


# ── 物品拖拽 / 双击 / 扔出 ─────────────────────────────────────────
def _item() -> Item:
    return Item(id="2000000", name="红药", count=12, kind="consume",
                info={"spec": {"hp": 50}})


def test_double_click_on_pickup_activates_window():
    win = BoxWindow(make_services())
    win.visible = True
    win.drag = (("cell", "consume", 0), _item())
    taken: list = []
    win.activate = lambda pk: taken.append(pk.source)
    mgr = make_manager(win)
    draw_once(mgr)
    press(mgr, (50, 40))
    release(mgr, (50, 40))
    press(mgr, (50, 40))
    release(mgr, (50, 40))
    assert taken == [("cell", "consume", 0)]


def test_drag_out_of_home_takes_item_for_drop():
    win = BoxWindow(make_services())
    win.visible = True
    item = _item()
    win.drag = (("cell", "consume", 0), item)
    win.take_for_drop = lambda pk: item
    mgr = make_manager(win)
    draw_once(mgr)
    press(mgr, (50, 40))
    motion(mgr, (500, 400))     # 超过拖拽阈值 → 激活
    release(mgr, (500, 400))
    assert mgr.take_dropped() is item
    assert mgr.take_dropped() is None   # 一次取走


def test_drag_back_into_home_cancels_drop():
    win = BoxWindow(make_services())
    win.visible = True
    item = _item()
    win.drag = (("cell", "consume", 0), item)
    win.take_for_drop = lambda pk: item
    mgr = make_manager(win)
    draw_once(mgr)
    press(mgr, (50, 40))
    motion(mgr, (500, 400))
    release(mgr, (50, 40))      # 放回来源窗口
    assert mgr.take_dropped() is None


def test_release_without_motion_is_not_drop_and_not_activate():
    """单击（非双击/非拖拽）：既不激活也不扔。"""
    win = BoxWindow(make_services())
    win.visible = True
    win.drag = (("cell", "consume", 0), _item())
    acted: list = []
    win.activate = lambda pk: acted.append(1)
    win.take_for_drop = lambda pk: pytest_fail("不应取出")
    mgr = make_manager(win)
    draw_once(mgr)
    press(mgr, (50, 40))
    release(mgr, (50, 40))
    assert acted == []


def pytest_fail(msg: str):
    raise AssertionError(msg)


# ── 坐标缩放 ───────────────────────────────────────────────────────
def test_to_view_pos_identity_at_scale_one():
    assert to_view_pos((123, 45)) == (123, 45)


# ── toast / tooltip 服务 ───────────────────────────────────────────
def test_tooltip_long_desc_wraps_within_max_width():
    svc = make_services()

    class TipWindow(Window):
        def draw(self, surface):
            self.svc.tooltip("药水\n" + "红色药草研磨作成的药水，恢复HP约50" * 8)

    win = TipWindow(svc)
    win.visible = True
    mgr = make_manager(win)
    surface = draw_once(mgr)
    area = surface.get_bounding_rect()
    assert area.width <= widgets.TOOLTIP_MAX_W   # 超宽被折行压住
    assert area.height > 3 * 16                  # 正文换成了多行


def test_flash_is_rendered_frame_and_decays():
    mgr = make_manager()
    mgr.flash("背包已满")
    draw_once(mgr)              # 有 toast 时绘制不抛错
    for _ in range(200):        # 衰减结束后清空
        draw_once(mgr)
    assert mgr._toast is None



