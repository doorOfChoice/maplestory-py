"""对话流脚本解释器：节点快照、条件过滤、选项推进、副作用、动态入口与转职脚本。"""
from __future__ import annotations

from types import SimpleNamespace

from game.core.jobs import JOBS
from game.systems.scripts import (
    DialogueScript, Node, Option, DialogueSession, build_advance_session,
)


def make_script() -> DialogueScript:
    actions: list = []

    def advance(ctx):
        actions.append(("advance", ctx))
        ctx.job = "bowman"
        return None

    goto_node = Option(label="yes", action=advance, next_id="result")
    no_node = Option(label="no", next_id="declined")
    return DialogueScript(
        entry="offer",
        nodes={
            "offer": Node(npc="赫丽娜", lines=["你想成为弓箭手吗？"],
                          options=[goto_node, no_node]),
            "result": Node(npc="赫丽娜", lines=["转职成功！"],
                           options=[Option(label="ok")]),
            "declined": Node(npc="赫丽娜", lines=["好吧，下次再来。"],
                             options=[Option(label="ok")]),
        },
    ), actions


def test_snapshot_returns_current_node():
    """快照返回当前节点的说话人/文本/模式与全部可用选项。"""
    script, _ = make_script()
    s = DialogueSession(script, SimpleNamespace())
    snap = s.snapshot()
    assert snap.npc == "赫丽娜"
    assert snap.lines == ["你想成为弓箭手吗？"]
    assert snap.mode == "quest"
    assert [o.label for o in snap.options] == ["yes", "no"]


def test_when_predicate_filters_options():
    """条件为假的选项从快照中剔除。"""
    script = DialogueScript(
        entry="n",
        nodes={"n": Node(npc="x", lines=["t"],
                         options=[Option(label="a", when=lambda c: True),
                                  Option(label="b", when=lambda c: False)])},
    )
    snap = DialogueSession(script, SimpleNamespace()).snapshot()
    assert [o.label for o in snap.options] == ["a"]


def test_choose_executes_action_and_advances():
    """选中选项执行其动作（突变上下文）并沿 next_id 前进。"""
    script, actions = make_script()
    ctx = SimpleNamespace(job="newbie")
    s = DialogueSession(script, ctx)
    assert s.choose("yes") is True
    assert ctx.job == "bowman"
    assert actions == [("advance", ctx)]
    assert s.snapshot().lines == ["转职成功！"]


def test_action_can_override_node():
    """动作返回的节点 id 优先于选项自身 next_id。"""
    actions = []

    def warped(ctx):
        actions.append("warped")
        return "result"

    script = DialogueScript(
        entry="n",
        nodes={
            "n": Node(npc="x", lines=["t"],
                      options=[Option(label="go", action=warped, next_id="other")]),
            "other": Node(npc="x", lines=["其他"], options=[Option(label="ok")]),
            "result": Node(npc="x", lines=["结果"], options=[Option(label="ok")]),
        },
    )
    s = DialogueSession(script, SimpleNamespace())
    s.choose("go")
    assert s.snapshot().lines == ["结果"]
    assert actions == ["warped"]


def test_choose_unknown_label_noop():
    """选中不存在的选项返回 False 且状态不变。"""
    script, _ = make_script()
    s = DialogueSession(script, SimpleNamespace())
    assert s.choose("bogus") is False
    assert s.snapshot().lines == ["你想成为弓箭手吗？"]


def test_terminal_node_ok_dismisses():
    """无选项的终态节点，按 ok 结束会话。"""
    script = DialogueScript(
        entry="end",
        nodes={"end": Node(npc="x", lines=["结束"])},
    )
    s = DialogueSession(script, SimpleNamespace())
    assert s.choose("ok") is True
    assert s.done is True
    assert s.choose("no") is False


# ── 转职脚本 ───────────────────────────────────────────────────────────

def fake_advancing_player(level: int, job: int = 0):
    calls = []

    def advance_to(code, assets):
        calls.append(code)

    return SimpleNamespace(level=level, job=job,
                           advance_to=advance_to, _calls=calls), calls


def test_advance_entry_resolves_by_player_state():
    """入口节点按玩家状态：可转职→confirm，已转职→already，不足→weak。"""
    jobdef = JOBS[3000]
    p, _ = fake_advancing_player(level=10, job=0)
    sess, ctx = build_advance_session(p, jobdef, "赫丽娜", None)
    assert sess.node_id == "confirm"
    assert [o.label for o in sess.snapshot().options] == ["yes", "no"]

    p2, _ = fake_advancing_player(level=30, job=3000)
    sess2, _ = build_advance_session(p2, jobdef, "赫丽娜", None)
    assert sess2.node_id == "already"

    p3, _ = fake_advancing_player(level=9, job=0)
    sess3, _ = build_advance_session(p3, jobdef, "赫丽娜", None)
    assert sess3.node_id == "weak"
    assert "Lv9" in sess3.snapshot().lines[1]


def test_advance_yes_changes_job_and_marks_advanced():
    """选 yes 触发转职（advance_to），ctx.advanced 置位，跳到 advanced 节点。"""
    jobdef = JOBS[3000]
    p, calls = fake_advancing_player(level=10, job=0)
    sess, ctx = build_advance_session(p, jobdef, "赫丽娜", None)
    assert sess.choose("yes") is True
    assert calls == [3000]
    assert ctx.advanced is True
    assert sess.snapshot().lines == ["恭喜！你已经转职为", "弓箭手了！"]


def test_advance_no_goes_declined():
    """选 no 进入 declined 节点，不转职。"""
    jobdef = JOBS[3000]
    p, calls = fake_advancing_player(level=10, job=0)
    sess, ctx = build_advance_session(p, jobdef, "赫丽娜", None)
    assert sess.choose("no") is True
    assert calls == []
    assert ctx.advanced is False
    assert sess.snapshot().lines == ["好吧，改变心意的话再来找我。"]
