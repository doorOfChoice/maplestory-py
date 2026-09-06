"""全局模态框生命周期：确认 / 取消 / Esc / Enter 都必须收起弹框。

seam：WindowManager.request_modal + dispatch/dispatch_key/handle_escape；
验证「点放弃后弹框还在」这类卡模态的回归。
"""

from __future__ import annotations

import pygame

from game.render.windows.core.dialogs import Modal
from tests.windows_harness import (BoxWindow, draw_once, key_press,
                                   make_manager, make_services, press)


def _modal(mgr, **kw):
    received = []
    m = Modal(on_ok=received.append, **kw)
    mgr.request_modal(m)
    draw_once(mgr)          # 绘制一帧以登记按钮热区
    return m, received


def test_confirm_button_closes_modal():
    mgr = make_manager()
    m, got = _modal(mgr)
    assert mgr.modal_open()
    press(mgr, m.ok_rect.center)
    assert got == [None]
    assert not mgr.modal_open()


def test_cancel_button_closes_modal():
    mgr = make_manager()
    m, got = _modal(mgr)
    press(mgr, m.cancel_rect.center)
    assert got == []
    assert not mgr.modal_open()


def test_enter_confirms_and_closes():
    mgr = make_manager()
    m, got = _modal(mgr)
    assert key_press(mgr, pygame.K_RETURN)
    assert got == [None]
    assert not mgr.modal_open()


def test_escape_cancels_and_closes():
    mgr = make_manager()
    m, got = _modal(mgr)
    assert mgr.handle_escape()
    assert got == []
    assert not mgr.modal_open()


def test_numeric_modal_clamps_quantity():
    mgr = make_manager()
    m, got = _modal(mgr, numeric=True, max_value=50)
    assert got == []
    assert m.text == "50"
    for ch in "123":
        key_press(mgr, getattr(pygame, f"K_{ch}"))
    key_press(mgr, pygame.K_RETURN)
    assert got == [50]              # 录入 123 超上限：钳到 max_value
    assert not mgr.modal_open()


def test_modal_draws_above_panels_rendered_after_manager():
    """对话气泡在 windows.draw 之后绘制也不能盖住模态框（draw_modal 顶层通道）。"""
    mgr = make_manager()
    m, _ = _modal(mgr)
    surface = pygame.Surface((800, 600), pygame.SRCALPHA)
    mgr.draw(surface)
    surface.fill((1, 2, 3, 255), m.ok_rect)   # 模拟后画的对话层糊在上面
    mgr.draw_modal(surface)
    assert surface.get_at(m.ok_rect.center) != (1, 2, 3, 255)


def test_events_swallowed_while_modal_open():
    win = BoxWindow(make_services())
    win.open()
    mgr = make_manager(win)
    _modal(mgr)
    assert win.clicked == []
    press(mgr, win.rect.center)          # 模态期间点窗口不生效
    assert win.clicked == []
