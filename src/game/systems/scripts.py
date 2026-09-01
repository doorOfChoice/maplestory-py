"""对话流脚本：把 NPC 交互（寒暄/任务/转职/商店）编排成声明式节点图。

原版把 NPC 对话流程写在服务器脚本里、不随 WZ 下发；本项目因此以声明式数据
自建：每个 NPC 一段脚本，节点含文本与选项，条件/动作是对系统功能的封闭调用。
解释器（DialogueSession）按玩家上下文走图，产出「当前该显示什么」（Snapshot）
并触发副作用（对 ctx 的可变操作）；渲染由 game 层映射到原版 UI 组件。

本模块纯逻辑、不依赖 pygame/WZ，可用合成 ctx 单测。转职流程以
build_advance_session 生成的脚本表示 —— 新增/改转职只动数据，不碰 game.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Union

# 条件：给定上下文 → 该选项是否可选
Predicate = Callable[[Any], bool]
# 动作：执行副作用，返回可选的下一节点 id（None = 沿用选项 next_id）
Action = Callable[[Any], Optional[str]]
# 文本：固定字符串序列，或据上下文动态生成
Lines = Union[List[str], Callable[[Any], List[str]]]

# 节点模式 → 对应的原版 UI 组件（由 game 层映射）
MODE_DIALOG = "dialog"   # ChatBalloon 气泡（寒暄）
MODE_QUEST = "quest"     # UtilDlgEx 白纸窗（单任务/转职确认）
MODE_MENU = "menu"       # QuestAlarm 列表（多任务选择）


@dataclass(frozen=True)
class Option:
    label: str
    when: Predicate = lambda ctx: True
    action: Optional[Action] = None
    next_id: Optional[str] = None


@dataclass(frozen=True)
class Node:
    npc: str
    lines: Lines
    mode: str = MODE_QUEST
    options: List[Option] = field(default_factory=list)


@dataclass(frozen=True)
class DialogueScript:
    entry: Union[str, Callable[[Any], str]]      # 可据上下文动态选入口节点
    nodes: Dict[str, Node]


@dataclass(frozen=True)
class Snapshot:
    """当前会话该显示什么（纯数据，由 UI 层消费）。"""
    npc: str
    lines: List[str]
    mode: str
    options: List[Option]        # 仅当次语境下 when(ctx) 通过的选项


class DialogueSession:
    """一台运行中的对话流解释器。"""

    def __init__(self, script: DialogueScript, ctx: Any):
        self.script = script
        self.ctx = ctx
        entry = script.entry
        self.node_id = entry(ctx) if callable(entry) else entry
        self.done = False

    @property
    def node(self) -> Node:
        return self.script.nodes[self.node_id]

    def snapshot(self) -> Snapshot:
        node = self.node
        lines = node.lines(self.ctx) if callable(node.lines) else node.lines
        available = [o for o in node.options if o.when(self.ctx)]
        return Snapshot(node.npc, list(lines), node.mode, available)

    def choose(self, label: str) -> bool:
        """选中某选项：执行动作并沿 next_id 前进；终态节点按 ok 结束。"""
        node = self.node
        if not node.options:
            if label == "ok":
                self.done = True
                return True
            return False
        for o in node.options:
            if o.label != label or not o.when(self.ctx):
                continue
            nxt: Optional[str] = o.next_id
            if o.action is not None:
                ret = o.action(self.ctx)
                if isinstance(ret, str):
                    nxt = ret
            if nxt is None:
                nxt = self.node_id
            if nxt == self.node_id:
                self.done = True
            else:
                self.node_id = nxt
            return True
        return False


# ════════════════════════════════════════════════════════════════════
# 转职脚本工厂（advancement 流程数据化）
# ════════════════════════════════════════════════════════════════════

def build_advance_session(player, jobdef, npc_name: str, assets,
                          ) -> tuple["DialogueSession", Any]:
    """把「可转职 / 已是该职 / 等级不足」的转职对话建模成脚本会话。

    ``ctx`` 携带 player/jobdef/assets；动作转职成功后置 ctx.advanced，供调用方
    播放音效与提示。入口节点按玩家状态动态选择（entry 为可调用对象）。
    """
    from game.core.jobs import can_advance

    def check_entry(ctx) -> str:
        if ctx.player.job == ctx.jobdef.code:
            return "already"
        if can_advance(ctx.player, ctx.jobdef):
            return "confirm"
        return "weak"

    def do_advance(ctx) -> str:
        ctx.player.advance_to(ctx.jobdef.code, ctx.assets)
        ctx.advanced = True
        return "advanced"

    def weak_lines(ctx) -> List[str]:
        return ["你还太弱小了，达到等级再来找我吧。",
                f"（当前 Lv{ctx.player.level} / 需要 Lv{ctx.jobdef.advance_lv}）"]

    script = DialogueScript(
        entry=check_entry,
        nodes={
            "already": Node(npc_name, [f"你已经是一名出色的{jobdef.name}了。"]),
            "weak": Node(npc_name, weak_lines),
            "confirm": Node(npc_name, [
                f"你想成为{jobdef.name}吗？",
                f"达到 Lv{jobdef.advance_lv} 的新手可以转职为{jobdef.name}，",
                "转职后我会送你武器并教你该职业的技能。",
            ], options=[Option(label="yes", action=do_advance),
                        Option(label="no", next_id="declined")]),
            "declined": Node(npc_name, ["好吧，改变心意的话再来找我。"]),
            "advanced": Node(npc_name, ["恭喜！你已经转职为", f"{jobdef.name}了！"]),
        },
    )
    ctx = SimpleNamespace(player=player, jobdef=jobdef, assets=assets,
                          advanced=False)
    return DialogueSession(script, ctx), ctx
