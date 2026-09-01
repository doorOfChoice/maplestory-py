"""Game 的 headless 冒烟测试：在无 WZ 文件下驱动开屏→世界构建→若干帧更新/绘制。

用途：游戏循环重构的自动护航。真实 Game 需要官方 WZ 资产方能运行（WZ 不入库），
故以合成 FakeAssets 替身驱动。这里触碰 Game 的若干私有方法（_bootstrap_frame /
_update / _draw / _enter_map / respawn），是刻意的「冒烟" harness——其余单测
都不覆盖 game.py，它是唯一的运行时验证防线。
"""

from __future__ import annotations

import os
import time
from types import SimpleNamespace

import pygame
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game.game import Game
from tests.fake_assets import FakeAssets

pygame.init()


def _boot(game: Game, timeout: float = 30.0) -> None:
    """推进开屏帧直到世界构建完成（墙钟超时防卡死），并完成主线程就绪。

    世界在后台线程构建，主线程空转画 splash 会独占 GIL 而饿死该线程，
    故每帧短暂 sleep 让出 GIL，并以墙钟而非帧数判定超时。
    """
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
    assert hasattr(game, "ctx") and hasattr(game.ctx.world, "player"), \
        "world 构建后应存在 player"


def _drive(game: Game, frames: int = 12) -> None:
    """跑若干帧输入 + 更新 + 绘制，确保不崩溃。"""
    for _ in range(frames):
        game._handle_input()
        game._update(0.016)
        game._draw()


@pytest.fixture
def game(monkeypatch, tmp_path):
    monkeypatch.setattr("game.game.Assets", FakeAssets)
    # 隔离真实存档：boot 测试不应受玩家进度（如已完成的转职任务）影响
    monkeypatch.setattr("game.settings.SAVE_FILE", tmp_path / "save.json")
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


def _fake_npc(npc_id: str = "1012100") -> SimpleNamespace:
    return SimpleNamespace(
        npc_id=npc_id, name="赫丽娜",
        rect=lambda: pygame.Rect(0, 0, 40, 80))


def test_advancement_flow_uses_script(game):
    """转职经脚本会话：Lv10 新手对导师点 yes → 转职为弓箭手，会话结束。"""
    from game.core.jobs import JOBS
    _boot(game)
    game.ctx.world.player.job = 0
    game.ctx.world.player.level = 10
    npc = _fake_npc()
    dlg = game._dialogue
    dlg._begin_lua_quest(npc, "adv_3000", "advance")
    assert dlg._advance_session is not None
    assert [o.label for o in dlg._advance_session.snapshot().options] == ["yes", "no"]
    dlg._advance_button("yes")
    assert game.ctx.world.player.job == 3000
    assert dlg._advance_session is not None      # 停在「恭喜转职」节点
    dlg._advance_button("ok")
    assert dlg._advance_session is None
    game._draw()   # 转职后正常出帧


def test_advance_quest_registered_in_boot(game):
    """启动装配后 quest_defs 含转职任务，Lv10 新手在导师处可见。"""
    from game.systems.quests import collect_npc_quests
    _boot(game)
    player = game.ctx.world.player
    player.job = 0
    player.level = 10
    assert "adv_3000" in game.quest_defs
    items = collect_npc_quests(game.quest_defs, player.quests, "1012100", player)
    assert "adv_3000" in [it.qid for it in items]


def test_npc_quest_menu_select_opens_quest(game):
    """多任务弹与单任务对话框同款的 UtilDlgEx 列表，点选条目进入对应任务接取流程。"""
    from game.systems.quests import QuestDef, collect_npc_quests, QuestLog
    _boot(game)
    npc = _fake_npc()
    player = game.ctx.world.player
    player.level = 10
    defs = {
        "1": QuestDef(qid="1", name="弓箭手入门", start_npc=1012100, lvmin=10),
        "2": QuestDef(qid="2", name="打菇菇", start_npc=1012100, lvmin=5),
        "3": QuestDef(qid="3", name="别处任务", start_npc=9999999, lvmin=10),
    }
    player.quests = QuestLog(defs)
    game.quest_defs = defs
    dlg = game._dialogue
    dlg.quest_defs = defs
    items = collect_npc_quests(defs, player.quests, "1012100", player)
    assert [it.qid for it in items] == ["1", "2"]
    dlg._open_quest_menu(npc, items)
    assert game.ctx.ui.quest_visible
    assert game.ctx.ui.quest_entries == [("弓箭手入门", 10), ("打菇菇", 5)]
    game._draw()   # 出菜单帧不崩溃
    dlg._open_npc_quest(npc, items[1])
    assert dlg._quest_flow == {"npc": npc, "quest": "2", "stage": "offer"}
    dlg._close_quest_menu()
    game._draw()
