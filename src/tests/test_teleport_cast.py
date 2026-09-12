"""快速移动接线：位移失败（垂直无落点）不扣 MP、不写冷却；成功才扣。"""

from __future__ import annotations

import os
import time

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from game.game import Game
from game import settings
from game.systems.skills import SkillDef
from tests.fake_assets import FakeAssets

pygame.init()

lupa = pytest.importorskip("lupa")

TELEPORT = "2101002"     # 火毒快速移动：登记为 teleport 形态


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
    g.ctx.ui.hide_dialog()
    yield g


def _arm_teleport(game: Game, slot: int = 1, mp_con: int = 13,
                  distance: int = 130) -> None:
    player = game.ctx.world.player
    book = player.skills
    book.defs[TELEPORT] = SkillDef(
        TELEPORT, "快速移动", "", [{"mpCon": mp_con, "range": distance}], 1)
    book.levels[TELEPORT] = 1
    book.hotkeys[slot] = TELEPORT
    player.x, player.y = 0.0, -settings.FEET_OFFSET
    player.on_ground = True
    player.ground_layer = 0
    player.cur_fh = game.ctx.world.physics.grounded_surface(0, 0.0)
    player.attacking = False
    player.mp = 500


def test_vertical_teleport_without_landing_costs_nothing(game):
    """平地上按 ↑ 瞬移：本层上方无平台 → 原地不动、不扣 MP。"""
    _arm_teleport(game)
    game.keys.up, game.keys.down = True, False
    player = game.ctx.world.player
    game._try_cast(1)
    assert player.x == 0.0 and player.y == -settings.FEET_OFFSET
    assert player.mp == 500
    assert TELEPORT not in player.skills.cooldowns


def test_horizontal_teleport_deducts_mp_and_moves(game):
    """水平瞬移成功：扣 MP、按朝向位移，不进入攻击流程。"""
    _arm_teleport(game)
    game.keys.up, game.keys.down = False, False
    player = game.ctx.world.player
    player.facing_right = True
    game._try_cast(1)
    assert player.x == 130.0
    assert player.mp == 500 - 13
    assert player.attacking is False
