"""步骤图对话引擎：show 过滤、click 跳步、nil 结束、buttons 路由、错误兜底。

含 Lua talk() 编译层：内嵌合成 Lua 源码驱动 from_source，不依赖 WZ。
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from game.systems.conversation import (
    Conversation, ConversationDef, Link, Step, make_ctx_view)

pytest.importorskip("lupa")


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


# ── Lua talk() 编译层 ─────────────────────────────────────────

_TALK_LUA = """
local M = {}
function M.talk(ctx)
  return {
    title = "托德",
    start = "greet",
    steps = {
      greet = {
        text = function(c)
          return { "等级 " .. c.player.level, "静态行" }
        end,
        links = {
          { label = "接任务",
            show = function(c) return c.player.level >= 10 end,
            click = function(c) return "after" end },
          { label = function(c) return "动态蓝字 " .. c.npc.name end,
            click = function(c) take_item(c.player.level) return nil end },
        },
        buttons = { yes = "after", no = function(c) return nil end },
      },
      after = { text = { "到达。" }, next = "greet" },
    },
  }
end
return M
"""


def compile_talk(level=10, env=None):
    calls = []
    env = env or {"take_item": lambda n: calls.append(n)}
    ctx = make_ctx_view(SimpleNamespace(level=level, job=0),
                        "1012119", "托德", 100000000)
    conv = Conversation.from_source(_TALK_LUA, env, ctx)
    return conv, calls


def test_lua_talk_compiles_steps():
    """talk() 步骤图折进引擎：文本（函数式插值）、按钮、next。"""
    conv, _ = compile_talk(10)
    snap = conv.current()
    assert snap.title == "托德"
    assert snap.lines == ["等级 10", "静态行"]
    assert snap.buttons == ["yes", "no"]
    assert snap.terminal is False


def test_lua_link_show_filters_by_ctx():
    """链接 show 读 ctx：等级不足时隐藏。"""
    conv, _ = compile_talk(level=5)
    assert [l for l, _ in conv.current().links] == ["动态蓝字 托德"]


def test_lua_link_click_jumps_step():
    """Lua click 返回步名 → 跳转。"""
    conv, _ = compile_talk(10)
    conv.current()
    conv.click_link(0)
    assert conv.current().lines == ["到达。"]
    conv.press("confirm")           # after 的 next = greet → 回首步
    assert not conv.done


def test_lua_click_nil_and_env_side_effect():
    """Lua click 调宿主函数并返回 nil → 副作用发生、会话结束。"""
    conv, calls = compile_talk(10)
    conv.current()
    conv.click_link(1)
    assert calls == [10]
    assert conv.done


def test_lua_buttons_yes_jumps_no_ends():
    """buttons：yes 折成步名跳转，no 函数返回 nil 结束。"""
    conv, _ = compile_talk(10)
    conv.press("yes")
    assert conv.current().lines == ["到达。"]
    conv2, _ = compile_talk(10)
    conv2.press("no")
    assert conv2.done


def test_missing_talk_raises():
    """脚本没有 talk() → LookupError，供调用方回落。"""
    with pytest.raises(LookupError):
        Conversation.from_source("return {}", {}, {})
