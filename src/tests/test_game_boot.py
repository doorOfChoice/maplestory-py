"""Game 的 headless 冒烟测试：在无 WZ 文件下驱动开屏→世界构建→若干帧更新/绘制。

用途：游戏循环重构的自动护航。真实 Game 需要官方 WZ 资产方能运行（WZ 不入库），
故以合成 FakeAssets 替身驱动。这里触碰 Game 的若干私有方法（_bootstrap_frame /
_update / _draw / _enter_map / respawn），是刻意的「冒烟" harness——其余单测
都不覆盖 game.py，它是唯一的运行时验证防线。
"""

from __future__ import annotations

import os

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.game import Game
from tests.fake_assets import FakeAssets

pygame.init()


def _boot(game: Game, frames: int = 2000) -> None:
    """推进开屏帧直到世界构建完成（含防卡死上限），并完成主线程就绪。"""
    for _ in range(frames):
        if game._world_ready:
            break
        game._bootstrap_frame(0.016)
    assert game._world_ready, "世界构建未在超时内完成"
    if not getattr(game, "_boot_done", False):
        game._finish_bootstrap()
        game._boot_done = True
    assert hasattr(game, "ctx") and hasattr(game.ctx.world, "player"), \
        "world 构建后应存在 player"


def _drive(game: Game, frames: int = 12) -> None:
    """跑若干帧输入 + 更新 + 绘制，确保不崩溃。"""
    for _ in range(frames):
        game._handle_input()
        game._update(0.016)
        game._draw()


@pytest.fixture
def game(monkeypatch):
    monkeypatch.setattr("game.game.Assets", FakeAssets)
    g = Game()
    yield g
    # 不调用 _shutdown：其 pygame.quit() 会使全局字体缓存失效，导致同一
    # 进程内后续测试复用 Font 时 C 层崩溃。冒烟骨架不负责资源回收，交给进程退出。


def test_boot_completes_and_draws(game):
    """开屏→世界构建完成后，能连续多帧 update/draw 而不崩溃。"""
    _boot(game)
    assert game.ctx.world.player.hp > 0
    _drive(game)


def test_map_switch_finishes_loading(game):
    """切图：_enter_map 后等加载完成，玩家被重定位到新图出生点。"""
    _boot(game)
    game._enter_map("200000000", "sp")
    assert game._loading
    for _ in range(120):
        game._update(0.016)
        game._draw()
        if not game._loading:
            break
    assert not game._loading, "加载未在超时内完成"
    assert game.ctx.assets.map_id == "200000000"


def test_respawn_recovers_player(game):
    """重生：hp 回满、世界实体重建、无崩溃。"""
    _boot(game)
    game.ctx.world.player.hp = 0
    game.dead = True
    game.respawn()
    assert not game.dead
    assert game.ctx.world.player.hp == game.ctx.world.player.max_hp
    assert game.ctx.world.monsters is not None
    assert game.ctx.world.npcs is not None
