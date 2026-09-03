"""任务对话适配层：QuestDef 的 Say 槽位折成通用步骤图。

官方任务与 Lua 自定义任务共用：接取（offer）/交付（complete）/进度提示（status）
三种子会话由 Python 构造 ConversationDef，副作用（accept/complete/音效/flash）
在按钮回调里执行——路由全在解释器，本模块只描述「这个任务该说什么」。
"""

from __future__ import annotations

from typing import Callable, List, Optional

from game.systems.conversation import Conversation, ConversationDef, Step
from game.systems.quests import QuestDef, QuestLog


def build_quest_conversation(qid: str, stage: str, *, d: QuestDef,
                             log: QuestLog, player, combat,
                             assets=None, audio=None,
                             notify: Callable[[str], None],
                             qmark: Callable[[str], str]) -> Conversation:
    """按 stage ∈ {offer, complete, status} 构造任务子会话。"""
    if stage == "offer":
        return _offer(qid, d, log, player, audio, notify, qmark)
    if stage == "complete":
        return _complete(qid, d, log, player, combat, assets, audio, notify, qmark)
    return _status(d, qmark)


def _lines(src: List[str], default: str, qmark: Callable[[str], str]) -> List[str]:
    """Say 槽有文本则逐行渲染标记，否则用缺省文案。"""
    return [qmark(l) for l in src] if src else [default]


def _offer(qid: str, d: QuestDef, log: QuestLog, player, audio,
           notify: Callable[[str], None],
           qmark: Callable[[str], str]) -> Conversation:
    def do_yes() -> Optional[str]:
        if not log.accept(qid, player):
            return None
        if audio is not None:
            audio.play("QuestClear", 0.5)
        notify(f"任务接受：{d.name}")
        return "accepted"

    steps = {
        "offer": Step(_lines(d.accept_lines, f"要接受任务「{d.name}」吗？", qmark),
                      buttons={"yes": do_yes, "no": "declined"}),
        "accepted": Step(_lines(d.accept_yes,
                                f"已接受任务「{d.name}」。按 Q 查看任务日志。", qmark)),
        "declined": Step(_lines(d.accept_no, "好吧，改变心意的话再来找我。", qmark)),
    }
    return Conversation(ConversationDef(f"任务 · {d.name}", "offer", steps))


def _complete(qid: str, d: QuestDef, log: QuestLog, player, combat, assets, audio,
              notify: Callable[[str], None],
              qmark: Callable[[str], str]) -> Conversation:
    def do_yes() -> Optional[str]:
        if not log.complete(qid, player, combat, assets=assets, audio=audio):
            return "stop"
        notify(f"任务完成：{d.name}")
        return "completed"

    steps = {
        "ask": Step(_lines(d.complete_lines,
                           f"已完成任务「{d.name}」的所有条件！要领取奖励吗？", qmark),
                    buttons={"yes": do_yes, "no": ""}),
        "completed": Step(_lines(d.complete_yes,
                                 f"已获得任务「{d.name}」的奖励！", qmark)),
        "stop": Step(_lines(d.complete_stop,
                            f"「{d.name}」还未完成，继续努力吧！", qmark)),
    }
    return Conversation(ConversationDef(f"任务完成 · {d.name}", "ask", steps))


def _status(d: QuestDef, qmark: Callable[[str], str]) -> Conversation:
    steps = {"s": Step(_lines(d.complete_stop,
                              f"「{d.name}」还未完成，继续努力吧！", qmark))}
    return Conversation(ConversationDef(d.name, "s", steps))
