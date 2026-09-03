"""Lua 发奖能力：宿主加载 reward_test.lua，验证 give_reward 发放 exp/金币/物品及返回值。

透过公开 seam Conversation.from_source 测试；用真实 Inventory + FakeAssets 构造玩家，
不使用 mock。host 携带 world 使 make_globals 注册 give_reward。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from game import settings
from game.systems.conversation import Conversation, make_ctx_view
from game.systems.inventory import Inventory
from game.systems.script_api import make_globals
from tests.fake_assets import FakeAssets

pytest.importorskip("lupa")

_SRC = (settings.RESOURCE_DIR / "content" / "npc" / "reward_test.lua"
        ).read_text("utf-8")


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
    host = SimpleNamespace(player=world.player, world=world, assets=None,
                           npc_name="测试", advanced=False)
    ctx = make_ctx_view(world.player, "9999999", "测试", 100000000)
    return Conversation.from_source(_SRC, make_globals(host), ctx)


def _click_branch(world, index: int) -> Conversation:
    """开一场会话并点第 index 条链接（full/exp_only/empty/negative）。"""
    conv = _session(world)
    conv.current()
    conv.click_link(index)
    return conv


def test_give_reward_full_grants_exp_meso_and_item():
    """full 分支：经验+500、金币+1000、物品 2000000×3 入背包，返回 true。"""
    world = _reward_world()
    conv = _click_branch(world, 0)
    assert world.player.exp == 500
    assert world.combat.meso == 1000
    assert world.player.inventory.consumes["02000000"].count == 3
    assert conv.current().lines == ["result:true"]


def test_give_reward_exp_only_skips_meso_and_item():
    """exp_only 分支：只加经验，金币与物品不受影响。"""
    world = _reward_world()
    conv = _click_branch(world, 1)
    assert world.player.exp == 500
    assert world.combat.meso == 0
    assert world.player.inventory.consumes == {}
    assert conv.current().lines == ["result:true"]


def test_give_reward_empty_is_noop_but_true():
    """empty 分支：无参数调用不改任何值，仍返回 true。"""
    world = _reward_world()
    conv = _click_branch(world, 2)
    assert conv.current().lines == ["result:true"]
    assert world.player.exp == 0
    assert world.combat.meso == 0
    assert world.player.inventory.consumes == {}


def test_give_reward_negative_removes_item():
    """negative 分支：物品负数量表示收回，背包里该物品数量减少。"""
    world = _reward_world()
    _click_branch(world, 0)                     # 先给 3 个
    conv = _click_branch(world, 3)              # 再收回 1 个
    assert conv.current().lines == ["result:true"]
    assert world.player.inventory.consumes["02000000"].count == 2
