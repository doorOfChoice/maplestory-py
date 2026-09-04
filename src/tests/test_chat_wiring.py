"""聊天接线：Enter 聚焦、聚焦时吞键、/指令执行与反馈、/warp 真实切图。

沿用 headless 冒烟手法：FakeAssets 驱动真实 Game，用注入的 pygame 事件
从公开入口走完整输入路由，验证聊天从按键到世界效果的闭环行为。
"""

from __future__ import annotations

import os
import time

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from game.game import Game
from tests.fake_assets import FakeAssets

pygame.init()

pytest.importorskip("lupa")


def _boot(game: Game, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not game._world_ready:
        game._bootstrap_frame(0.016)
        if game._world_ready:
            break
        if time.monotonic() > deadline:
            break
        time.sleep(0.001)
    assert game._world_ready, "世界构建未在超时内完成"
    if not getattr(game, "_boot_done", False):
        game._finish_bootstrap()
        game._boot_done = True


@pytest.fixture
def game(monkeypatch, tmp_path):
    monkeypatch.setattr("game.game.Assets", FakeAssets)
    monkeypatch.setattr("game.settings.SAVE_FILE", tmp_path / "save.json")
    g = Game()
    _boot(g)
    g.ctx.ui.hide_dialog()        # 关掉欢迎气泡，Enter 不再被对话层消费
    yield g


def _key(game: Game, key: int) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=""))
    game._handle_input()


def _text(game: Game, s: str) -> None:
    pygame.event.post(pygame.event.Event(pygame.TEXTINPUT, text=s))
    game._handle_input()


def _send(game: Game, line: str) -> None:
    _key(game, pygame.K_RETURN)     # 聚焦聊天
    _text(game, line)
    _key(game, pygame.K_RETURN)     # 发送并收起


def _pump_loading(game: Game, frames: int = 120) -> None:
    for _ in range(frames):
        game._update(0.016)
        game._draw()
        if not game._loading:
            return


# ── 聚焦与吞键 ──────────────────────────────────────────────────────

def test_enter_focuses_chat_and_keys_type_text(game):
    _key(game, pygame.K_RETURN)
    assert game.chat.focused
    _text(game, "你好")
    assert game.chat.text == "你好"


def test_focused_chat_swallows_game_keys(game):
    """聚焦时按攻击键不进缓冲也不触发攻击；字符仍由 TEXTINPUT 入缓冲。"""
    _key(game, pygame.K_RETURN)
    _key(game, pygame.K_a)
    assert game.chat.text == ""
    assert not game.ctx.world.player.attacking
    _text(game, "a")
    assert game.chat.text == "a"


def test_esc_clears_and_closes_chat(game):
    _key(game, pygame.K_RETURN)
    _text(game, "半句话")
    _key(game, pygame.K_ESCAPE)
    assert not game.chat.focused
    assert game.chat.text == ""


def test_enter_closes_chat_and_keeps_log(game):
    """普通发言：发送后收起，日志留下「我自己」的白行。"""
    _send(game, "大家好")
    assert not game.chat.focused
    assert game.chat.lines[-1].kind == "player"
    assert "大家好" in game.chat.lines[-1].text


def test_dialog_still_consumes_enter_first(game):
    """NPC 对话打开时 Enter 先用于关对话，不会顺手聚焦聊天。"""
    game.ctx.ui.show_dialog("村长", ["测试"])
    _key(game, pygame.K_RETURN)
    assert not game.ctx.ui.dialog_visible
    assert not game.chat.focused


# ── GM 指令闭环 ─────────────────────────────────────────────────────

def test_heal_command_restores_and_logs(game):
    game.ctx.world.player.hp = 1
    _send(game, "/heal")
    p = game.ctx.world.player
    assert p.hp == p.max_hp and p.mp == p.max_mp
    assert game.chat.lines[-1].kind == "system"


def test_warp_command_switches_map(game):
    _send(game, "/warp 200000000")
    assert game._loading
    _pump_loading(game)
    assert not game._loading
    assert game.ctx.assets.map_id == "200000000"


def test_warp_missing_map_reports_error_without_loading(game):
    _send(game, "/warp 999999999")
    assert not game._loading
    assert game.chat.lines[-1].kind == "error"


def test_meso_command_adds_money(game):
    before = game.ctx.world.combat.meso
    _send(game, "/meso 12345")
    assert game.ctx.world.combat.meso == before + 12345


def test_unknown_command_logs_error(game):
    _send(game, "/fly")
    assert game.chat.lines[-1].kind == "error"
