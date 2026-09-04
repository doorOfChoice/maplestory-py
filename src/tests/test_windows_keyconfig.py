"""按键设置窗组件：点行录入、按键改绑落盘、Esc 取消/关窗、右键重置、滚轮限幅。

透过 KeyConfigWindow + WindowManager 公开接口验证行为（不依赖 WZ 素材）。
行热区由 draw 登记（同 title_rect 契约），测试先 draw_once 再按 rows 命中。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pygame

from game.core.keybindings import KeyBindings
from game.render.windows.keyconfig import KC_ROW_H, KeyConfigWindow
from game.render.windows.core.services import WindowServices
from tests.windows_harness import (FakeAssets, FakeUI, draw_once, key_press,
                                   make_manager, press, wheel)


# ── 测试数据助手 ────────────────────────────────────────────────────
class FakeBindings:
    """记录改绑/重置/落盘调用的假绑定表；key_of 返回稳定键码供绘制。"""

    def __init__(self) -> None:
        self.set_calls: list = []
        self.reset_calls: list = []
        self.saved = 0

    def key_of(self, action: str) -> int:
        return pygame.K_a

    def set(self, action: str, key: int) -> bool:
        self.set_calls.append((action, key))
        return True

    def reset(self, action: str) -> None:
        self.reset_calls.append(action)

    def save(self) -> None:
        self.saved += 1


def make_window(bindings=None, player=None) -> KeyConfigWindow:
    svc = WindowServices(assets=FakeAssets(), ui=FakeUI(),
                         player=lambda: player, bindings=bindings)
    return KeyConfigWindow(svc)


def make_open(bindings=None, player=None) -> tuple:
    """开窗 + 装配 manager + 画一帧登记行热区。"""
    win = make_window(bindings, player)
    win.open()
    mgr = make_manager(win)
    draw_once(mgr)
    return win, mgr


def row_center(win: KeyConfigWindow, action: str) -> tuple:
    return next(rect.center for rect, a in win.rows if a == action)


def visible_actions(win: KeyConfigWindow) -> list:
    return [a for _, a in win.rows]


# ── 开合与重置 ──────────────────────────────────────────────────────
def test_toggle_flips_visibility():
    win = make_window(FakeBindings())
    assert not win.visible
    win.toggle()
    assert win.visible
    win.toggle()
    assert not win.visible


def test_reopen_resets_capture_and_scroll():
    """每次打开恢复干净状态：旧录入取消、滚动回顶。"""
    win, mgr = make_open(FakeBindings())
    press(mgr, row_center(win, "attack"))
    for _ in range(5):
        wheel(mgr, win.rect.center, up=False)
    assert mgr.handle_escape()
    win.open()
    draw_once(mgr)
    assert win.capturing_action is None
    assert "move_left" in visible_actions(win)


def test_close_during_capture_cancels_it():
    win, mgr = make_open(FakeBindings())
    press(mgr, row_center(win, "attack"))
    mgr.handle_escape()
    assert win.capturing_action is None


# ── 录入态 ─────────────────────────────────────────────────────────
def test_click_row_enters_capture_and_click_again_cancels():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    assert press(mgr, row_center(win, "attack"))
    assert win.capturing_action == "attack"
    assert fb.set_calls == []
    press(mgr, row_center(win, "attack"))
    assert win.capturing_action is None


def test_click_another_row_switches_capture_target():
    win, mgr = make_open(FakeBindings())
    press(mgr, row_center(win, "attack"))
    press(mgr, row_center(win, "pickup"))
    assert win.capturing_action == "pickup"


def test_captured_key_rebinds_and_saves_once():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    press(mgr, row_center(win, "attack"))
    assert key_press(mgr, pygame.K_j)
    assert fb.set_calls == [("attack", pygame.K_j)]
    assert fb.saved == 1
    assert win.capturing_action is None


def test_escape_in_capture_cancels_without_rebind_or_close():
    """录入态 Esc：dispatch_key 先消费 → 只取消录入，不改绑、不关窗。"""
    fb = FakeBindings()
    win, mgr = make_open(fb)
    press(mgr, row_center(win, "attack"))
    assert key_press(mgr, pygame.K_ESCAPE)
    assert fb.set_calls == []
    assert win.capturing_action is None
    assert win.visible


def test_escape_without_capture_closes_via_manager():
    win, mgr = make_open(FakeBindings())
    assert not key_press(mgr, pygame.K_ESCAPE)   # 未录入不消费，交给 Esc 链
    assert mgr.handle_escape()
    assert not win.visible


def test_key_not_consumed_when_not_capturing():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    assert not key_press(mgr, pygame.K_j)
    assert fb.set_calls == []


def test_header_row_is_not_capturable():
    """点分组标题行：事件被窗口吞掉，但不进入录入态。"""
    win, mgr = make_open(FakeBindings())
    band_y = win.rect.y + 26 + KC_ROW_H // 2     # 首条目 =〔移动〕标题行
    assert press(mgr, (win.rect.x + 100, band_y))
    assert win.capturing_action is None


# ── 右键重置 ────────────────────────────────────────────────────────
def test_right_click_row_resets_and_saves():
    fb = FakeBindings()
    win, mgr = make_open(fb)
    assert press(mgr, row_center(win, "attack"), button=3)
    assert fb.reset_calls == ["attack"]
    assert fb.saved == 1


def test_right_click_restores_chain_defaults_and_persists():
    """改绑互换后右键「普通攻击」→ 攻击与顶用的拾取链式归位并落盘。"""
    kb = KeyBindings()
    kb.set("attack", pygame.K_j)
    kb.set("pickup", pygame.K_a)
    with tempfile.TemporaryDirectory() as td:
        kb.path = Path(td) / "kb.json"
        win, mgr = make_open(kb)
        assert press(mgr, row_center(win, "attack"), button=3)
        assert kb.key_of("attack") == pygame.K_a
        assert kb.key_of("pickup") == pygame.K_z
        assert KeyBindings.load(kb.path).key_of("attack") == pygame.K_a


# ── 滚轮限幅 ────────────────────────────────────────────────────────
def test_wheel_scrolls_and_clamps():
    win, mgr = make_open(FakeBindings())
    for _ in range(40):
        assert wheel(mgr, win.rect.center, up=False)
    draw_once(mgr)
    actions = visible_actions(win)
    assert "move_left" not in actions and "skill_12" in actions
    for _ in range(40):
        wheel(mgr, win.rect.center, up=True)
    draw_once(mgr)
    assert "move_left" in visible_actions(win)


# ── 真绑定表全链路（吸收旧冲突互换 / 持久化 / 技能槽用例）──────────
def test_rebind_conflict_swaps_and_persists():
    kb = KeyBindings()
    with tempfile.TemporaryDirectory() as td:
        kb.path = Path(td) / "kb.json"
        win, mgr = make_open(kb)
        press(mgr, row_center(win, "attack"))
        assert key_press(mgr, pygame.K_z)        # 抢拾取键 → 互换
        assert kb.key_of("attack") == pygame.K_z
        assert kb.key_of("pickup") == pygame.K_a
        assert KeyBindings.load(kb.path).key_of("attack") == pygame.K_z


def test_skill_row_binds_custom_key():
    """技能 3 行录入 F7：数字 3 不再是技能 3。"""
    kb = KeyBindings()
    win, mgr = make_open(kb)
    for _ in range(20):                     # 技能 3 不在首屏，先滚过去
        wheel(mgr, win.rect.center, up=False)
    draw_once(mgr)
    press(mgr, row_center(win, "skill_3"))
    assert key_press(mgr, pygame.K_F7)
    assert kb.skill_slot_for(pygame.K_F7) == 3
    assert kb.skill_slot_for(pygame.K_3) is None


def test_skill_row_label_includes_bound_skill_name():
    """skill_N 行标签拼上槽位当前技能名。"""
    player = SimpleNamespace(skills=SimpleNamespace(
        hotkeys={3: "9311005"},
        defs={"9311005": SimpleNamespace(name="断魂箭")}))
    win = make_window(FakeBindings(), player)
    assert win.row_label("skill_3") == "技能 3 · 断魂箭"
    assert win.row_label("attack") == "普通攻击"
