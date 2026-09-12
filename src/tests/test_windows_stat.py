"""StatWindow 行为：关闭钮 / 加点热区 / 一键分配 / 窗口内消费（素材缺失 fallback 路径）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

from game.core.jobs import JOBS
from game.render.windows.stat import DETAIL_ROWS, StatWindow
from tests.windows_harness import (draw_once, make_manager, make_services,
                                   press, release)


# ── 测试数据助手 ───────────────────────────────────────────────────
def _stat(total: int):
    """面板 getter 桩：无 buff 基础值比总值低 5，供详情行验证 buff 后缀。"""
    return lambda with_buffs=True: total if with_buffs else total - 5


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
        attack_value=_stat(120), defense_value=_stat(45),
        magic_attack_value=_stat(88), magic_defense_value=_stat(30),
        accuracy_value=_stat(95), evasion_value=_stat(12),
        attack_speed_value=lambda: 4,
        move_speed_display=_stat(100),
        jump_power_display=_stat(100),
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


def test_escape_closes_stat_window():
    """官方底板窗无自绘 CLOSE：Esc 经 manager 逐层关窗。"""
    win, mgr = open_stat(make_player())
    assert mgr.handle_escape()
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
    assert mgr.last_toast() is not None and mgr.last_toast() == "没有可分配的属性点"


def test_positive_ap_clicks_each_stat_row():
    """ap>0 依次点四行「+」→ allocate_ap 按 str/dex/int/luk 各自属性被调用且无提示。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    assert len(win._ap_rects) == 4
    for rect, st in win._ap_rects:
        assert press(mgr, rect.center)
        release(mgr, rect.center)
    assert player.calls == ["str", "dex", "int", "luk"]
    assert mgr.last_toast() is None


def test_auto_button_triggers_auto_allocate():
    """一键分配命中 → auto_allocate_ap 被调用，成功时无提示。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    assert win._auto_rect is not None
    assert press(mgr, win._auto_rect.center)
    release(mgr, win._auto_rect.center)
    assert player.calls == ["auto"]
    assert mgr.last_toast() is None


def test_auto_button_without_ap_flashes_no_point_message():
    """ap=0 点一键分配失败 → 同样 flash「没有可分配的属性点」。"""
    player = make_player(ap=0, auto_ok=False)
    win, mgr = open_stat(player)
    assert press(mgr, win._auto_rect.center)
    assert player.calls == ["auto"]
    assert mgr.last_toast() == "没有可分配的属性点"


def test_detail_button_toggles_popup_open_close():
    """点 BtDetail 打开「詳細說明」，再点关闭；默认关闭。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    assert not win._detail
    assert win._detail_rect is not None
    assert press(mgr, win._detail_rect.center)
    assert win._detail
    assert press(mgr, win._detail_rect.center)
    assert not win._detail


def test_detail_popup_reads_all_nine_rows():
    """详情弹窗打开时逐行读取九项数值；buff 行额外读取不含 buff 的基础值。"""
    seen: List[tuple] = []
    player = make_player(ap=8)
    for _key, _label, getter, _aware in DETAIL_ROWS:
        def probe(with_buffs=True, g=getter):
            seen.append((g, with_buffs))
            return 1
        setattr(player, getter, probe)
    win, mgr = open_stat(player)
    assert seen == []                       # 关闭时不读战斗数值
    press(mgr, win._detail_rect.center)     # 打开详情
    draw_once(mgr)                          # 重建热区并绘制弹窗
    expected: List[tuple] = []
    for _key, _label, getter, aware in DETAIL_ROWS:
        expected.append((getter, True))
        if aware:
            expected.append((getter, False))
    assert seen == expected


def test_detail_popup_click_consumed_without_action():
    """点击已打开的详情弹窗被消费，不触发加点、不穿透。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    press(mgr, win._detail_rect.center)
    draw_once(mgr)
    assert win._detail_popup_rect is not None
    assert press(mgr, win._detail_popup_rect.center)
    assert player.calls == []
    assert win._detail


def test_click_inside_window_consumed_without_side_effects():
    """点击窗口内空白处被消费（防穿透），不触发任何加点。"""
    player = make_player(ap=8)
    win, mgr = open_stat(player)
    pos = (win.rect.x + 8, win.rect.y + win.rect.height // 2)
    assert press(mgr, pos)
    assert player.calls == []
