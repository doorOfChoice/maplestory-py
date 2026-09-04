"""声明式链接展开 + takeover：type=quest/travel/shop 由宿主按数据源展开成具体链接。

合成 QuestDef（含字符串 qid 前置）+ 真实 QuestLog + 内嵌 Lua talk() 源码，
验证：quest 接/交链接显隐与终态步文案、travel 剔当前图、shop 非生意、
on_business 让位判定、travel 子集写法、prereq 字符串翻译。不依赖 WZ。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from lupa import LuaRuntime

from game.systems.conversation import ConvServices, Conversation, make_ctx_view
from game.systems.lua_quests import _quest_to_def
from game.systems.quests import QuestDef, QuestLog
from game.systems.script_api import make_globals

pytest.importorskip("lupa")

_rt = LuaRuntime(unpack_returned_tuples=True, register_eval=False)

NPC = "999"
MAP = 100000000


def make_defs() -> dict:
    """两环任务链：q1 收集药水，q2 前置=q1 完成。"""
    return {
        "q1": QuestDef(qid="q1", name="收集蓝药水", start_npc=int(NPC),
                       end_npc=int(NPC), lvmin=1,
                       end_items=[(2000000, 2)], reward_exp=100, reward_money=1000,
                       accept_yes=["受领した！"], complete_yes=["これは報酬！"],
                       complete_stop=["まだ足りない。"]),
        "q2": QuestDef(qid="q2", name="大订单", start_npc=int(NPC),
                       end_npc=int(NPC), lvmin=1,
                       prereq=[("q1", 2)], end_items=[(2000000, 1)]),
    }


def make_world(defs, level: int = 30, potions: int = 0):
    player = SimpleNamespace(level=level, job=0, assets=None, exp=0,
                             inventory=SimpleNamespace(etcs={}, consumes={}),
                             gain_exp=lambda n: None)
    if potions:
        player.inventory.consumes["02000000"] = SimpleNamespace(
            id="02000000", count=potions)
    player.quests = QuestLog(defs)
    return SimpleNamespace(player=player, combat=SimpleNamespace(meso=0),
                           assets=None)


_SRC = """
local M = {}
function M.talk(ctx)
  return {
    title = "T",
    takeover = "%s",
    steps = {
      greet = { text = {"hi"}, links = {
        { type = "quest", qid = "q1" },
        { type = "quest", qid = "q2" },
        { type = "travel" },
        { type = "shop" },
        { label = "chat", click = function(c) return "c" end },
      } },
      c = { text = {"hello"} },
    },
  }
end
return M
"""


def open_conv(world, takeover: str = "on_business", *, teleports=None,
              has_shop: bool = True) -> Conversation:
    defs = world.player.quests.defs
    host = SimpleNamespace(player=world.player, world=world, jobdef=None,
                           assets=None, npc_name="T", quest_defs=defs,
                           advanced=False, pending_warp=None, pending_shop=None)
    ctx_view = make_ctx_view(world.player, NPC, "T", MAP)
    conv = Conversation.from_source(
        _SRC % takeover, make_globals(host), ctx_view, title="T",
        services=ConvServices(quest_defs=defs,
                              teleports=teleports if teleports is not None
                              else [("射手村", "100000000"),
                                    ("魔法密林", "101000000")],
                              has_shop=has_shop))
    conv._host = host  # 断言 pending_warp/pending_shop 用
    return conv


def labels(conv: Conversation):
    return [l for l, _ in conv.current().links]


def test_quest_expansion_respects_prereq_and_travel_filter():
    """q2 被 prereq 挡住；travel 剔当前图；shop/手写链接恒在。"""
    conv = open_conv(make_world(make_defs()))
    assert labels(conv) == ["接任务：收集蓝药水", "魔法密林", "商店", "chat"]


def test_accept_click_shows_accept_yes():
    """点「接任务」：任务接取，跳到 accept_yes 文案步。"""
    world = make_world(make_defs())
    conv = open_conv(world)
    conv.click_link(0)
    assert world.player.quests.is_accepted("q1")
    assert conv.current().lines == ["受领した！"]


def test_business_and_yield_policy():
    """接了 q1 但没凑齐：无生意 → on_business 让位；always 不让位。"""
    world = make_world(make_defs())
    open_conv(world, teleports=[]).click_link(0)
    idle = open_conv(world, teleports=[])
    assert not idle.has_business()
    assert idle.yields_to_route()
    stay = open_conv(world, takeover="always", teleports=[])
    assert stay.yields_to_route() is False


def test_complete_link_reward_and_step():
    """凑齐后：「交付」出现，点击发奖并跳 complete_yes。"""
    world = make_world(make_defs(), potions=2)
    open_conv(world).click_link(0)
    conv = open_conv(world)
    assert labels(conv) == ["交付：收集蓝药水", "魔法密林", "商店", "chat"]
    conv.click_link(0)
    assert world.player.quests.is_completed("q1")
    assert world.combat.meso == 1000
    assert conv.current().lines == ["これは報酬！"]


def test_travel_click_registers_warp_and_ends():
    """点目的地：teleport 登记意图且会话结束。"""
    world = make_world(make_defs())
    conv = open_conv(world)
    conv.click_link(1)                      # 魔法密林
    assert conv._host.pending_warp == "101000000"
    assert conv.done


def test_travel_subset_by_label():
    """{type="travel", label=…} 只展开指名目的地。"""
    src = """
local M = {}
function M.talk(ctx)
  return { title = "T", steps = { greet = { links = {
    { type = "travel", label = "魔法密林" },
  } } } }
end
return M
"""
    world = make_world(make_defs())
    host = SimpleNamespace(player=world.player, world=world, jobdef=None,
                           assets=None, npc_name="T",
                           quest_defs=world.player.quests.defs,
                           advanced=False, pending_warp=None, pending_shop=None)
    conv = Conversation.from_source(
        src, make_globals(host), make_ctx_view(world.player, NPC, "T", MAP),
        services=ConvServices(quest_defs=host.quest_defs,
                              teleports=[("射手村", "100000000"),
                                         ("魔法密林", "101000000")]))
    assert [l for l, _ in conv.current().links] == ["魔法密林"]
    assert conv.has_business()


def test_shop_link_not_business_and_registers_intent():
    """商店链接不算生意，但点击登记开店意图并结束。"""
    world = make_world(make_defs())
    conv = open_conv(world, teleports=[])
    conv.click_link(1)                      # q1 offer 之后就是商店（q2 被挡）
    assert conv._host.pending_shop is True
    assert conv.done


def test_business_counts_quest_offer_or_completable_only():
    """四环无生意判定的反例：无任务条目 + 无 travel → 无生意。"""
    src = """
local M = {}
function M.talk(ctx)
  return { title = "T", takeover = "on_business", steps = { greet = { links = {
    { label = "chat", click = function(c) return "c" end },
  } }, c = { text = {"ok"} } } }
end
return M
"""
    world = make_world(make_defs())
    world.player.quests.status["q2"] = "accepted"      # 进行中但不可交付
    host = SimpleNamespace(player=world.player, world=world, jobdef=None,
                           assets=None, npc_name="T",
                           quest_defs=world.player.quests.defs,
                           advanced=False, pending_warp=None, pending_shop=None)
    conv = Conversation.from_source(
        src, make_globals(host), make_ctx_view(world.player, NPC, "T", MAP),
        services=ConvServices(quest_defs=host.quest_defs, teleports=[],
                              has_shop=True))
    assert not conv.has_business()
    assert conv.yields_to_route()


def test_string_prereq_translation():
    """entries() 的 prereq 支持字符串 qid（c_1012119_1 这类自定义任务）。"""
    tbl = _rt.table(_rt.table("c_1012119_1", 2))
    d = _quest_to_def("1012119", 2, _rt.table(name="x", prereq=tbl))
    assert d.prereq == [("c_1012119_1", 2)]
