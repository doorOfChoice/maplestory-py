"""任务接取/交付对话适配器：Say 槽位折进步骤图，副作用走 QuestLog。"""
from __future__ import annotations

from types import SimpleNamespace

from game.systems.quest_flow import build_quest_conversation
from game.systems.quests import QuestDef, QuestLog


def make_log(**kw):
    d = QuestDef(qid="7", name="打地兽", start_npc=1, end_npc=1,
                 lvmin=kw.get("lv", 10), kills=[(100101, 2)],
                 accept_lines=["接吗？"], accept_yes=["好。"], accept_no=["滚。"],
                 complete_lines=["交吗？"], complete_yes=["赏。"],
                 complete_stop=["还差。"])
    log = QuestLog({"7": d})
    return d, log


def fake_player():
    return SimpleNamespace(level=10, job=0,
                           inventory=SimpleNamespace(etcs={}, consumes={}),
                           gain_exp=lambda n: None)


def build(stage, d, log, player=None, combat=None, audio=None):
    notes: list = []
    conv = build_quest_conversation("7", stage, d=d, log=log,
                                    player=player or fake_player(),
                                    combat=combat or SimpleNamespace(meso=0),
                                    assets=None, audio=audio,
                                    notify=notes.append, qmark=lambda s: s)
    return conv, notes


def test_offer_shows_confirm_buttons_and_lines():
    d, log = make_log()
    conv, _ = build("offer", d, log)
    snap = conv.current()
    assert snap.lines == ["接吗？"]
    assert snap.buttons == ["yes", "no"]


def test_offer_yes_accepts_and_flashes():
    d, log = make_log()
    conv, notes = build("offer", d, log)
    conv.press("yes")
    assert log.is_accepted("7")
    assert notes == ["任务接受：打地兽"]
    assert conv.current().lines == ["好。"]
    assert conv.current().terminal


def test_offer_no_shows_decline():
    d, log = make_log()
    conv, _ = build("offer", d, log)
    conv.press("no")
    assert not log.started("7")
    assert conv.current().lines == ["滚。"]


def test_offer_yes_fails_condition_closes():
    """条件不足（等级不够）点 yes：不发 flash，直接结束。"""
    d, log = make_log(lv=50)
    conv, notes = build("offer", d, log)
    conv.press("yes")
    assert conv.done and notes == []


def test_complete_yes_grants_and_ends_flow():
    d, log = make_log()
    log.status["7"] = "accepted"
    log.kills["7"] = {100101: 2}
    conv, notes = build("complete", d, log)
    conv.press("yes")
    assert log.is_completed("7")
    assert notes == ["任务完成：打地兽"]
    assert conv.current().lines == ["赏。"]


def test_complete_without_progress_goes_stop_step():
    d, log = make_log()
    log.status["7"] = "accepted"
    log.kills["7"] = {100101: 1}
    conv, _ = build("complete", d, log)
    conv.press("yes")
    assert conv.current().lines == ["还差。"]
    assert not log.is_completed("7")


def test_status_stage_single_terminal_step():
    d, log = make_log()
    log.status["7"] = "accepted"
    conv, _ = build("status", d, log)
    snap = conv.current()
    assert snap.terminal and snap.lines == ["还差。"]
