"""按键设置窗：点行进入录入、按键改绑（冲突互换）、Esc 取消、右键恢复默认。

透过 Panels 公开接口验证行为（不依赖 WZ 素材，_kc_rows 模拟绘制登记的行热区）。
"""

import tempfile
from pathlib import Path

import pygame

from game.core.keybindings import KeyBindings
from game.render.panels import Panels


class FakeUI:
    font = font_small = font_tiny = None


class FakeAssets:
    def ui_surface(self, img, path):
        return None


def _rows_at(pan: Panels, actions):
    """模拟窗口绘制登记：从 (10, 60) 起每行 18px 高。"""
    pan._kc_rect = pygame.Rect(4, 50, 240, 320)
    pan._kc_rows = [(pygame.Rect(10, 60 + 18 * i, 220, 18), a)
                    for i, a in enumerate(actions)]


def make():
    pygame.init()
    pan = Panels(FakeUI(), FakeAssets())
    kb = KeyBindings()
    with tempfile.TemporaryDirectory() as td:
        kb.path = Path(td) / "kb.json"
    pan.attach_bindings(kb)
    return pan, kb


def test_open_and_close():
    pan, _ = make()
    pan.toggle_keyconfig()
    assert pan.keyconfig_visible
    pan.toggle_keyconfig()
    assert not pan.keyconfig_visible


def test_click_row_enters_capture():
    """点击「普通攻击」行 → 进入录入态，其它键事件被窗口吞掉。"""
    pan, kb = make()
    pan.toggle_keyconfig()
    _rows_at(pan, ["attack", "pickup"])
    assert pan.handle_click((20, 62), None)
    assert pan.capturing_action == "attack"
    assert kb.key_of("attack") == pygame.K_a   # 尚未改绑


def test_captured_key_rebinds_and_persists():
    """录入态按 J → 攻击改绑 J 并写盘，退出录入态。"""
    pan, kb = make()
    pan.toggle_keyconfig()
    _rows_at(pan, ["attack"])
    pan.handle_click((20, 62), None)
    assert pan.consume_binding_key(pygame.K_j)
    assert kb.key_of("attack") == pygame.K_j
    assert pan.capturing_action is None
    assert KeyBindings.load(kb.path).key_of("attack") == pygame.K_j


def test_conflict_key_swaps():
    """录入态按 Z（拾取键）→ 攻击占 Z、拾取顶到 A。"""
    pan, kb = make()
    pan.toggle_keyconfig()
    _rows_at(pan, ["attack"])
    pan.handle_click((20, 62), None)
    pan.consume_binding_key(pygame.K_z)
    assert kb.key_of("attack") == pygame.K_z
    assert kb.key_of("pickup") == pygame.K_a


def test_escape_cancels_capture_without_rebinding():
    pan, kb = make()
    pan.toggle_keyconfig()
    _rows_at(pan, ["attack"])
    pan.handle_click((20, 62), None)
    assert pan.consume_binding_key(pygame.K_ESCAPE)
    assert pan.capturing_action is None
    assert kb.key_of("attack") == pygame.K_a


def test_consume_ignored_when_not_capturing():
    """开窗但未点行：按键归游戏逻辑处理，窗口不吞。"""
    pan, _ = make()
    pan.toggle_keyconfig()
    assert not pan.consume_binding_key(pygame.K_j)


def test_capture_survives_window_close_and_other_click():
    """关闭设置窗即取消录入；改点另一行则切换录入目标。"""
    pan, kb = make()
    pan.toggle_keyconfig()
    _rows_at(pan, ["attack", "pickup"])
    pan.handle_click((20, 62), None)
    pan.toggle_keyconfig()
    assert pan.capturing_action is None
    pan.toggle_keyconfig()
    pan.handle_click((20, 80), None)
    assert pan.capturing_action == "pickup"


def test_right_click_row_resets_to_default():
    """改绑后右键该行 → 恢复默认键并落盘。"""
    pan, kb = make()
    kb.set("attack", pygame.K_j)
    kb.set("pickup", pygame.K_a)
    pan.toggle_keyconfig()
    _rows_at(pan, ["attack"])
    pan.handle_right_click((20, 62), None)
    assert kb.key_of("attack") == pygame.K_a
    assert kb.key_of("pickup") == pygame.K_z
    assert KeyBindings.load(kb.path).key_of("attack") == pygame.K_a


def test_skill_row_binds_custom_key():
    """技能 3 行可录入 F7：数字 3 不再是技能 3。"""
    pan, kb = make()
    pan.toggle_keyconfig()
    _rows_at(pan, ["skill_3"])
    pan.handle_click((20, 62), None)
    pan.consume_binding_key(pygame.K_F7)
    assert kb.skill_slot_for(pygame.K_F7) == 3
    assert kb.skill_slot_for(pygame.K_3) is None
