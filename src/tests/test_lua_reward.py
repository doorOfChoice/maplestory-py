"""Lua 发奖能力：宿主加载 reward_test.lua，验证 give_reward 发放 exp/金币/物品及返回值。

透过公开 seam build_lua_session 测试；用真实 Inventory + FakeAssets 构造玩家，
不使用 mock。world 以 **extra 传入 build_lua_session，使宿主注册 give_reward。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.core.jobs import JOBS
from game.systems.inventory import Inventory
from game.systems.scripting import build_lua_session
from tests.fake_assets import FakeAssets

pytest.importorskip("lupa")


class FakePlayer:
    """最小玩家替身：记录 gain_exp 调用，挂真实 Inventory 供发物品。"""

    def __init__(self, level: int = 10, job: int = 0):
        self.level = level
        self.job = job
        self.assets = FakeAssets()
        self.inventory = Inventory()
        self.exp = 0

    def gain_exp(self, amount: int) -> bool:
        self.exp += amount
        return False


def _reward_world():
    player = FakePlayer()
    world = SimpleNamespace(player=player,
                            combat=SimpleNamespace(meso=0))
    return world


def _session(world):
    sess, ctx = build_lua_session(
        "npc/reward_test", player=world.player, jobdef=JOBS[3000],
        npc_name="测试", world=world)
    return sess


def test_give_reward_full_grants_exp_meso_and_item():
    """full 分支：经验+500、金币+1000、物品 2000000×3 入背包，返回 true。"""
    world = _reward_world()
    sess = _session(world)
    sess.choose("full")
    assert sess.snapshot().lines[0] == "result:true"
    assert world.player.exp == 500
    assert world.combat.meso == 1000
    item = world.player.inventory.consumes["02000000"]
    assert item.count == 3


def test_give_reward_exp_only_skips_meso_and_item():
    """exp_only 分支：只加经验，金币与物品不受影响。"""
    world = _reward_world()
    sess = _session(world)
    sess.choose("exp_only")
    assert world.player.exp == 500
    assert world.combat.meso == 0
    assert world.player.inventory.consumes == {}


def test_give_reward_empty_is_noop_but_true():
    """empty 分支：无参数调用不改任何值，仍返回 true。"""
    world = _reward_world()
    sess = _session(world)
    sess.choose("empty")
    assert sess.snapshot().lines[0] == "result:true"
    assert world.player.exp == 0
    assert world.combat.meso == 0
    assert world.player.inventory.consumes == {}


def test_give_reward_negative_removes_item():
    """negative 分支：物品负数量表示收回，背包里该物品数量减少。"""
    world = _reward_world()
    sess = _session(world)
    # 先给 3 个再收回 1 个
    sess.choose("full")
    assert world.player.inventory.consumes["02000000"].count == 3
    sess2 = _session(world)
    sess2.choose("negative")
    assert sess2.snapshot().lines[0] == "result:true"
    assert world.player.inventory.consumes["02000000"].count == 2
