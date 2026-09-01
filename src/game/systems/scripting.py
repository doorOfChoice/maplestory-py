"""Lua 宿主：把 content/*.lua 脚本跑成「一门会话状态机」，对接 Python 渲染层。

内容层（content/*.lua）负责声明对话流程与台词；本模块只做三件事：
1. 建一个沙箱 lupa 运行时（禁用 os/io/package/dofile/loadfile，内容为仓库内可信文本）；
2. 把宿主上下文（只读视图）与 script_api 提供的全局函数灌进去，加载模块并实例化会话；
3. 把 Lua 会话对外封装成 snapshot/choose/done 接口，game 层渲染与按钮路由不用改。

此处同时定义渲染契约 Option/Snapshot；仅依赖 lupa，按公开 seam 单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, List, Optional

import lupa
from lupa import LuaRuntime

from game import settings
from game.systems.script_api import make_globals

# 内容目录：resources/content/*.lua
_SCRIPT_DIR = settings.RESOURCE_DIR / "content"

# 沙箱里禁止的系统库/加载函数（内容脚本只需要 string/table/math/setmetatable 等）
_FORBIDDEN = ("os", "io", "package", "debug", "dofile", "loadfile")


@dataclass(frozen=True)
class Option:
    """会话即时可选的一个选项（内容脚本只给标签，路由由 Lua 决定）。"""
    label: str


@dataclass(frozen=True)
class Snapshot:
    """当前会话该显示什么（纯数据，由 UI 层消费）。"""
    npc: str
    lines: List[str]
    mode: str
    options: List[Option] = field(default_factory=list)


def _sandboxed_runtime() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    g = lua.globals()
    for name in _FORBIDDEN:
        g[name] = None
    return lua


def _ctx_view(ctx: Any) -> dict:
    """只读上下文视图：Lua 只能看到标量/嵌套表，拿不到真实对象引用。"""
    return {
        "player": {"level": getattr(ctx.player, "level", 0),
                   "job": getattr(ctx.player, "job", 0)},
        "jobdef": {"code": ctx.jobdef.code, "name": ctx.jobdef.name,
                   "advance_lv": ctx.jobdef.advance_lv},
        "npc_name": ctx.npc_name,
    }


def _as_array(tbl) -> List[str]:
    """把 Lua 的 1 起始数组折成 Python list；nil 视为空。"""
    out: List[str] = []
    if tbl is None:
        return out
    for i in range(1, len(tbl) + 1):
        out.append(tbl[i])
    return out


class LuaSession:
    """对一门 Lua 对话会话的封装：透过 snapshot/choose/done 与渲染层对接。

    每个会话各持一个独立运行时，避免全局函数闭包在会话间串扰。
    """

    def __init__(self, script_name: str, ctx: Any):
        self.ctx = ctx
        self.done = False
        self._lua = _sandboxed_runtime()
        g = self._lua.globals()
        for name, fn in make_globals(ctx).items():
            g[name] = fn
        ctx_tbl = self._lua.table_from(_ctx_view(ctx))
        src = (_SCRIPT_DIR / f"{script_name}.lua").read_text(encoding="utf-8")
        mod = self._lua.execute(src, script_name)
        self.session = mod["new"](ctx_tbl)

    def snapshot(self) -> Snapshot:
        snap = self.session["snapshot"](self.session)
        return Snapshot(
            snap["npc"],
            _as_array(snap["lines"]),
            snap["mode"] or "quest",
            [Option(label=str(o)) for o in _as_array(snap["options"])],
        )

    def choose(self, label: str) -> bool:
        self.session["choose"](self.session, label)
        self.done = bool(self.session["done"])
        return True

    @property
    def is_terminal(self) -> bool:
        return self.done


def build_lua_session(script_name: str, *, player, jobdef, npc_name: str,
                      assets: Optional[Any] = None, **extra) -> tuple["LuaSession", Any]:
    """依据内容脚本建一场 Lua 对话会话，并回传宿主上下文（含 advanced 标记）。"""
    ctx = SimpleNamespace(player=player, jobdef=jobdef, assets=assets,
                          npc_name=npc_name, advanced=False, **extra)
    return LuaSession(script_name, ctx), ctx
