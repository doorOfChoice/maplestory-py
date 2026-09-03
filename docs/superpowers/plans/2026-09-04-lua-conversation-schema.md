# Lua 声明式对话系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立统一的「步骤图」对话 schema：NPC 对话 = 黑文本行 + 蓝字链接（Lua 函数式 show/click）+ 可选 yes/no 按钮，转职/任务接交/出租车/商店入口全部收编进同一个 Python 解释器，Python 不再持有对话状态机与文案。

**Architecture:** 新增 `game/systems/conversation.py`（步骤图数据结构 + 导航引擎 + Lua `talk()` 编译器）与 `game/systems/quest_flow.py`（QuestDef Say 槽 → 步骤适配器）；`ui.py` 合并出单一渲染契约 `show_conv`；`npc_dialogue.py` 收拢为「一个 `Conversation` + 优先级路由」。设计依据见 spec。

**Tech Stack:** Python 3.12 / pygame / lupa（Lua 5.1 沙箱）/ pytest

**Spec:** `docs/superpowers/specs/2026-09-04-lua-conversation-schema-design.md`

## Global Constraints

- 每个 `.py` 顶部 `from __future__ import annotations`；注释/docstring 简体中文；行宽 ≤120
- 包内绝对导入（`from game.systems.conversation import ...`）；可变默认值用 `field(default_factory=...)`
- 测试：pytest（`uv run pytest`），无 mock 无 fixture，纯函数 + 模块层辅助函数，合成数据不依赖 WZ
- Lua 沙箱禁止 `os/io/package/debug/dofile/loadfile`（沿用 `_FORBIDDEN` 元组写法）
- 提交信息风格：`feat: 中文描述` / `refactor: …` / `test: …`；只 add 本任务涉及的文件
- 解释器**不持久化**：每次开对话重新构建 ctx 与会话；会话非模态、走远/Esc/切图即销毁

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `src/game/systems/conversation.py` | 新建 | `Link/Step/ConversationDef/Snapshot` 数据契约、`Conversation` 导航引擎、`Conversation.from_source` Lua 编译器、`make_ctx_view` |
| `src/game/systems/quest_flow.py` | 新建 | `build_quest_conversation`：QuestDef Say 槽 + QuestLog 副作用 → 步骤图 |
| `src/game/render/ui.py` | 修改 | `show_conv/conv_link_hit/conv_button_hit` 统一渲染；`show_quest/show_quest_list` 变薄壳 |
| `src/game/npc_dialogue.py` | 重写核心 | 单一 `_conv` 状态；`build_menu_conversation`（默认会话）；`talk()` 路径；删三套旧路由 |
| `src/game/systems/script_api.py` | 修改 | 新增 `teleport(map_id)` 全局（置 `ctx.pending_warp`）；jobdef 缺失时不注册转职函数 |
| `resources/content/advance.lua` | 重写 | 新 `talk(ctx)` 步骤图 |
| `resources/content/npc/reward_test.lua` | 重写 | 新 schema（单测专用） |
| `resources/content/npc/1012119.lua` | 修改 | 演示 `talk()`（任务+商店链接） |
| `src/tests/test_conversation.py` | 新建 | 引擎 + Lua 编译单测 |
| `src/tests/test_quest_flow.py` | 新建 | Say 槽适配器单测 |
| `src/tests/test_menu_conversation.py` | 新建 | 默认会话合成单测 |
| `src/tests/test_quest_list.py` | 修改 | 适配 show_conv 统一渲染 |
| `src/tests/test_lua_advance.py` / `test_lua_reward.py` | 重写 | 驱动新解释器 |
| `src/game/systems/scripting.py` | 删除 | LuaSession 旧契约退役 |
| `resources/content/AGENTS.md`、`AGENTS.md` | 修改 | 契约文档 |

---

### Task 1: 步骤图导航引擎（纯 Python，无 Lua）

**Files:**
- Create: `src/game/systems/conversation.py`
- Test: `src/tests/test_conversation.py`

**Interfaces:**
- Consumes: 无（本任务零依赖）
- Produces: `Link(label: str, note: int = 0, show: Callable[[], bool], click: Callable[[], Optional[str]])`、`Step(text: List[str], links: List[Link], buttons: Dict[str, str | Callable[[], Optional[str]]], next: Optional[str])`、`ConversationDef(title: str, start: str, steps: Dict[str, Step])`、`Snapshot(title, lines: List[str], links: List[Tuple[str, int]], buttons: List[str], terminal: bool)`、`Conversation(defn)`：`current()/click_link(i)/press(key)/done`

- [ ] **Step 1: 写失败测试（引擎行为）**

`src/tests/test_conversation.py`：

```python
"""步骤图对话引擎：show 过滤、click 跳步、nil 结束、buttons 路由、错误兜底。"""
from __future__ import annotations

import logging

from game.systems.conversation import (
    Conversation, ConversationDef, Link, Step)


def one_link_conv(click_ret, visible=True):
    """单步单链接的会话：click 返回 click_ret，show 返回 visible。"""
    step = Step(text=["黑文本"], links=[Link("蓝字", show=lambda: visible,
                                             click=lambda: click_ret)])
    return Conversation(ConversationDef("T", "s", {"s": step}))


def test_current_snapshot_lists_visible_links_and_text():
    """current() 返回黑文本 + 过滤后的蓝字（label,note 元组）。"""
    conv = one_link_conv("s")
    snap = conv.current()
    assert snap.title == "T"
    assert snap.lines == ["黑文本"]
    assert snap.links == [("蓝字", 0)]
    assert snap.buttons == []
    assert snap.terminal is False


def test_hidden_link_excluded_from_snapshot():
    """show 返回 False 的链接不进快照、不占点击序号。"""
    conv = one_link_conv("s", visible=False)
    assert conv.current().links == []


def test_click_jump_keeps_conversation_on_target_step():
    """click 返回步名 → 跳转到该步。"""
    steps = {"a": Step(links=[Link("go", click=lambda: "b")]),
             "b": Step(text=["到达"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    conv.click_link(0)
    assert not conv.done
    assert conv.current().lines == ["到达"]


def test_click_none_ends_conversation():
    """click 返回 None → 会话结束。"""
    conv = one_link_conv(None)
    conv.current()
    conv.click_link(0)
    assert conv.done


def test_click_unknown_step_ends_with_warning():
    """click 返回不存在的步名 → 结束（不崩溃）并记 warning。"""
    conv = one_link_conv("nope")
    conv.current()
    conv.click_link(0)
    assert conv.done


def test_click_raising_ends_conversation():
    """click 抛异常 → 结束会话，游戏不崩。"""
    def boom():
        raise RuntimeError("x")
    conv = Conversation(ConversationDef(
        "T", "s", {"s": Step(links=[Link("坏", click=boom)])}))
    conv.current()
    conv.click_link(0)
    assert conv.done


def test_show_raising_hides_only_that_link():
    """show 抛异常 → 仅该链接隐藏，其余正常。"""
    def boom():
        raise RuntimeError("x")
    step = Step(links=[Link("坏", show=boom), Link("好")])
    conv = Conversation(ConversationDef("T", "s", {"s": step}))
    assert [l for l, _ in conv.current().links] == ["好"]


def test_terminal_step_reports_terminal():
    """无链接无按钮的步骤 = 终态（渲染 BtOK，确认即结束）。"""
    conv = Conversation(ConversationDef("T", "s", {"s": Step(text=["完"])}))
    assert conv.current().terminal
    conv.press("confirm")
    assert conv.done


def test_press_confirm_fires_yes_button():
    """confirm（回车/空格/BtYes 命中）触发 buttons 里的 yes。"""
    steps = {"a": Step(text=["问"], buttons={"yes": "b", "no": "c"}),
             "b": Step(text=["好"]), "c": Step(text=["拒"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    snap = conv.current()
    assert snap.buttons == ["yes", "no"]
    conv.press("confirm")
    assert conv.current().lines == ["好"]


def test_press_close_fires_no_button():
    """close（Esc/BtNo 命中）触发 no 分支。"""
    steps = {"a": Step(buttons={"yes": "b", "no": "c"}),
             "b": Step(text=["好"]), "c": Step(text=["拒"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    conv.press("close")
    assert conv.current().lines == ["拒"]


def test_press_close_without_no_button_ends():
    """无 no 按钮时 Esc 直接结束会话。"""
    conv = Conversation(ConversationDef("T", "a", {"a": Step(text=["问"])}))
    conv.press("close")
    assert conv.done


def test_button_value_can_be_callable():
    """buttons 的值也可以是函数：副作用后返回步名。"""
    calls = []

    def do_yes():
        calls.append(1)
        return "b"
    steps = {"a": Step(buttons={"yes": do_yes}), "b": Step(text=["完"])}
    conv = Conversation(ConversationDef("T", "a", steps))
    conv.press("yes")
    assert calls == [1]
    assert conv.current().lines == ["完"]


def test_step_next_used_on_terminal_confirm():
    """终态步骤的 next 指向后续步（无 next 才结束）。"""
    steps = {"a": Step(text=["问"], buttons={"yes": "b"}),
             "b": Step(text=["谢"], next="a")}
    conv = Conversation(ConversationDef("T", "b", steps))
    conv.press("confirm")
    assert not conv.done
    assert conv.current().lines == ["问"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest src/tests/test_conversation.py -v`
Expected: FAIL（`ModuleNotFoundError: game.systems.conversation`）

- [ ] **Step 3: 实现引擎**

`src/game/systems/conversation.py`（本任务只写数据契约与引擎，Lua 编译在 Task 2 补进同一文件）：

```python
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
        if self._done or index >= len(self._visible):
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest src/tests/test_conversation.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/game/systems/conversation.py src/tests/test_conversation.py
git commit -m "feat: 步骤图对话解释器（show 过滤/click 跳步/按钮路由/错误兜底）"
```

---

### Task 2: Lua `talk()` 编译器（`Conversation.from_source`）

**Files:**
- Modify: `src/game/systems/conversation.py`（文件末尾追加编译层）
- Test: `src/tests/test_conversation.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `Link/Step/ConversationDef/Conversation`
- Produces: `Conversation.from_source(lua_src: str, env: Dict[str, Callable], ctx_view: Dict, title: str = "") -> Conversation`（`talk()` 缺失/加载失败抛 `LookupError`/`lupa.LuaError`，由调用方兜底）；`make_ctx_view(player, npc_id, npc_name, map_id, jobdef=None) -> dict`（形如 `{"player": {level, job, map}, "npc": {id, name}, "jobdef"?: {...}}`）；Lua 侧步骤字段：`text`（数组或 function(ctx)）、`links[].label`（string 或 function(ctx)）、`links[].show/click = function(ctx)`、`buttons = {yes=步名|function, no=...}`、`next`

- [ ] **Step 1: 写失败测试**

在 `test_conversation.py` 追加（文件头 `import pytest`、`pytest.importorskip("lupa")` 放文件级；辅助函数）：

```python
_TALK_LUA = """
local M = {}
function M.talk(ctx)
  return {
    title = "托德",
    start = "greet",
    steps = {
      greet = {
        text = function(c)
          return { "等级 " .. c.player.level, "静态行" }
        end,
        links = {
          { label = "接任务",
            show = function(c) return c.player.level >= 10 end,
            click = function(c) return "after" end },
          { label = function(c) return "动态蓝字 " .. c.npc.name end,
            click = function(c) take_item(c.player.level) return nil end },
        },
        buttons = { yes = "after", no = function(c) return nil end },
      },
      after = { text = { "到达。" }, next = "greet" },
    },
  }
end
return M
"""


def compile_talk(level=10, env=None):
    calls = []
    env = env or {"take_item": lambda n: calls.append(n)}
    ctx = make_ctx_view(SimpleNamespace(level=level, job=0),
                        "1012119", "托德", 100000000)
    conv = Conversation.from_source(_TALK_LUA, env, ctx)
    return conv, calls


def test_lua_talk_compiles_steps():
    """talk() 步骤图折进引擎：文本（函数式插值）、按钮、next。"""
    conv, _ = compile_talk(10)
    snap = conv.current()
    assert snap.title == "托德"
    assert snap.lines == ["等级 10", "静态行"]
    assert snap.buttons == ["yes", "no"]
    assert snap.terminal is False


def test_lua_link_show_filters_by_ctx():
    """链接 show 读 ctx：等级不足时隐藏。"""
    conv, _ = compile_talk(level=5)
    assert [l for l, _ in conv.current().links] == ["动态蓝字 托德"]


def test_lua_link_click_jumps_step():
    """Lua click 返回步名 → 跳转。"""
    conv, _ = compile_talk(10)
    conv.current()
    conv.click_link(0)
    assert conv.current().lines == ["到达。"]
    conv.press("confirm")           # after 的 next = greet → 回首步
    assert not conv.done


def test_lua_click_nil_and_env_side_effect():
    """Lua click 调宿主函数并返回 nil → 副作用发生、会话结束。"""
    conv, calls = compile_talk(10)
    conv.current()
    conv.click_link(1)
    assert calls == [10]
    assert conv.done


def test_lua_buttons_yes_jumps_no_ends():
    """buttons：yes 折成步名跳转，no 函数返回 nil 结束。"""
    conv, _ = compile_talk(10)
    conv.press("yes")
    assert conv.current().lines == ["到达。"]
    conv2, _ = compile_talk(10)
    conv2.press("no")
    assert conv2.done


def test_missing_talk_raises():
    """脚本没有 talk() → LookupError，供调用方回落。"""
    with pytest.raises(LookupError):
        Conversation.from_source("return {}", {}, {})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest src/tests/test_conversation.py -v`
Expected: 新增用例 FAIL（`from_source` / `make_ctx_view` 不存在）

- [ ] **Step 3: 实现编译层**

在 `conversation.py` 顶部补导入 `import lupa` / `from lupa import LuaRuntime`，末尾追加：

```python
# ═══ Lua talk() 编译 ═══════════════════════════════════════════════

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


def _fold_conv(lua: LuaRuntime, ctx_tbl, root, fallback_title: str) -> ConversationDef:
    start = str(root["start"] or "")
    steps: Dict[str, Step] = {}
    st = root["steps"]
    if st is None:
        raise LookupError("talk() 缺少 steps")
    for name, s in st.items():
        steps[str(name)] = _fold_step(lua, ctx_tbl, s)
    if not start:
        start = next(iter(steps))
    title = str(root["title"] or fallback_title)
    return ConversationDef(title, start, steps)


def _fold_step(lua: LuaRuntime, ctx_tbl, s) -> Step:
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
            buttons[key] = (lambda f: lambda: _ret(f(ctx_tbl)))(v) \
                if callable(v) else str(v)
    nxt = s["next"]
    return Step(text, links, buttons, str(nxt) if nxt else None)


def _fold_link(ctx_tbl, l) -> Link:
    lab = l["label"]
    if callable(lab):
        label = str(lab(ctx_tbl))
    else:
        label = str(lab or "")
    note = int(l["note"] or 0) if l["note"] is not None else 0
    show_f, click_f = l["show"], l["click"]
    show = (lambda f: lambda: bool(f(ctx_tbl)))(show_f) if show_f is not None \
        else (lambda: True)
    click = (lambda f: lambda: _ret(f(ctx_tbl)))(click_f) if click_f is not None \
        else (lambda: None)
    return Link(label, note, show, click)


def _ret(v) -> Optional[str]:
    return None if v is None else str(v)


def _fold_text(raw, ctx_tbl) -> List[str]:
    tbl = raw(ctx_tbl) if callable(raw) else raw
    out: List[str] = []
    if tbl is None:
        return out
    for i in range(1, len(tbl) + 1):
        v = tbl[i]
        if v is not None:
            out.append(str(v))
    return out


# 绑定到类上：Conversation.from_source(...)
def _from_source(cls, lua_src: str, env: Dict[str, Callable],
                 ctx_view: dict, title: str = "") -> "Conversation":
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
    return cls(_fold_conv(lua, ctx_tbl, root, title))


Conversation.from_source = classmethod(_from_source)
```

> 注：`Conversation.from_source = classmethod(...)` 是过渡写法不好看；直接把 `_from_source` 的函数体作为 `Conversation` 类内的 `@classmethod from_source` 定义、把 `_fold_*` 放模块级亦可——**实现时采用类内 classmethod 版本**，此处给出的是等价代码。测试行为以此为准。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest src/tests/test_conversation.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/game/systems/conversation.py src/tests/test_conversation.py
git commit -m "feat: Lua talk() 步骤图编译进对话解释器"
```

---

### Task 3: UI 统一渲染契约 `show_conv`

**Files:**
- Modify: `src/game/render/ui.py:94-200`（任务对话框状态/接口）、`src/game/render/ui.py:528-612`（draw_quest/_draw_quest_list）
- Test: `src/tests/test_quest_list.py`（追加），现有三个几何用例保持通过

**Interfaces:**
- Consumes: 无 Lua/解释器依赖（纯 UI）
- Produces:
  - `UI.show_conv(title: str, lines: List[str], links: List[Tuple[str, int]], buttons: List[str], terminal: bool)`
  - `UI.conv_link_hit(pos) -> Optional[int]`、`UI.conv_button_hit(pos) -> Optional[str]`（"yes"/"no"/"ok"）
  - `show_quest(title, lines, buttons)` 与 `show_quest_list(title, entries)` 重写为 `show_conv` 薄壳（语义不变，旧调用方零改动）；`quest_hit/quest_list_hit` 保留为别名
  - 状态字段：`quest_lines: List[str]`、`quest_links: List[Tuple[str, int]]`、`quest_button_keys: List[str]`、`quest_terminal: bool`（取代 `quest_entries/_quest_buttons_keys`）

- [ ] **Step 1: 写失败测试**

`test_quest_list.py` 追加：

```python
def test_show_conv_body_counts_lines_and_links():
    """正文行数与蓝字行数共同决定面板高度（同一面板共存）。"""
    ui = UI(FakeAssets())
    ui.show_conv("T", ["a", "b"], [("l1", 0), ("l2", 5)], [], False)
    surface = pygame.Surface((960, 540), pygame.SRCALPHA)
    ui.draw_quest(surface)
    # 2 黑行 + 2 蓝字行：比只有黑行时高出 2 个 LIST_ROW_H
    only_lines = UI(FakeAssets())
    only_lines.show_conv("T", ["a", "b"], [], [], False)
    only_lines.draw_quest(pygame.Surface((960, 540), pygame.SRCALPHA))
    assert ui.quest_rect.height == only_lines.quest_rect.height + 2 * LIST_ROW_H


def test_conv_link_hit_returns_index():
    """点击蓝字行区域 → 返回链接序号；空白处 None。"""
    ui = UI(FakeAssets())
    ui.show_conv("T", [], [("l1", 0), ("l2", 0)], [], False)
    ui.draw_quest(pygame.Surface((960, 540), pygame.SRCALPHA))
    rect0, idx0 = ui.quest_entry_rects[0]
    assert ui.conv_link_hit((rect0.centerx, rect0.centery)) == 0
    outside = (ui.quest_rect.centerx, ui.quest_rect.y + 3)
    assert ui.conv_link_hit(outside) is None


def test_show_quest_and_list_delegate_to_conv():
    """旧接口语义折进统一状态：show_quest 只有按钮、show_quest_list 只有链接。"""
    ui = UI(FakeAssets())
    ui.show_quest("Q", ["台词"], ["yes", "no"])
    assert ui.quest_lines == ["台词"] and ui.quest_links == []
    assert ui.quest_button_keys == ["yes", "no"] and not ui.quest_terminal
    ui.show_quest_list("M", [("任务", 10)])
    assert ui.quest_links == [("任务", 10)] and ui.quest_button_keys == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest src/tests/test_quest_list.py -v`
Expected: 新用例 FAIL（`show_conv` 不存在）；旧用例 PASS

- [ ] **Step 3: 实现**

`ui.py` 中任务对话框区块（`# ── 任务对话框 ──`）替换为：

```python
    def show_conv(self, title: str, lines: List[str],
                  links: List[Tuple[str, int]], buttons: List[str],
                  terminal: bool) -> None:
        """统一会话面板：黑正文行 + 蓝字链接行（(label, Lv 标注)）+ 按钮。

        buttons 为 ["yes","no"] 子集；terminal 时画 BtOK。
        """
        self.quest_visible = True
        self.quest_title = title
        self.quest_lines = list(lines)
        self.quest_links = list(links)
        self.quest_button_keys = [b for b in buttons if b in ("yes", "no")]
        self.quest_terminal = terminal
        self.quest_buttons = []
        self.quest_entry_rects = []

    def show_quest(self, title: str, lines: List[str],
                   buttons: Optional[List[str]] = None) -> None:
        bs = list(buttons or ["ok"])
        self.show_conv(title, lines, [], [b for b in bs if b != "ok"], "ok" in bs)

    def show_quest_list(self, title: str, entries: List[Tuple[str, int]]) -> None:
        self.show_conv(title, [], entries, [], False)

    def conv_link_hit(self, pos) -> Optional[int]:
        if not self.quest_visible:
            return None
        for rect, idx in self.quest_entry_rects:
            if rect.collidepoint(pos):
                return idx
        return None

    def conv_button_hit(self, pos) -> Optional[str]:
        if not self.quest_visible:
            return None
        for rect, key in self.quest_buttons:
            if rect.collidepoint(pos):
                return key
        return None

    # 兼容别名（迁移完成后可删）
    quest_hit = conv_button_hit
    quest_list_hit = conv_link_hit
```

`draw_quest` 与 `_draw_quest_list` 合并为单一 `_draw_conv`（`draw_quest` 只留一行转发）。绘制规则：

1. 高度：`body_h = max(70, LIST_PAD_TOP + len(wrapped) * DLG_LINE_H + LINK_BLOCK + LIST_PAD_BOTTOM)`，`wrapped` 为 `quest_lines` 按 `DLG_TEXT_W` 折行；`LINK_BLOCK = len(quest_links) * LIST_ROW_H + (6 if wrapped and quest_links else 0)`
2. 标题金色（同现状）；黑文本行 `DLG_LINE_H` 逐行下移；蓝字行用现有 `quest_list_row_rects(...)` 的画法（起点 = 标题+黑文本之后，行高 `LIST_ROW_H`，悬停高亮 `QUEST_LIST_BLUE_HOVER`、右侧 `Lv n` 灰标注当 note>0）
3. 按钮行：`reversed(quest_button_keys + (["ok"] if quest_terminal else []))` 起，沿用现 `draw_quest` 的 BtYes/BtNo/BtOK 贴图与叠放算法（先画的在最右），命中矩形存 `quest_buttons`

同步 `hide_quest()`：清 `quest_lines/quest_links/quest_button_keys/quest_terminal`（替代旧 `quest_entries/_quest_buttons_keys` 的引用点）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest src/tests/test_quest_list.py src/tests/test_taxi.py -v && uv run pytest -x -q`
Expected: 全部 PASS（旧调用方经薄壳不受影响）

- [ ] **Step 5: 提交**

```bash
git add src/game/render/ui.py src/tests/test_quest_list.py
git commit -m "feat: UI 会话面板统一黑文本与蓝字链接（show_conv）"
```

---

### Task 4: 任务 Say 槽适配器 `quest_flow.py`

**Files:**
- Create: `src/game/systems/quest_flow.py`
- Test: `src/tests/test_quest_flow.py`

**Interfaces:**
- Consumes: Task 1 `Conversation/ConversationDef/Step/Link`；`quests.QuestDef/QuestLog`
- Produces: `build_quest_conversation(qid: str, stage: str, *, d: QuestDef, log: QuestLog, player, combat, assets, audio=None, notify: Callable[[str, None]], qmark: Callable[[str], str]) -> Conversation`，stage ∈ `{"offer","complete","status"}`；副作用（发奖/音效/flash）在回调里执行，`notify` 收 flash 文本

- [ ] **Step 1: 写失败测试**

`src/tests/test_quest_flow.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest src/tests/test_quest_flow.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`src/game/systems/quest_flow.py`：

```python
"""任务对话适配层：QuestDef 的 Say 槽位折成通用步骤图。

官方任务与 Lua 自定义任务共用：接取（offer）/交付（complete）/进度提示（status）
三种子会话由 Python 构造 ConversationDef，副作用（accept/complete/音效/flash）
在按钮回调里执行——路由全在解释器，本模块只描述「这个任务该说什么」。
"""

from __future__ import annotations

from typing import Callable, Optional

from game.systems.conversation import Conversation, ConversationDef, Step
from game.systems.quests import QuestDef, QuestLog


def build_quest_conversation(qid: str, stage: str, *, d: QuestDef,
                             log: QuestLog, player, combat,
                             assets=None, audio=None,
                             notify: Callable[[str], None],
                             qmark: Callable[[str], str]) -> Conversation:
    if stage == "offer":
        return _offer(qid, d, log, player, audio, notify, qmark)
    if stage == "complete":
        return _complete(qid, d, log, player, combat, audio, notify, qmark)
    return _status(d, qmark)


def _lines(src, default, qmark):
    return [qmark(l) for l in src] if src else [default]


def _offer(qid, d, log, player, audio, notify, qmark) -> Conversation:
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


def _complete(qid, d, log, player, combat, audio, notify, qmark) -> Conversation:
    def do_yes() -> Optional[str]:
        if not log.complete(qid, player, combat, assets=None, audio=audio):
            return "stop"
        notify(f"任务完成：{d.name}")
        return "completed"

    steps = {
        "ask": Step(_lines(d.complete_lines,
                           f"已完成任务「{d.name}」的所有条件！要领取奖励吗？", qmark),
                    buttons={"yes": do_yes, "no": None or ""}),
        "completed": Step(_lines(d.complete_yes, f"已获得任务「{d.name}」的奖励！", qmark)),
        "stop": Step(_lines(d.complete_stop, f"「{d.name}」还未完成，继续努力吧！", qmark)),
    }
    return Conversation(ConversationDef(f"任务完成 · {d.name}", "ask", steps))


def _status(d: QuestDef, qmark) -> Conversation:
    steps = {"s": Step(_lines(d.complete_stop,
                              f"「{d.name}」还未完成，继续努力吧！", qmark))}
    return Conversation(ConversationDef(d.name, "s", steps))
```

注意 `"no": None or ""` 直接写 `""`（表示点 No 结束，`_fire` 对空串结束会话）。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest src/tests/test_quest_flow.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/game/systems/quest_flow.py src/tests/test_quest_flow.py
git commit -m "feat: 任务接取/交付对话折进步骤图（Say 槽位适配器）"
```

---

### Task 5: 默认会话合成（选择菜单 + 出租车 + 商店入口收编）

**Files:**
- Modify: `src/game/npc_dialogue.py`（新增模块级 `build_menu_conversation`；重写路由/点击/按键/清理/距离收起）
- Modify: `src/game/systems/quest_flow.py` 不需要改动
- Test: `src/tests/test_menu_conversation.py`（新）；`src/tests/test_taxi.py`、`src/tests/test_npc_quests.py` 保持

**Interfaces:**
- Consumes: Task 1 引擎；`quests.collect_npc_quests/NpcQuest`；`travel.teleports_of`；`shop.shops_of`
- Produces:
  - `npc_dialogue.build_menu_conversation(npc_name: str, map_id: str, quests: List[NpcQuest], teleports: List[Tuple[str, str]], accepted: List[NpcQuest], has_shop: bool, *, on_quest: Callable[[NpcQuest], None], on_teleport: Callable[[str], None], on_shop: Callable[[], None]) -> Conversation`（`on_*` 只登记意图并返回 None → 链接点击即结束本菜单会话，由控制器消费意图）
  - 控制器新状态：`self._conv`（唯一对话状态）与 `self._conv_npc/self._conv_host/self._conv_qid`；`_quest_flow/_menu_items/_menu_npc/_begin_quest_flow/_open_choice_menu/_show_quest_offer/_show_quest_complete/_show_quest_status/_quest_button/_quest_flow` 全部删除

- [ ] **Step 1: 写失败测试**

`src/tests/test_menu_conversation.py`：

```python
"""默认会话合成：可交付在前、可接、进行中、传送（剔当前图）、商店链接。"""
from __future__ import annotations

from game.npc_dialogue import build_menu_conversation
from game.systems.quests import NpcQuest


def build(quests=(), dests=(), accepted=(), has_shop=False):
    hit = {"quest": [], "teleport": [], "shop": []}
    conv = build_menu_conversation(
        "托德", "100000000", list(quests), list(dests), list(accepted), has_shop,
        on_quest=lambda q: hit["quest"].append(q.qid),
        on_teleport=lambda m: hit["teleport"].append(m),
        on_shop=lambda: hit["shop"].append(1),
    )
    return conv, hit


def q(qid, state, title=None, level=0):
    return NpcQuest(qid=qid, title=title or qid, level=level, state=state)


def test_menu_link_order_completes_first_then_offers_then_accepted():
    conv, _ = build(quests=[q("a", "offer"), q("b", "complete")],
                    accepted=[q("c", "accepted")])
    labels = [l for l, _ in conv.current().links]
    assert labels == ["b", "a", "c"]


def test_menu_excludes_current_map_teleport():
    conv, _ = build(dests=[("射手村", "100000000"), ("魔法密林", "101000000")])
    assert [l for l, _ in conv.current().links] == ["魔法密林"]


def test_menu_shop_link_appended_last():
    conv, hit = build(quests=[q("a", "offer")], has_shop=True)
    assert conv.current().links[-1] == ("商店", 0)
    conv.current()
    conv.click_link(len(conv.current().links) - 1)
    assert hit["shop"] == [1]


def test_click_quest_link_fires_hook_and_ends_menu():
    conv, hit = build(quests=[q("a", "offer", level=10)])
    assert conv.current().links == [("a", 10)]
    conv.click_link(0)
    assert hit["quest"] == ["a"]
    assert conv.done


def test_click_teleport_fires_hook_with_map():
    conv, hit = build(dests=[("魔法密林", "101000000")])
    conv.click_link(0)
    assert hit["teleport"] == ["101000000"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest src/tests/test_menu_conversation.py -v`
Expected: FAIL（`build_menu_conversation` 不存在）

- [ ] **Step 3: 实现 builder 并重写控制器**

`npc_dialogue.py` 中删除 `NpcTeleport` 数据类、`_menu_items/_menu_npc` 状态、`_open_choice_menu/_close_menu/_begin_quest_flow`，新增模块级函数：

```python
def build_menu_conversation(npc_name: str, map_id: str,
                            quests: List[NpcQuest],
                            teleports: List[Tuple[str, str]],
                            accepted: List[NpcQuest],
                            has_shop: bool, *,
                            on_quest: Callable[[NpcQuest], None],
                            on_teleport: Callable[[str], None],
                            on_shop: Callable[[], None]) -> Conversation:
    """无 talk() 脚本 NPC 的默认会话：任务/进行中/传送/商店合一张蓝字列表。"""
    links: List[Link] = []
    for item in quests:
        links.append(Link(item.title, item.level,
                          click=lambda it=item: _intent(on_quest, it)))
    for item in accepted:
        links.append(Link(f"{item.title}（进行中）", item.level,
                          click=lambda it=item: _intent(on_quest, it)))
    for label, mid in teleports:
        if str(mid) == str(map_id):
            continue
        links.append(Link(label, click=lambda m=mid: _intent(on_teleport, m)))
    if has_shop:
        links.append(Link("商店", click=lambda: _intent(on_shop, None)))
    title = npc_name if quests or accepted else f"{npc_name} · 要去哪里？"
    steps = {"menu": Step(links=links)}
    return Conversation(ConversationDef(title, "menu", steps))


def _intent(fn, arg) -> None:
    fn(arg)
    return None
```

控制器改为单一 `_conv`（本任务先只接「默认会话 → 任务子会话」这条链，`talk()` 在 Task 6 接入后成为最高优先级）：

```python
    def try_talk(self) -> None:
        for npc in self.ctx.world.npcs:
            if not npc.rect().colliderect(...):        # 判定框不变
                continue
            qlist = collect_npc_quests(self.quest_defs,
                                       self.ctx.world.player.quests,
                                       str(npc.npc_id), self.ctx.world.player)
            dests = travel.teleports_of(npc.npc_id, self.ctx.assets.map_id)
            in_progress = self._accepted_at(npc)
            has_shop = bool(shops_of(npc.npc_id))
            if qlist or dests or in_progress:
                conv = build_menu_conversation(
                    npc.name, str(self.ctx.assets.map_id), qlist, dests,
                    in_progress, has_shop,
                    on_quest=lambda it: self._open_quest_conv(npc, it),
                    on_teleport=self._request_warp, on_shop=self._request_shop)
                self._set_conv(conv, npc)
                return
            if has_shop:
                self.ctx.storage_panel.close()
                self.ctx.shop_panel.open(npc.npc_id)
                return
            # 寒暄气泡（原逻辑不变）
            ...

    def _open_quest_conv(self, npc, item: NpcQuest) -> None:
        """任务链接 → 子会话；Lua 驱动任务（d.script）在 Task 6 接入。"""
        d = self.quest_defs.get(item.qid)
        if d is None:
            return
        if d.script:
            self._open_script_conv(npc, item.qid, d.script)   # Task 6 实现
            return
        if item.state == "accepted":
            stage = "status"
        else:
            stage = item.state            # offer / complete
        conv = build_quest_conversation(
            item.qid, stage, d=d, log=self.ctx.world.player.quests,
            player=self.ctx.world.player, combat=self.ctx.world.combat,
            assets=self.assets, audio=self.ctx.audio,
            notify=self.ctx.panels.flash, qmark=self._qmark)
        self._set_conv(conv, npc)
```

意图登记（传送/商店）与统一善后：

```python
    def _request_warp(self, map_id: str) -> None:
        self._next_warp = map_id

    def _request_shop(self) -> None:
        self._next_shop = True

    def _after_turn(self) -> None:
        if self._next_warp:
            w, self._next_warp = self._next_warp, None
            self._close_conv()
            if self.warp is not None:
                self.warp(w)
            return
        if self._next_shop:
            self._next_shop = None
            npc = self._conv_npc
            self._close_conv()
            self.ctx.storage_panel.close()
            self.ctx.shop_panel.open(npc.npc_id)
            return
        host = self._conv_host
        if host is not None and getattr(host, "pending_warp", None):
            w = host.pending_warp
            host.pending_warp = None
            self._close_conv()
            if self.warp is not None:
                self.warp(w)
            return
        if self._conv is not None and self._conv.done:
            self._finish_conv()
        else:
            self._show_conv()

    def _show_conv(self) -> None:
        snap = self._conv.current()
        self.ctx.ui.show_conv(snap.title, snap.lines, snap.links,
                              snap.buttons, snap.terminal)

    def _set_conv(self, conv, npc) -> None:
        self._conv = conv
        self._conv_npc = npc
        self.ctx.ui.hide_dialog()
        self._talk_npc = None
        self._show_conv()
```

`consume_click/consume_keydown/update/close_all/portal_blocked` 相应精简：

```python
    def consume_click(self, pos):
        if self._conv is not None:
            idx = self.ctx.ui.conv_link_hit(pos)
            if idx is not None:
                self._conv.click_link(idx)
                self._after_turn()
            else:
                btn = self.ctx.ui.conv_button_hit(pos)
                if btn is not None:
                    self._conv.press(btn)
                    self._after_turn()
                elif not self.ctx.ui.quest_dialog_hit(pos):
                    self._close_conv()      # 点面板外 → 收起
            return True
        # 寒暄气泡部分不变

    def consume_keydown(self, key):
        if self._conv is not None:
            if key == pygame.K_ESCAPE:
                self._conv.press("close")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._conv.press("confirm")
            else:
                return True                 # 会话打开时吃掉其它键（同现状）
            self._after_turn()
            return True
        # 寒暄气泡部分不变

    def update(self):
        # 寒暄气泡走远收起不变；会话统一：
        if self._conv is not None and self._conv_npc is not None:
            if abs(player.x - self._conv_npc.rect().centerx) > TALK_RANGE:
                self._close_conv()

    def close_all(self):
        self.ctx.ui.hide_dialog()
        self._talk_npc = None
        self._close_conv()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest src/tests/test_menu_conversation.py src/tests/test_quest_flow.py src/tests/test_taxi.py -v && uv run pytest -x -q`
Expected: 全部 PASS（`test_lua_advance.py` 此时仍走旧 `_advance_*` 通道——本任务**保留** `_advance_session` 一族不删，Task 6 一并退役；`_open_script_conv` 先 `raise NotImplementedError` 之外，转职任务链接在 Task 5 期间仍从旧通道进入：`try_talk` 前部照搬现 `_advance_session is not None` 分支不可行的话，直接允许转职在 Task 5 后短暂经由 `_open_quest_conv → _open_script_conv` 抛错被 warning 吞掉，Task 6 修复。若不接受中间态，可把 Task 6 与本任务合并执行。）

- [ ] **Step 5: 提交**

```bash
git add src/game/npc_dialogue.py src/tests/test_menu_conversation.py
git commit -m "feat: 默认会话合成收编任务/出租车/商店选择菜单"
```

---

### Task 6: `talk()` 接入 + 转职重写 + 旧契约退役

**Files:**
- Modify: `src/game/npc_dialogue.py`（`_open_script_conv`、`try_talk` 加 talk 优先级、删 `_advance_*` 一族）
- Modify: `src/game/systems/script_api.py`（`teleport` 全局；jobdef 缺失不注册转职函数）
- Rewrite: `resources/content/advance.lua`、`resources/content/npc/reward_test.lua`
- Delete: `src/game/systems/scripting.py`
- Test: 重写 `src/tests/test_lua_advance.py`、`src/tests/test_lua_reward.py`

**Interfaces:**
- Consumes: `Conversation.from_source/make_ctx_view`、Task 5 的 `_after_turn/_set_conv/`pending_warp 约定
- Produces: 控制器 `_open_script_conv(npc, qid, script_name) -> None`、`_open_npc_talk(npc) -> bool`；`script_api` 新全局 `teleport(map_id)`（置宿主 `ctx.pending_warp = str(map_id)`）；`content/npc/<id>.lua` 可选导出 `talk(ctx)`

- [ ] **Step 1: 重写两个失败测试**

`src/tests/test_lua_advance.py`（整文件替换）：

```python
"""转职步骤图：advance.lua 以 talk(ctx) 驱动，验证路由/台词/选 yes 改真身。

透过公开 seam Conversation.from_source 测试；SimpleNamespace 假身，不用 mock。
"""
from __future__ import annotations

from pathlib import Path
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
    conv, _ = _conv(5)
    snap = conv.current()
    assert "太弱小" in snap.lines[0]
    assert snap.terminal


def test_confirm_step_has_yes_no_buttons():
    conv, _ = _conv(10)
    snap = conv.current()
    assert snap.buttons == ["yes", "no"]
    assert "弓箭手" in "".join(snap.lines)


def test_yes_triggers_advance_and_shows_congrats():
    conv, calls = _conv(10)
    conv.press("yes")
    assert calls == [3000]
    assert conv.current().lines[0] == "恭喜！你已转职为"


def test_no_goes_declined_step():
    conv, calls = _conv(10)
    conv.press("no")
    assert calls == []
    assert "改变心意" in conv.current().lines[0]


def test_already_advanced_job_shows_plain_notice():
    conv, _ = _conv(10, job=3000)
    assert "已经是一名" in conv.current().lines[0]
```

`src/tests/test_lua_reward.py`（整文件替换，`_session` 改为）：

```python
def _session(world):
    host = SimpleNamespace(player=world.player, world=world, assets=None,
                           npc_name="测试", advanced=False)
    ctx = make_ctx_view(world.player, "9999999", "测试", 100000000)
    src = (settings.RESOURCE_DIR / "content" / "npc" / "reward_test.lua"
           ).read_text("utf-8")
    return Conversation.from_source(src, make_globals(host), ctx)


def test_give_reward_full_grants_exp_meso_and_item():
    world = _reward_world()
    conv = _session(world)
    conv.current()
    conv.click_link(0)                      # 「full」链接
    assert world.player.exp == 500
    assert world.combat.meso == 1000
    assert world.player.inventory.consumes["02000000"].count == 3
    assert conv.current().lines == ["result:true"]
```

（其余三个分支同构：`click_link(1..3)` 对应 exp_only/empty/negative 链接。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest src/tests/test_lua_advance.py src/tests/test_lua_reward.py -v`
Expected: FAIL（旧 advance.lua 无 talk()）

- [ ] **Step 3: 重写内容脚本 + script_api + 控制器**

`resources/content/advance.lua`（整文件替换）：

```lua
-- 转职对话：talk(ctx) 步骤图。宿主契约见 resources/content/AGENTS.md。
local M = {}

function M.talk(ctx)
	local jd = ctx.jobdef
	local name = ctx.npc.name
	if ctx.player.job == jd.code then
		return { title = name, start = "already", steps = {
			already = { text = { "你已经是一名出色的" .. jd.name .. "了。" } } } }
	end
	if can_advance() then
		return { title = name, start = "confirm", steps = {
			confirm = {
				text = { "你想成为" .. jd.name .. "吗？",
					"达到 Lv" .. jd.advance_lv .. " 就可以转职为" .. jd.name .. "，",
					"转职后我会教你该职业的技能。" },
				buttons = { yes = function(c) advance_job() return "advanced" end,
					no = "declined" } },
			advanced = { text = { "恭喜！你已转职为", "" .. jd.name .. "了！" } },
			declined = { text = { "好吧，改变心意的话再来找我。" } } } }
	end
	return { title = name, start = "weak", steps = {
		weak = { text = { "你还太弱小了，达到等级再来找我吧。",
			string.format("（当前 Lv%d / 需要 Lv%d）",
				ctx.player.level, jd.advance_lv) } } } }
end

return M
```

`resources/content/npc/reward_test.lua`（整文件替换，links 顺序 = full/exp_only/empty/negative）：

```lua
-- 发奖能力测试脚本（仅供 test_lua_reward.py，不入游戏流程）
local M = {}
local last = "nil"

function M.talk(ctx)
	local function branch(f)
		return function(c) last = tostring(f()) return "result" end
	end
	return { start = "pick", steps = {
		pick = { text = { "choose" }, links = {
			{ label = "full",      click = branch(function() return give_reward(500, 1000, { { 2000000, 3 } }) end) },
			{ label = "exp_only",  click = branch(function() return give_reward(500) end) },
			{ label = "empty",     click = branch(function() return give_reward() end) },
			{ label = "negative",  click = branch(function() return give_reward(0, 0, { { 2000000, -1 } }) end) },
		} },
		result = { text = function(c) return { "result:" .. last } end } } }
end

return M
```

`script_api.make_globals` 顶部注册处改为（并新增 teleport）：

```python
    globals_: Dict[str, Callable] = {}
    if getattr(ctx, "jobdef", None) is not None:
        globals_["can_advance"] = can_advance
        globals_["advance_job"] = advance_job
    ...
    world = getattr(ctx, "world", None)
    if world is not None:
        ...
        def teleport(map_id) -> bool:
            """登记切图请求：解释器结束会话后由宿主执行。"""
            ctx.pending_warp = str(map_id)
            return True
        globals_["teleport"] = teleport
```

`npc_dialogue.py`：

1. `try_talk` 最前面加 `if self._open_npc_talk(npc): return`
2. 实现脚本会话通道（替换 `_begin_lua_quest/_show_session_snapshot/_advance_button` 与全部 `_advance_*` 字段）：

```python
    _CONTENT_DIR = settings.RESOURCE_DIR / "content"

    def _host_ctx(self, npc, jobdef=None):
        return SimpleNamespace(player=self.ctx.world.player,
                               world=self.ctx.world, jobdef=jobdef,
                               assets=self.assets, npc_name=npc.name,
                               quest_defs=self.quest_defs,
                               advanced=False, pending_warp=None)

    def _open_script_conv(self, npc, qid, script_name) -> bool:
        """content/<script>.lua 的 talk() 会话；失败返回 False 由调用方回落。"""
        path = self._CONTENT_DIR / f"{script_name}.lua"
        if not path.is_file():
            return False
        host = self._host_ctx(npc, jobdef=job_for_trainer(npc.npc_id,
                                self.ctx.world.player.job))
        ctx_view = make_ctx_view(host.player, npc.npc_id, npc.name,
                                 self.assets.map_id, jobdef=host.jobdef)
        try:
            conv = Conversation.from_source(path.read_text("utf-8"),
                                            make_globals(host), ctx_view,
                                            title=npc.name)
        except (LookupError, Exception):
            logging.warning("对话脚本 %s 加载失败", script_name, exc_info=True)
            return False
        self._conv_host = host
        self._conv_qid = qid
        self._set_conv(conv, npc)
        return True

    def _open_npc_talk(self, npc) -> bool:
        return self._open_script_conv(npc, None, f"npc/{npc.npc_id}")

    def _finish_conv(self) -> None:
        """会话正常结束（done）时的善后：转职音效/灯泡/force_complete。"""
        if self._conv_qid is not None and self._conv_host is not None \
                and self._conv_host.advanced:
            self.ctx.audio.play("LevelUp", 0.6)
            self.ctx.panels.flash(f"转职成功：{JOBS[self.ctx.world.player.job].name}")
            self.ctx.world.player.quests.force_complete(self._conv_qid)
        self._close_conv()
```

3. `_close_conv()` 清 `_conv/_conv_npc/_conv_host/_conv_qid`；`ui.hide_quest()`。
4. 删除 `from game.systems.scripting import build_lua_session`；删除 `src/game/systems/scripting.py`。
5. `ui.py` 删除 `show_quest/show_quest_list/quest_hit/quest_list_hit` 薄壳与别名（grep 确认仅剩 `_ = show_quest_list` 无引用后），`test_quest_list.py` 里用到旧壳的用例改用 `show_conv`。

- [ ] **Step 4: 跑全量测试**

Run: `uv run pytest -q`
Expected: 全部 PASS

- [ ] **Step 5: 手动冒烟**

Run: `uv run python -m game.main`
检查：新手 Lv10 在希拉处接到转职菜单 → 转职对话 yes 成功改职；1012119 商店+任务菜单正常；出租车点选切图、走远/Esc 收起。

- [ ] **Step 6: 提交**

```bash
git add src/game/npc_dialogue.py src/game/systems/script_api.py \
        src/game/systems/scripting.py resources/content/advance.lua \
        resources/content/npc/reward_test.lua src/tests/test_lua_advance.py \
        src/tests/test_lua_reward.py src/game/render/ui.py src/tests/test_quest_list.py
git commit -m "feat: talk() 契约接管转职与 NPC 脚本会话，退役 LuaSession 旧模型"
```

---

### Task 7: 内容示例迁移 + 契约文档

**Files:**
- Modify: `resources/content/npc/1012119.lua`（加 `talk()` 演示）
- Modify: `resources/content/AGENTS.md`、`AGENTS.md`
- Test: 无新增代码测试（文档/脚本），以全量 pytest + 冒烟收尾

**Interfaces:**
- Consumes: Task 2/5/6 全部契约
- Produces: 可复制的 `talk()` 参考实现；更新后的编写规范

- [ ] **Step 1: 给 1012119 写演示 talk()**

在 `resources/content/npc/1012119.lua` 的 `M.entries` 之前加入：

```lua
function M.talk(ctx)
  local QID = "c_1012119_1"
  return {
    start = "greet",
    steps = {
      greet = {
        text = { "哟，冒险者。要点什么？" },
        links = {
          { label = "接任务：收集红药水",
            show  = function(c) return quest_state(QID) == "available" end,
            click = function(c) accept_quest(QID) return "accepted" end },
          { label = "交付：收集红药水",
            show  = function(c) return quest_state(QID) == "accepted"
                                        and #quest_completable(ctx.npc.id) > 0 end,
            click = function(c) if complete_quest(QID) then return "rewarded" end
                                 return "not_yet" end },
          { label = "随便聊聊",
            click = function(c) return "chat" end },
        },
        buttons = { },
      },
      accepted   = { text = { "太好了！收集 10 个 #t2000000# 就来找我吧。",
                             "按 Q 查看任务日志。" } },
      rewarded   = { text = { "这是你的奖励！" } },
      not_yet    = { text = { "还差一些，继续加油！" } },
      chat       = { text = { "呵呵，看你装备渐佳，是个人物。" } },
    },
  }
end
```

要点：任务链接展示「自定义任务也能全程 Lua 编排」；`greet` 无商店链接是因为默认商店路由（`shops_of` 非空且无任务/传送时直开店）仍在——但本 NPC 有任务，所以菜单形态由 `talk()` 完全接管；想加"商店"入口就在 links 里补 `{ label = "商店", click = function(c) open_shop() ... end }`（本轮不做 `open_shop` 全局，文档注明留给后续）。

- [ ] **Step 2: 游戏内验证 talk() 优先于默认菜单**

Run: `uv run python -m game.main`，与 1012119 对话：应出现「哟，冒险者」黑文本 + 三~四条蓝字；接任务后蓝字变「交付…」；全部链接走完 Esc/点外关闭。
Expected: 行为如上；若 `quest_state/quest_completable` 未注册（host ctx 无 world/quest_defs）→ 检查 `_host_ctx`。

- [ ] **Step 3: 重写 `resources/content/AGENTS.md` 契约章节**

- 删除「每份脚本必须导出的契约」（new/snapshot/choose/done）与「snapshot() 返回表字段」「选项标签约定」节
- 新增 `talk(ctx)` 章节：step/link/buttons/next 字段表（照 spec §4）、结束标记（无 links 无 buttons = 终态；click 返回 nil = 结束）、buttons 值可为步名或函数、错误处理表（spec §5.3）
- ctx 表更新：`ctx.player.{level,job,map}`、`ctx.npc.{id,name}`、`ctx.jobdef.*`（仅转职）
- 全局函数表补 `teleport(map_id)`
- 「任务条目」的 `accept_lines` 等槽位标注降级为「不写 talk() 时的默认对话文本」
- 新增说明：不写 `talk()` 时宿主自动合成默认会话（任务/进行中/传送/商店），写了则完全接管

- [ ] **Step 4: 根 `AGENTS.md` 架构要点补一行**

「游戏循环」小节 `src/game/systems/` 分层描述后追加：
`对话统一走 systems/conversation.py 步骤图解释器（talk() Lua 契约 + quest_flow.py 适配器），npc_dialogue.py 只做路由。`

- [ ] **Step 5: 全量测试 + 提交**

Run: `uv run pytest -q`
Expected: 全部 PASS

```bash
git add resources/content/npc/1012119.lua resources/content/AGENTS.md AGENTS.md \
        docs/superpowers/specs/2026-09-04-lua-conversation-schema-design.md
git commit -m "docs: talk() 契约文档与 1012119 演示脚本；spec 存档"
```

---

## Self-Review 记录

1. **Spec 覆盖**：§4 契约（Task 2/6/7）、§5 解释器与错误处理（Task 1/2）、§5.2 teleport（Task 6）、§6.1-6.4 收编（Task 5/6）、§7 UI（Task 3）、§8 迁移顺序与 §9 测试逐条对应。无缺口。
2. **占位符**：无 TBD；Task 5 Step 4 对转职中间态给出了明确的合并执行选项。
3. **类型一致性**：`Snapshot.links: List[Tuple[str,int]]` 与 `UI.show_conv(links)`、`Link.note` 三处一致；`press` 键名（confirm/close/yes/no/ok）在引擎、控制器、UI 命中返回（yes/no/ok）间一致；`pending_warp/advanced` 约定在 script_api、Task 5 `_after_turn`、Task 6 `_finish_conv` 一致。
