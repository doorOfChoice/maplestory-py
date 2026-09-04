"""StatWindow 行为：关闭钮 / 加点热区 / 一键分配 / 窗口内消费（素材缺失 fallback 路径）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

from game.core.jobs import JOBS
from game.render.windows.stat import StatWindow
from tests.windows_harness import (close_button_pos, draw_once, make_manager,
                                   make_services, press, release)


# ── 测试数据助手 ───────────────────────────────────────────────────
def make_player(ap: int = 0, alloc_ok: bool = True, auto_ok: bool = True):
    """假玩家：allocate_ap / auto_allocate_ap 记录调用并可控返回值。"""
    calls: List[str] = []

    def allocate_ap(stat: str) -> bool:
        calls.append(stat)
        return alloc_ok

    def auto_allocate_ap() -> bool:
        calls.append("auto")
        return auto_ok

    return SimpleNamespace(
        ap=ap, level=12, hp=77.5, max_hp=120, mp=31.25, max_mp=60,
        exp=1234, exp_to_next=lambda: 4321,
        total_stats=lambda: {"str": 25, "dex": 20, "int": 4, "luk": 6},
        inventory=SimpleNamespace(bonus=lambda st: 3 if st == "str" else 0),
        job=next(iter(JOBS)),
        allocate_ap=allocate_ap,
        auto_allocate_ap=auto_allocate_ap,
        calls=calls,
    )


def open_stat(player) -> tuple:
    """装配一个可见的 StatWindow 并绘制一帧（重建加点热区）。"""
    win = StatWindow(make_services(player))
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    return win, mgr


# ── 开合与 chrome ──────────────────────────────────────────────────
def test_default_invisible_and_toggle_shows():
    """默认不可见，由外部 toggle 打开。"""
    win = StatWindow(make_services(make_player()))
    assert not win.visible
    win.toggle()
    assert win.visible


def test_close_button_click_closes_stat_window():
    """有 chrome：draw 后点关闭钮即关窗（经 manager 全链路）。"""
    win, mgr = open_stat(make_player())
    assert win.close_rect is not None
    assert press(mgr, close_button_pos(win))
    assert not win.visible


# ── 加点行为 ───────────────────────────────────────────────────────
def test_zero_ap_plus_click_flashes_no_point_message():
    """ap=0 点「+」→ allocate 失败回传 → flash「没有可分配的属性点」。"""
    player = make_player(ap=0, alloc_ok=False)
    win, mgr = open_stat(player)
    rect, st = win._ap_rects[0]
    assert press(mgr, rect.center)
    release(mgr, rect.center)
    assert player.calls == [st]
    assert mgr._toast is not None and mgr._toast[0] == "没有可分配的属性点"


def test_positive_ap_clicks_each_stat_row():
    """ap>0 依次点四行「+」→ allocate_ap 按 str/dex/int/luk 各自属性被调用且无提示。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    assert len(win._ap_rects) == 4
    for rect, st in win._ap_rects:
        assert press(mgr, rect.center)
        release(mgr, rect.center)
    assert player.calls == ["str", "dex", "int", "luk"]
    assert mgr._toast is None


def test_auto_button_triggers_auto_allocate():
    """一键分配命中 → auto_allocate_ap 被调用，成功时无提示。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    assert win._auto_rect is not None
    assert press(mgr, win._auto_rect.center)
    release(mgr, win._auto_rect.center)
    assert player.calls == ["auto"]
    assert mgr._toast is None


def test_auto_button_without_ap_flashes_no_point_message():
    """ap=0 点一键分配失败 → 同样 flash「没有可分配的属性点」。"""
    player = make_player(ap=0, auto_ok=False)
    win, mgr = open_stat(player)
    assert press(mgr, win._auto_rect.center)
    assert player.calls == ["auto"]
    assert mgr._toast[0] == "没有可分配的属性点"


def test_click_inside_window_consumed_without_side_effects():
    """点击窗口内空白处被消费（防穿透），不触发任何加点。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    pos = (win.rect.x + 8, win.rect.y + win.rect.height // 2)
    assert press(mgr, pos)
    assert player.calls == []
