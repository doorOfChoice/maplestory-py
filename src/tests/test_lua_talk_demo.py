"""1012119 talk() 演示脚本端到端最小验证：链接按任务实时状态显隐、接取/交付跳步。

透过公开 seam Conversation.from_source 测试；任务定义由真实 entries() 翻译
（load_lua_quest_defs 扫 content/npc），状态机用真实 QuestLog；玩家/世界为
SimpleNamespace 替身，不依赖 WZ、不使用 mock。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from game import settings
from game.systems.conversation import Conversation, make_ctx_view
from game.systems.lua_quests import load_lua_quest_defs
from game.systems.quests import QuestLog
from game.systems.script_api import make_globals

pytest.importorskip("lupa")

_SRC = (settings.RESOURCE_DIR / "content" / "npc" / "1012119.lua").read_text("utf-8")
QID = "c_1012119_1"


def make_world(potions: int = 0):
    """合成世界：真实 QuestDef（entries() 翻译）+ 真实 QuestLog + 假玩家。"""
    defs = load_lua_quest_defs()
    player = SimpleNamespace(level=30, job=0, assets=None, exp=0,
                             inventory=SimpleNamespace(etcs={}, consumes={}),
                             gain_exp=lambda n: None)
    if potions:
        player.inventory.consumes["02000000"] = SimpleNamespace(
            id="02000000", count=potions)
    player.quests = QuestLog(defs)
    return SimpleNamespace(player=player, combat=SimpleNamespace(meso=0),
                           assets=None)


def open_talk(world) -> Conversation:
    """按 npc_dialogue._open_script_conv 同款方式搭宿主 ctx 并开会话。"""
    host = SimpleNamespace(player=world.player, world=world, assets=None,
                           npc_name="托德", quest_defs=world.player.quests.defs,
                           advanced=False, pending_warp=None)
    ctx = make_ctx_view(world.player, "1012119", "托德", 100000000)
    return Conversation.from_source(_SRC, make_globals(host), ctx, title="托德")


def labels(conv: Conversation):
    return [l for l, _ in conv.current().links]


def accept(world) -> None:
    """新开一场会话并点第一条链接（接任务）。"""
    conv = open_talk(world)
    conv.click_link(0)


def test_fresh_player_sees_accept_link_and_no_complete():
    """未接取：显示「接任务」，隐藏「交付」，寒暄恒在。"""
    assert labels(open_talk(make_world())) == ["接任务：收集红药水", "商店", "随便聊聊"]


def test_accept_link_jumps_to_accepted_step():
    """点「接任务」：accept_quest 生效并跳到接取文案步。"""
    world = make_world()
    conv = open_talk(world)
    conv.click_link(0)
    assert world.player.quests.is_accepted(QID)
    assert "太好了" in conv.current().lines[0]


def test_accepted_without_items_hides_both_quest_links():
    """已接取但药水不足：两条任务链接都隐藏。"""
    world = make_world()
    accept(world)
    assert labels(open_talk(world)) == ["商店", "随便聊聊"]


def test_accepted_with_items_shows_complete_link():
    """已接取且药水凑满：「交付」链接出现，「接任务」消失。"""
    world = make_world(potions=10)
    accept(world)
    assert labels(open_talk(world)) == ["交付：收集红药水", "商店", "随便聊聊"]


def test_complete_click_grants_reward_and_completes():
    """点「交付」：complete_quest 发奖、任务置完成、跳奖励文案步。"""
    world = make_world(potions=10)
    accept(world)
    conv = open_talk(world)
    conv.click_link(0)
    assert world.player.quests.is_completed(QID)
    assert world.combat.meso == 1000
    assert conv.current().lines == ["这是你的奖励！"]


def test_completed_quest_hides_quest_links():
    """任务完成后重开：两条任务链接都不再出现。"""
    world = make_world(potions=10)
    accept(world)
    conv = open_talk(world)
    conv.click_link(0)
    assert labels(open_talk(world)) == ["商店", "随便聊聊"]
