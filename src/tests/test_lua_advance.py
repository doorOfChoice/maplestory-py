"""转职步骤图：advance.lua 以 talk(ctx) 驱动，验证路由/台词/选 yes 改真身。

透过公开 seam Conversation.from_source 测试；SimpleNamespace 假身，不用 mock。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from game import settings
from game.core.jobs import JOBS
from game.systems.conversation import Conversation, make_ctx_view
from game.systems.script_api import make_globals

pytest.importorskip("lupa")

_SRC = (settings.RESOURCE_DIR / "content" / "advance.lua").read_text("utf-8")


def fake_player(level: int, job: int = 0):
    calls: list = []

    def advance_to(code, assets):
        calls.append(code)

    return SimpleNamespace(level=level, job=job, advance_to=advance_to), calls


def _conv(level: int, job: int = 0):
    p, calls = fake_player(level, job)
    jobdef = JOBS[3000]
    host = SimpleNamespace(player=p, jobdef=jobdef, assets=None,
                           npc_name="赫丽娜", advanced=False)
    env = make_globals(host)
    ctx = make_ctx_view(p, "1012100", "赫丽娜", 100000000, jobdef=jobdef)
    return Conversation.from_source(_SRC, env, ctx), calls


def test_weak_player_gets_level_hint_terminal():
    """等级不足：weak 步终态，台词含等级提示。"""
    conv, _ = _conv(5)
    snap = conv.current()
    assert "太弱小" in snap.lines[0]
    assert snap.terminal


def test_confirm_step_has_yes_no_buttons():
    """可转职：confirm 步含职业名与 yes/no 按钮。"""
    conv, _ = _conv(10)
    snap = conv.current()
    assert snap.buttons == ["yes", "no"]
    assert "弓箭手" in "".join(snap.lines)


def test_yes_triggers_advance_and_shows_congrats():
    """选 yes：调 advance_to(3000)，切到恭喜步。"""
    conv, calls = _conv(10)
    conv.press("yes")
    assert calls == [3000]
    assert conv.current().lines[0] == "恭喜！你已转职为"


def test_no_goes_declined_step():
    """选 no：不转职，进拒绝文案。"""
    conv, calls = _conv(10)
    conv.press("no")
    assert calls == []
    assert "改变心意" in conv.current().lines[0]


def test_already_advanced_job_shows_plain_notice():
    """已是目标职业：单句陈述终态。"""
    conv, _ = _conv(10, job=3000)
    assert "已经是一名" in conv.current().lines[0]
