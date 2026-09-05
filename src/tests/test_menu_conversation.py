"""默认会话合成：可交付在前、可接、进行中、传送（剔当前图）、商店链接。"""
from __future__ import annotations

from game.npc_dialogue import build_menu_conversation
from game.systems.quests import NpcQuest


def build(quests=(), dests=(), accepted=(), has_shop=False):
    hit = {"quest": [], "teleport": [], "shop": []}
    conv = build_menu_conversation(
        "托德", "100000000", list(quests), list(dests), list(accepted), has_shop,
        on_quest=lambda q: hit["quest"].append(q.qid),
        on_teleport=lambda m, fare: hit["teleport"].append((m, fare)),
        on_shop=lambda: hit["shop"].append(1),
    )
    return conv, hit


def q(qid, state, title=None, level=0):
    return NpcQuest(qid=qid, title=title or qid, level=level, state=state)


def test_menu_link_order_completes_first_then_offers_then_accepted():
    conv, _ = build(quests=[q("a", "offer"), q("b", "complete")],
                    accepted=[q("c", "accepted")])
    labels = [l for l, _ in conv.current().links]
    assert labels == ["b", "a", "c（进行中）"]


def test_menu_excludes_current_map_teleport():
    """当前图目的地剔除；有票价的把价格写进链接文案。"""
    conv, _ = build(dests=[("射手村", "100000000", 1000),
                           ("魔法密林", "101000000", 800)])
    assert [l for l, _ in conv.current().links] == ["魔法密林  800金币"]


def test_menu_shop_link_appended_last():
    conv, hit = build(quests=[q("a", "offer")], has_shop=True)
    assert conv.current().links[-1] == ("商店", 0)
    conv.current()
    conv.click_link(len(conv.current().links) - 1)
    assert hit["shop"] == [1]


def test_click_quest_link_fires_hook_and_ends_menu():
    conv, hit = build(quests=[q("a", "offer", level=10)])
    assert conv.current().links == [("a", 10)]
    conv.click_link(0)
    assert hit["quest"] == ["a"]
    assert conv.done


def test_click_teleport_fires_hook_with_map_and_fare():
    conv, hit = build(dests=[("魔法密林", "101000000", 800)])
    conv.click_link(0)
    assert hit["teleport"] == [("101000000", 800)]
