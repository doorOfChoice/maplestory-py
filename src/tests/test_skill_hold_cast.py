"""通道技按住连发（暴風神射等 WZ keydown 技能）：按住以间隔补放、松手即停。

沿用 headless 冒烟手法：FakeAssets 驱动真实 Game，注入按键与 get_pressed，
从公开入口验证「keydown 事件首放 → 按住按间隔续放 → 松开停止」的完整链路。
"""

from __future__ import annotations

import os
import time

import pygame

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from game.game import Game
from game import settings
from game.systems.skills import SkillDef, SkillBook
from tests.fake_assets import FakeAssets

pygame.init()

pytest.importorskip("lupa")

REPEAT = "3121004"      # 暴風神射：WZ 带 keydown → 按住连发
ONCE = "3111004"        # 箭雨对照组用：本项目按单次施放处理（非通道）


class HeldKeys:
    """pygame.key.get_pressed() 替身：按集合模拟按住状态。"""

    def __init__(self) -> None:
        self.down: set[int] = set()

    def __getitem__(self, key: int) -> bool:
        return key in self.down


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


def _make_def(sid: str, repeat: bool, mp_con: int = 9) -> SkillDef:
    return SkillDef(sid, "暴風神射" if repeat else "箭雨", "",
                    [{"mpCon": mp_con, "damage": 51}], 1, repeat=repeat)


def _arm_skill(game: Game, slot: int, key: int, sid: str,
               repeat: bool) -> SkillBook:
    book = game.ctx.world.player.skills
    book.defs[sid] = _make_def(sid, repeat)
    book.levels[sid] = 1
    book.hotkeys[slot] = sid
    game.keybindings.set(f"skill_{slot}", key)
    game.ctx.world.player.mp = 9999
    return book


def _press(game: Game, key: int, held: HeldKeys) -> None:
    held.down.add(key)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key,
                                          unicode="", mod=0))
    game._handle_input()


def _release(held: HeldKeys, key: int) -> None:
    held.down.discard(key)


# ── SkillBook：cast 数据透出 repeat ─────────────────────────────────
def test_cast_marks_repeat_skill():
    book = SkillBook(None, 3120, defs={"3121004": _make_def(REPEAT, True)})
    book.levels[REPEAT] = 1
    assert book.cast(REPEAT, 120)["repeat"] is True


def test_cast_non_repeat_skill_marked_false():
    book = SkillBook(None, 3110, defs={"3111004": _make_def(ONCE, False)})
    book.levels[ONCE] = 1
    assert book.cast(ONCE, 70)["repeat"] is False


# ── Game 接线：按住按间隔续放、松开即停 ──────────────────────────────
def test_hold_repeat_skill_refires_while_held(game, monkeypatch):
    held = HeldKeys()
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: held)
    casts: list[int] = []
    monkeypatch.setattr(game, "_try_cast", lambda slot: casts.append(slot))
    _arm_skill(game, 1, pygame.K_q, REPEAT, repeat=True)

    _press(game, pygame.K_q, held)
    assert casts == [1]                      # keydown 事件首放

    game._update(settings.SKILL_KEYDOWN_INTERVAL - 0.05)
    assert casts == [1]                      # 未到间隔不补放
    game._update(0.1)
    assert casts == [1, 1]                   # 到间隔自动补放
    game._update(settings.SKILL_KEYDOWN_INTERVAL + 0.1)
    assert casts == [1, 1, 1]

    _release(held, pygame.K_q)
    game._update(settings.SKILL_KEYDOWN_INTERVAL * 3)
    assert casts == [1, 1, 1]                # 松手后不再补放


def test_hold_repeat_skill_shows_channel_effect_tracking_player(game, monkeypatch):
    """按住通道技时挂上 keydown 持续特效（循环且跟随玩家），而非只飘一次。"""
    held = HeldKeys()
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: held)
    frame = (pygame.Surface((4, 4)), (2, 4), 100)
    monkeypatch.setattr(game.assets, "skill_keydown_frames", lambda sid: [frame])
    monkeypatch.setattr(game, "_try_cast", lambda slot: None)
    _arm_skill(game, 1, pygame.K_q, REPEAT, repeat=True)

    _press(game, pygame.K_q, held)
    effects = game.ctx.world.combat.effects
    looping = [e for e in effects if getattr(e, "loop", False)]
    assert len(looping) == 1
    assert looping[0].follow is game.ctx.world.player

    game.ctx.world.player.x += 50.0
    game._update(0.05)
    assert looping[0].x == game.ctx.world.player.x


def test_channel_effect_flips_with_player_facing(game, monkeypatch):
    """通道技持续特效随人物朝向水平镜像，人物转身特效立即改朝。"""
    held = HeldKeys()
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: held)
    frame = (pygame.Surface((4, 4)), (2, 4), 100)
    monkeypatch.setattr(game.assets, "skill_keydown_frames", lambda sid: [frame])
    monkeypatch.setattr(game, "_try_cast", lambda slot: None)
    _arm_skill(game, 1, pygame.K_q, REPEAT, repeat=True)

    game.ctx.world.player.facing_right = True
    _press(game, pygame.K_q, held)
    looping = [e for e in game.ctx.world.combat.effects
               if getattr(e, "loop", False)]
    game._update(0.05)
    assert looping[0].flip is False
    game.ctx.world.player.facing_right = False
    game._update(0.05)
    assert looping[0].flip is True


def test_release_repeat_skill_ends_channel_effect(game, monkeypatch):
    """松手：移除循环特效并补播一次 keydownend 收招。"""
    held = HeldKeys()
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: held)
    frame = (pygame.Surface((4, 4)), (2, 4), 1000)
    monkeypatch.setattr(game.assets, "skill_keydown_frames", lambda sid: [frame])
    monkeypatch.setattr(game.assets, "skill_keydown_end_frames",
                        lambda sid: [frame])
    monkeypatch.setattr(game, "_try_cast", lambda slot: None)
    _arm_skill(game, 1, pygame.K_q, REPEAT, repeat=True)

    _press(game, pygame.K_q, held)
    _release(held, pygame.K_q)
    game._update(0.1)
    effects = game.ctx.world.combat.effects
    assert not any(getattr(e, "loop", False) for e in effects)
    assert any(not getattr(e, "loop", False) for e in effects)


def test_hold_does_not_repeat_non_keydown_skill(game, monkeypatch):
    held = HeldKeys()
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: held)
    casts: list[int] = []
    monkeypatch.setattr(game, "_try_cast", lambda slot: casts.append(slot))
    _arm_skill(game, 2, pygame.K_w, ONCE, repeat=False)

    _press(game, pygame.K_w, held)
    assert casts == [2]
    game._update(settings.SKILL_KEYDOWN_INTERVAL * 5)
    assert casts == [2]                      # 非通道技：按住不连发


# ── 冷却策略：通道技不写 CD（按住节奏由补放间隔控制）────────────────
def test_repeat_skill_cast_writes_no_cooldown(game):
    book = _arm_skill(game, 1, pygame.K_q, REPEAT, repeat=True)
    game._try_cast(1)
    assert book.levels[REPEAT] == 1
    assert REPEAT not in book.cooldowns
    assert game.ctx.world.player.attacking   # 已进入技能攻击


def test_normal_skill_cast_still_gets_cooldown(game):
    book = _arm_skill(game, 2, pygame.K_w, ONCE, repeat=False)
    game._try_cast(2)
    assert book.cooldowns.get(ONCE, 0.0) > 0.0
