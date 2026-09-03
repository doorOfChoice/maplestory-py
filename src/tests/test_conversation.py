"""步骤图对话引擎：show 过滤、click 跳步、nil 结束、buttons 路由、错误兜底。"""
from __future__ import annotations

import logging

from game.systems.conversation import (
    Conversation, ConversationDef, Link, Step)


def one_link_conv(click_ret, visible=True):
    """单步单链接的会话：click 返回 click_ret，show 返回 visible。"""
    step = Step(text=["黑文本"], links=[Link("蓝字", show=lambda: visible,
                                             click=lambda: click_ret)])
    return Conversation(ConversationDef("T", "s", {"s": step}))


def test_current_snapshot_lists_visible_links_and_text():
    """current() 返回黑文本 + 过滤后的蓝字（label,note 元组）。"""
    conv = one_link_conv("s")
    snap = conv.current()
    assert snap.title == "T"
    assert snap.lines == ["黑文本"]
    assert snap.links == [("蓝字", 0)]
    assert snap.buttons == []
    assert snap.terminal is False


def test_hidden_link_excluded_from_snapshot():
    """show 返回 False 的链接不进快照、不占点击序号。"""
    conv = one_link_conv("s", visible=False)
    assert conv.current().links == []


def test_click_jump_keeps_conversation_on_target_step():
    """click 返回步名 → 跳转到该步。"""
    steps = {"a": Step(links=[Link("go", click=lambda: "b")]),
             "b": Step(text=["到达"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    conv.click_link(0)
    assert not conv.done
    assert conv.current().lines == ["到达"]


def test_click_none_ends_conversation():
    """click 返回 None → 会话结束。"""
    conv = one_link_conv(None)
    conv.current()
    conv.click_link(0)
    assert conv.done


def test_click_unknown_step_ends_with_warning():
    """click 返回不存在的步名 → 结束（不崩溃）并记 warning。"""
    conv = one_link_conv("nope")
    conv.current()
    conv.click_link(0)
    assert conv.done


def test_click_raising_ends_conversation():
    """click 抛异常 → 结束会话，游戏不崩。"""
    def boom():
        raise RuntimeError("x")
    conv = Conversation(ConversationDef(
        "T", "s", {"s": Step(links=[Link("坏", click=boom)])}))
    conv.current()
    conv.click_link(0)
    assert conv.done


def test_show_raising_hides_only_that_link():
    """show 抛异常 → 仅该链接隐藏，其余正常。"""
    def boom():
        raise RuntimeError("x")
    step = Step(links=[Link("坏", show=boom), Link("好")])
    conv = Conversation(ConversationDef("T", "s", {"s": step}))
    assert [l for l, _ in conv.current().links] == ["好"]


def test_terminal_step_reports_terminal():
    """无链接无按钮的步骤 = 终态（渲染 BtOK，确认即结束）。"""
    conv = Conversation(ConversationDef("T", "s", {"s": Step(text=["完"])}))
    assert conv.current().terminal
    conv.press("confirm")
    assert conv.done


def test_press_confirm_fires_yes_button():
    """confirm（回车/空格/BtYes 命中）触发 buttons 里的 yes。"""
    steps = {"a": Step(text=["问"], buttons={"yes": "b", "no": "c"}),
             "b": Step(text=["好"]), "c": Step(text=["拒"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    snap = conv.current()
    assert snap.buttons == ["yes", "no"]
    conv.press("confirm")
    assert conv.current().lines == ["好"]


def test_press_close_fires_no_button():
    """close（Esc/BtNo 命中）触发 no 分支。"""
    steps = {"a": Step(buttons={"yes": "b", "no": "c"}),
             "b": Step(text=["好"]), "c": Step(text=["拒"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    conv.press("close")
    assert conv.current().lines == ["拒"]


def test_press_close_without_no_button_ends():
    """无 no 按钮时 Esc 直接结束会话。"""
    conv = Conversation(ConversationDef("T", "a", {"a": Step(text=["问"])}))
    conv.press("close")
    assert conv.done


def test_button_value_can_be_callable():
    """buttons 的值也可以是函数：副作用后返回步名。"""
    calls = []

    def do_yes():
        calls.append(1)
        return "b"
    steps = {"a": Step(buttons={"yes": do_yes}), "b": Step(text=["完"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    conv.press("yes")
    assert calls == [1]
    assert conv.current().lines == ["完"]


def test_step_next_used_on_terminal_confirm():
    """终态步骤的 next 指向后续步（无 next 才结束）。"""
    steps = {"a": Step(text=["问"], buttons={"yes": "b"}),
             "b": Step(text=["谢"], next="a")}
    conv = Conversation(ConversationDef("T", "b", steps))
    conv.press("confirm")
    assert not conv.done
    assert conv.current().lines == ["问"]
