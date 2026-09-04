"""通用对话解释器：步骤图数据结构 + 导航引擎 + Lua talk() 编译。

对话 = 步骤图：每步 = 黑文本行 + 蓝字链接（show 显隐 / click 副作用+跳步，
返回 None 即结束）+ 可选 yes/no 按钮（值为步名或函数）。无链接无按钮 = 终态。
会话不持久化：每次开对话重新求值，所有条件天然是「此刻」的。

链接按 type 判别：无 type（或 "link"）为手写链接（label/show/click 闭包）；
"quest"/"travel"/"shop" 为声明式链接，建模时由宿主按 ConvServices（任务表/
传送注册表/商店）展开成具体链接与终态步，脚本零闭包。会话顶层 `takeover`
策略（"always" 缺省 / "on_business" / 函数）决定「无生意时让位默认路由」。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

import lupa
from lupa import LuaRuntime

# 按钮/链接的目标：步名字符串，或「执行副作用后返回步名/None」的函数
Target = Union[str, Callable[[], Optional[str]]]


@dataclass
class ConvServices:
    """type 链接展开器需要的宿主数据源（开会话时由控制器注入）。"""
    quest_defs: Mapping[str, Any] = field(default_factory=dict)
    teleports: List[Tuple[str, str]] = field(default_factory=list)  # (label, map_id)
    has_shop: bool = False


@dataclass
class Link:
    """一条蓝字交互行。show/click 均为无参闭包（ctx 已被构造方捕获）。

    business=True：quest/travel 类链接——「玩家点 NPC 的理由」，
    全部隐藏时 on_business 会话让位给默认路由。
    """
    label: str
    note: int = 0                                     # 右侧 Lv 标注，0=不显示
    show: Callable[[], bool] = lambda: True
    click: Callable[[], Optional[str]] = lambda: None
    business: bool = False


@dataclass
class Step:
    """一个对话步骤。buttons 值为步名（str）或副作用函数（callable）。

    text_fn：Lua `text = function(ctx)` 的惰性求值闭包（spec §5：函数文本在
    current() 时刻求值，能读到点击产生的最新副作用）；None 时用静态 text。
    """
    text: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    buttons: Dict[str, Target] = field(default_factory=dict)
    next: Optional[str] = None                        # 终态「确定」后的跳转
    text_fn: Optional[Callable[[], List[str]]] = None


@dataclass
class ConversationDef:
    title: str
    start: str
    steps: Dict[str, Step]
    takeover: str = "always"      # always / on_business / never（函数式求值后折入）


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
                    ctx_view: dict, title: str = "",
                    services: Optional[ConvServices] = None) -> "Conversation":
        """编译 Lua 脚本的 talk(ctx) 步骤图为会话。

        每次开对话调用一次：沙箱加载脚本、注入宿主函数 env、实时求值
        talk() 并整体折成 Python 步骤结构（type 声明链接按 services 展开）。
        talk() 缺失或返回 nil 抛 LookupError，Lua 语法/运行时错误由 lupa
        抛出——本层不吞，调用方兜底。
        """
        lua = _sandbox()
        g = lua.globals()
        for name, fn in env.items():
            g[name] = _bind_host_fn(lua, fn)
        ctx_tbl = lua.table_from(ctx_view)
        mod = lua.execute(lua_src, "conversation")
        talk = mod["talk"]
        if talk is None:
            raise LookupError("脚本缺少 talk()")
        root = talk(ctx_tbl)
        if root is None:
            raise LookupError("talk() 返回 nil")
        return cls(_fold_conv(ctx_tbl, root, title, ctx_view, env, services))

    # ── 接管策略 ─────────────────────────────────────────
    def has_business(self) -> bool:
        """会话此刻是否存在「生意」：任一 business 链接可见。"""
        return any(_safe_show(l.show)
                   for s in self._def.steps.values()
                   for l in s.links if l.business)

    def yields_to_route(self) -> bool:
        """takeover 策略是否判定「无话可说，让位默认路由」（调用方回落）。"""
        if self._def.takeover == "never":
            return True
        if self._def.takeover == "on_business":
            return not self.has_business()
        return False

    @property
    def done(self) -> bool:
        return self._done

    def current(self) -> Snapshot:
        step = self._def.steps[self._step]
        lines = step.text_fn() if step.text_fn is not None else list(step.text)
        self._visible = [l for l in step.links if _safe_show(l.show)]
        keys = [k for k in ("yes", "no") if k in step.buttons]
        return Snapshot(self._def.title, lines,
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

# 沙箱里禁止的系统库/加载函数（与 lua_quests.py 保持一致）
_FORBIDDEN = ("os", "io", "package", "debug", "dofile", "loadfile")


def _sandbox() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    g = lua.globals()
    for name in _FORBIDDEN:
        g[name] = None
    return lua


def _bind_host_fn(lua: LuaRuntime, fn: Callable) -> Callable:
    """包一层宿主函数：list/dict 返回值折成 Lua 原生表再交给脚本。

    lupa 默认把返回的 Python 序列包成 POBJECT，Lua 侧 `#t` 直接报错、
    越界索引抛 IndexError；折表后 quest_available/quest_completable 等
    列表函数才真正可用。标量原样透传。
    """
    def wrapped(*args):
        return _to_lua_value(lua, fn(*args))
    return wrapped


def _to_lua_value(lua: LuaRuntime, value: Any) -> Any:
    if isinstance(value, dict):
        return lua.table_from({str(k): _to_lua_value(lua, v)
                               for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return lua.table_from([_to_lua_value(lua, v) for v in value])
    return value


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


def _fold_conv(ctx_tbl: Any, root: Any, fallback_title: str, ctx_view: dict,
               env: Dict[str, Callable],
               services: Optional[ConvServices]) -> ConversationDef:
    """把 talk() 返回的步骤图整体折成 ConversationDef（此后不再穿 Lua 遍历）。"""
    start = str(root["start"] or "")
    steps: Dict[str, Step] = {}
    st = root["steps"]
    if st is None:
        raise LookupError("talk() 缺少 steps")
    extra: Dict[str, Step] = {}                     # 展开器生成的终态步
    for name, s in st.items():
        steps[str(name)] = _fold_step(ctx_tbl, s, ctx_view, env, services, extra)
    for name, s in extra.items():
        steps.setdefault(name, s)                   # 脚本自带的同名步优先
    if not start:
        # Lua 表遍历顺序不定：缺省起点约定为 greet，否则取名字序第一个
        start = "greet" if "greet" in steps else min(steps)
    title = str(root["title"] or fallback_title)
    return ConversationDef(title, start, steps, _fold_takeover(ctx_tbl, root))


def _fold_takeover(ctx_tbl: Any, root: Any) -> str:
    """takeover 字段：字符串策略名，或函数（建模时求值一次 → always/never）。"""
    tv = root["takeover"]
    if tv is None:
        return "always"
    if _is_fn(tv):
        return "always" if bool(tv(ctx_tbl)) else "never"
    mode = str(tv)
    if mode not in ("always", "on_business"):
        logging.warning("未知 takeover 策略 %r，按 always 处理", mode)
        return "always"
    return mode


def _fold_step(ctx_tbl: Any, s: Any, ctx_view: dict, env: Dict[str, Callable],
               services: Optional[ConvServices],
               extra: Dict[str, Step]) -> Step:
    raw_text = s["text"]
    if _is_fn(raw_text):
        # 函数文本不在此刻求值：保留 lupa 引用，current() 时再穿 Lua
        text_fn = (lambda f: lambda: _fold_text(f(ctx_tbl)))(raw_text)
        text: List[str] = []
    else:
        text_fn, text = None, _fold_text(raw_text)
    links: List[Link] = []
    lt = s["links"]
    if lt is not None:
        for i in range(1, len(lt) + 1):
            l = lt[i]
            if l is None:
                continue
            ty = l["type"]
            kind = str(ty) if ty is not None else "link"
            if kind == "link":
                links.append(_fold_link(ctx_tbl, l))
            elif kind == "quest":
                links.extend(_expand_quest(l, ctx_view, env, services, extra))
            elif kind == "travel":
                links.extend(_expand_travel(l, ctx_view, env, services))
            elif kind == "shop":
                links.extend(_expand_shop(l, env, services))
            else:
                logging.warning("未知链接 type：%s，跳过", kind)
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
    return Step(text, links, buttons, str(nxt) if nxt else None, text_fn)


# ── type 链接展开器：按 ConvServices + 宿主函数生成具体链接/终态步 ──

_QUEST_ENV_FNS = ("quest_available", "quest_completable",
                  "accept_quest", "complete_quest")


def _expand_quest(item: Any, ctx_view: dict, env: Dict[str, Callable],
                  services: Optional[ConvServices],
                  extra: Dict[str, Step]) -> List[Link]:
    """{type="quest", qid} → 「接任务/交付」两条链接 + 四个终态步。

    显隐以 collect_npc_quests（已含 lvmin/prereq/进度判定）为唯一事实来源；
    终态文案取 QuestDef 的 Say 槽（accept_yes/complete_yes/complete_stop），
    缺省用兜底话术；busy 步脚本已定义则不覆盖。
    """
    if services is None:
        logging.warning("quest 链接缺少宿主 services，跳过")
        return []
    qid = str(item["qid"] or "")
    d = services.quest_defs.get(qid)
    if d is None:
        logging.warning("quest 链接引用未知任务：%s", qid)
        return []
    if any(fn not in env for fn in _QUEST_ENV_FNS):
        logging.warning("宿主未注册任务函数，quest 链接跳过：%s", qid)
        return []
    npc_id = ctx_view["npc"]["id"]
    avail, completable = env["quest_available"], env["quest_completable"]
    extra.setdefault(f"{qid}_accepted", Step(
        list(d.accept_yes) or [f"已接受任务「{d.name}」。"]))
    extra.setdefault(f"{qid}_rewarded", Step(
        list(d.complete_yes) or [f"已获得任务「{d.name}」的奖励！"]))
    extra.setdefault(f"{qid}_notyet", Step(
        list(d.complete_stop) or [f"「{d.name}」还未完成，继续努力吧！"]))
    extra.setdefault("busy", Step(["现在好像接不了，回头再看看你的等级吧。"]))

    def _offer_visible() -> bool:
        return any(str(e["qid"]) == qid and e.get("state") == "offer"
                   for e in avail(npc_id))

    def _complete_visible() -> bool:
        return any(str(e["qid"]) == qid for e in completable(npc_id))

    return [
        Link(f"接任务：{d.name}", int(d.lvmin), show=_offer_visible,
             click=lambda: f"{qid}_accepted" if env["accept_quest"](qid)
             else "busy",
             business=True),
        Link(f"交付：{d.name}", show=_complete_visible,
             click=lambda: f"{qid}_rewarded" if env["complete_quest"](qid)
             else f"{qid}_notyet",
             business=True),
    ]


def _expand_travel(item: Any, ctx_view: dict, env: Dict[str, Callable],
                   services: Optional[ConvServices]) -> List[Link]:
    """{type="travel"[, label]} → 目的地蓝字（剔当前图），点击登记切图并结束。"""
    if services is None or "teleport" not in env:
        logging.warning("travel 链接缺少宿主数据/teleport 函数，跳过")
        return []
    want = item["label"]
    dests = ([(lab, mid) for lab, mid in services.teleports
              if lab == str(want)] if want is not None
             else list(services.teleports))
    cur = str(ctx_view["player"]["map"])
    return [Link(lab, show=lambda mid=mid: str(mid) != cur,
                 click=lambda mid=mid: (env["teleport"](mid), None)[1],
                 business=True)
            for lab, mid in dests]


def _expand_shop(item: Any, env: Dict[str, Callable],
                 services: Optional[ConvServices]) -> List[Link]:
    """{type="shop"[, label]} → 开店入口（角色/情调，不算生意）。"""
    if services is None or not services.has_shop or "open_shop" not in env:
        logging.warning("shop 链接但本店无货架，跳过")
        return []
    lab = item["label"]
    return [Link(str(lab) if lab is not None else "商店",
                 click=lambda: (env["open_shop"](), None)[1])]


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


def _fold_text(tbl: Any) -> List[str]:
    """Lua 文本数组 → Python 行列表；nil 视为空。"""
    out: List[str] = []
    if tbl is None:
        return out
    for i in range(1, len(tbl) + 1):
        v = tbl[i]
        if v is not None:
            out.append(str(v))
    return out
