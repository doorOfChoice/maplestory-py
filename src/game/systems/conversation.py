"""通用对话解释器：步骤图数据结构 + 导航引擎 + Lua talk() 编译。

对话 = 步骤图：每步 = 黑文本行 + 蓝字链接（show 显隐 / click 副作用+跳步，
返回 None 即结束）+ 可选 yes/no 按钮（值为步名或函数）。无链接无按钮 = 终态。
会话不持久化：每次开对话重新求值，所有条件天然是「此刻」的。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Union

# 按钮/链接的目标：步名字符串，或「执行副作用后返回步名/None」的函数
Target = Union[str, Callable[[], Optional[str]]]


@dataclass
class Link:
    """一条蓝字交互行。show/click 均为无参闭包（ctx 已被构造方捕获）。"""
    label: str
    note: int = 0                                     # 右侧 Lv 标注，0=不显示
    show: Callable[[], bool] = lambda: True
    click: Callable[[], Optional[str]] = lambda: None


@dataclass
class Step:
    """一个对话步骤。buttons 值为步名（str）或副作用函数（callable）。"""
    text: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    buttons: Dict[str, Target] = field(default_factory=dict)
    next: Optional[str] = None                        # 终态「确定」后的跳转


@dataclass
class ConversationDef:
    title: str
    start: str
    steps: Dict[str, Step]


@dataclass(frozen=True)
class Snapshot:
    """当前该显示什么（纯数据，UI 层消费）。links 为 (label, note) 元组。"""
    title: str
    lines: List[str]
    links: List[Tuple[str, int]]
    buttons: List[str]
    terminal: bool


class Conversation:
    """步骤图导航引擎。公开 seam：current / click_link / press / done。"""

    def __init__(self, defn: ConversationDef):
        self._def = defn
        self._step = defn.start
        self._done = False
        self._visible: List[Link] = []

    @property
    def done(self) -> bool:
        return self._done

    def current(self) -> Snapshot:
        step = self._def.steps[self._step]
        self._visible = [l for l in step.links if _safe_show(l.show)]
        keys = [k for k in ("yes", "no") if k in step.buttons]
        return Snapshot(self._def.title, list(step.text),
                        [(l.label, l.note) for l in self._visible], keys,
                        terminal=not step.links and not step.buttons)

    def click_link(self, index: int) -> None:
        if self._done:
            return
        self.current()  # 可见链接按「此刻」条件重新求值
        if index >= len(self._visible):
            return
        self._fire(self._visible[index].click)

    def press(self, key: str) -> None:
        """键盘/按钮路由：confirm(回车=确认) / close(Esc) / yes / no / ok。"""
        if self._done:
            return
        step = self._def.steps[self._step]
        if key == "confirm":
            if "yes" in step.buttons:
                self._fire(step.buttons["yes"])
            elif not step.links and not step.buttons:
                self._confirm_terminal()
        elif key == "close":
            if "no" in step.buttons:
                self._fire(step.buttons["no"])
            else:
                self._done = True
        elif key in step.buttons:
            self._fire(step.buttons[key])
        elif key == "ok":
            self._confirm_terminal()

    # ── 内部 ─────────────────────────────────────────────
    def _confirm_terminal(self) -> None:
        nxt = self._def.steps[self._step].next
        if nxt is not None and nxt in self._def.steps:
            self._step = nxt
        else:
            self._done = True

    def _fire(self, target: Target) -> None:
        ret: Optional[str]
        if callable(target):
            try:
                ret = target()
            except Exception:
                logging.warning("对话 click 异常，结束会话", exc_info=True)
                self._done = True
                return
        else:
            ret = target
        if ret is None or ret == "":
            self._done = True
        elif ret in self._def.steps:
            self._step = ret
        else:
            logging.warning("对话跳转到未知步骤: %s", ret)
            self._done = True


def _safe_show(fn: Callable[[], bool]) -> bool:
    try:
        return bool(fn())
    except Exception:
        logging.warning("对话链接 show 条件异常，隐藏该链接", exc_info=True)
        return False
