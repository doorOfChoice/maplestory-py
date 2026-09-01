"""Lua 转职会话：宿主加载 advance.lua，验证入口路由、快照文本与选 yes 触发 advance_job。

透过公开 seam build_lua_session 测试；用 SimpleNamespace 假身，不用 mock。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from game.core.jobs import JOBS
from game.systems.scripting import build_lua_session

pytest.importorskip("lupa")


def fake_player(level: int, job: int = 0):
    calls: list = []

    def advance_to(code, assets):
        calls.append(code)

    return SimpleNamespace(level=level, job=job,
                           advance_to=advance_to, _calls=calls), calls


def _session(level: int, job: int = 0):
    p, calls = fake_player(level, job)
    jobdef = JOBS[3000]
    sess, ctx = build_lua_session(
        "advance", player=p, jobdef=jobdef, npc_name="赫丽娜", assets=None)
    return sess, ctx, calls


def test_confirm_routing_shows_options():
    """可转职玩家路由到 confirm：台词含职业名，选项 yes/no。"""
    sess, _, _ = _session(10, 0)
    snap = sess.snapshot()
    assert snap.npc == "赫丽娜"
    assert snap.mode == "quest"
    assert "弓箭手" in snap.lines[0]
    assert [o.label for o in snap.options] == ["yes", "no"]


def test_already_routing_shows_a_statement():
    """已转职玩家路由到 already：单句说明，无选项。"""
    sess, _, _ = _session(30, 3000)
    snap = sess.snapshot()
    assert "弓箭手" in snap.lines[0]
    assert snap.options == []


def test_weak_routing_shows_level():
    """等级不足路由到 weak：提示当前/所需等级。"""
    sess, _, _ = _session(9, 0)
    lines = sess.snapshot().lines
    assert "Lv9" in lines[1]


def test_choose_yes_advances_and_marks_ctx():
    """confirm 下选 yes：调用 advance_to，ctx.advanced 置位，切到 advanced 态。"""
    sess, ctx, calls = _session(10, 0)
    assert sess.choose("yes") is True
    assert calls == [3000]
    assert ctx.advanced is True
    assert sess.done is False


def test_choose_no_goes_declined():
    """confirm 下选 no：不转职，进入 declined 文案。"""
    sess, ctx, calls = _session(10, 0)
    assert sess.choose("no") is True
    assert calls == []
    assert ctx.advanced is False
    assert sess.snapshot().lines == ["好吧，改变心意的话再来找我。"]


def test_choose_ok_dismisses_terminal():
    """终态按 ok：会话结束（done 为真）。"""
    sess, _, _ = _session(10, 0)
    sess.choose("yes")
    sess.choose("ok")
    assert sess.done is True
