"""通用对话解释器：步骤图数据结构 + 导航引擎 + Lua talk() 编译。

对话 = 步骤图：每步 = 黑文本行 + 蓝字链接（show 显隐 / click 副作用+跳步，
返回 None 即结束）+ 可选 yes/no 按钮（值为步名或函数）。无链接无按钮 = 终态。
会话不持久化：每次开对话重新求值，所有条件天然是「此刻」的。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import lupa
from lupa import LuaRuntime

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
    """步骤图导航引擎。公开 seam：from_source / current / click_link / press / done。"""

    def __init__(self, defn: ConversationDef):
        self._def = defn
        self._step = defn.start
        self._done = False
        self._visible: List[Link] = []

    @classmethod
    def from_source(cls, lua_src: str, env: Dict[str, Callable],
                    ctx_view: dict, title: str = "") -> "Conversation":
        """编译 Lua 脚本的 talk(ctx) 步骤图为会话。

        每次开对话调用一次：沙箱加载脚本、注入宿主函数 env、实时求值
        talk() 并整体折成 Python 步骤结构。talk() 缺失或返回 nil 抛
        LookupError，Lua 语法/运行时错误由 lupa 抛出——本层不吞，调用方兜底。
        """
        lua = _sandbox()
        g = lua.globals()
        for name, fn in env.items():
            g[name] = fn
        ctx_tbl = lua.table_from(ctx_view)
        mod = lua.execute(lua_src, "conversation")
        talk = mod["talk"]
        if talk is None:
            raise LookupError("脚本缺少 talk()")
        root = talk(ctx_tbl)
        if root is None:
            raise LookupError("talk() 返回 nil")
        return cls(_fold_conv(ctx_tbl, root, title))

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


# ═══ Lua talk() 编译 ═══════════════════════════════════════════════

# 沙箱里禁止的系统库/加载函数（与 scripting.py / lua_quests.py 保持一致）
_FORBIDDEN = ("os", "io", "package", "debug", "dofile", "loadfile")


def _sandbox() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    g = lua.globals()
    for name in _FORBIDDEN:
        g[name] = None
    return lua


def make_ctx_view(player, npc_id, npc_name: str, map_id,
                  jobdef=None) -> dict:
    """宿主 ctx → 纯数据只读视图（不传真实对象进沙箱）。"""
    view = {
        "player": {"level": int(getattr(player, "level", 0)),
                   "job": int(getattr(player, "job", 0)),
                   "map": int(map_id or 0)},
        "npc": {"id": str(npc_id), "name": str(npc_name)},
    }
    if jobdef is not None:
        view["jobdef"] = {"code": jobdef.code, "name": jobdef.name,
                          "advance_lv": jobdef.advance_lv}
    return view


def _fold_conv(ctx_tbl: Any, root: Any, fallback_title: str) -> ConversationDef:
    """把 talk() 返回的步骤图整体折成 ConversationDef（此后不再穿 Lua 遍历）。"""
    start = str(root["start"] or "")
    steps: Dict[str, Step] = {}
    st = root["steps"]
    if st is None:
        raise LookupError("talk() 缺少 steps")
    for name, s in st.items():
        steps[str(name)] = _fold_step(ctx_tbl, s)
    if not start:
        start = next(iter(steps))
    title = str(root["title"] or fallback_title)
    return ConversationDef(title, start, steps)


def _fold_step(ctx_tbl: Any, s: Any) -> Step:
    text = _fold_text(s["text"], ctx_tbl)
    links: List[Link] = []
    lt = s["links"]
    if lt is not None:
        for i in range(1, len(lt) + 1):
            l = lt[i]
            if l is not None:
                links.append(_fold_link(ctx_tbl, l))
    buttons: Dict[str, Target] = {}
    bt = s["buttons"]
    if bt is not None:
        for key in ("yes", "no"):
            v = bt[key]
            if v is None:
                continue
            if _is_fn(v):
                buttons[key] = (lambda f: lambda: _ret(f(ctx_tbl)))(v)
            else:
                buttons[key] = str(v)
    nxt = s["next"]
    return Step(text, links, buttons, str(nxt) if nxt else None)


def _fold_link(ctx_tbl: Any, l: Any) -> Link:
    lab = l["label"]
    label = str(lab(ctx_tbl)) if _is_fn(lab) else str(lab or "")
    note = int(l["note"] or 0) if l["note"] is not None else 0
    show_f, click_f = l["show"], l["click"]
    show = (lambda f: lambda: bool(f(ctx_tbl)))(show_f) \
        if show_f is not None else (lambda: True)
    click = (lambda f: lambda: _ret(f(ctx_tbl)))(click_f) \
        if click_f is not None else (lambda: None)
    return Link(label, note, show, click)


def _ret(v: Any) -> Optional[str]:
    """Lua click/按钮函数的返回值折成 Python 目标：nil → None，其余转步名。"""
    return None if v is None else str(v)


def _is_fn(v: Any) -> bool:
    """lupa 2.x 的 table 同样可调用，判函数必须用 lua_type。"""
    return lupa.lua_type(v) == "function"


def _fold_text(raw: Any, ctx_tbl: Any) -> List[str]:
    tbl = raw(ctx_tbl) if _is_fn(raw) else raw
    out: List[str] = []
    if tbl is None:
        return out
    for i in range(1, len(tbl) + 1):
        v = tbl[i]
        if v is not None:
            out.append(str(v))
    return out
