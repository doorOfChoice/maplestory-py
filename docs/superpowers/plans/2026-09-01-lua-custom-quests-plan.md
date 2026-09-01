# Lua 自定义任务系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `resources/content/npc/<npc_id>.lua` 可为任意 NPC 定义多个自定义任务，并接入游戏流程

**Architecture:** Lua 脚本导出 `quests(ctx)` 返回任务定义数组 → Python 翻译成 `QuestDef` 并合并进 `quest_defs` 字典 → 现有 `QuestLog`/`collect_npc_quests`/NPC 路灯/存档全自动生效

**Tech Stack:** Python 3.12, lupa, tempfile (测试), 无额外依赖

**Spec:** `docs/superpowers/specs/2026-09-01-lua-custom-quests-design.md`

## Global Constraints

- 每个文件顶部加 `from __future__ import annotations`
- 导入顺序：标准库 → 第三方 → 本项目，空行分隔；本项目内用绝对导入
- 类型标注：所有函数签名都应标注
- 测试：不用 mock、不用 fixture（`tmp_path` 等 pytest 内置 fixture 除外，但为保持一致，测试用 `tempfile.mkdtemp` + 手动清理）、合成数据、不依赖 WZ
- 新增 `.py` 文件必须加模块 docstring（简体中文）
- `load_lua_quest_defs` 签名：`load_lua_quest_defs(script_dir: Optional[Path] = None, ctx: Optional[Any] = None) -> Dict[str, QuestDef]`（与规格比去掉 `assets` 参数，翻译纯数据不依赖 WZ）
- 当前加载阶段玩家未建，ctx 传 None；条件过滤由 `lvmin`/`lvmax`/`jobs` 字段 + QuestLog 负责

---

### Task 1: `_lua_to_py` 递归转换 + `_quest_to_def` 单条翻译

**Files:**
- Create: `src/game/systems/lua_quests.py`（起始部分，只包含 helper 和 `_quest_to_def`）
- Test: `src/tests/test_lua_quest_defs.py`（模块级辅助函数建构 lupa 表，不写临时文件）

**Interfaces:**
- Consumes: `QuestDef`（from `game.systems.quests`）、`lupa.LuaRuntime`
- Produces: `_lua_to_py(value) -> Any`（递归折 lupa table → python 标量/list/dict）、`_pairs(v) -> list[tuple[int, int]]`、`_ints(v) -> list[int]`、`_lines(v) -> list[str]`、`_quest_to_def(npc_id: str, idx: int, tbl) -> Optional[QuestDef]`

- [ ] **Step 1: 写 `lua_quests.py` 模块 docstring 和导入**

```python
"""Lua 自定义任务定义翻译器：把 content/npc/*.lua 的 quests() 返回值翻译成 QuestDef。

扫描脚本目录，加载每个 Lua 脚本，调用 quests(ctx) 拿到任务数组，
逐条翻译成 QuestDef 后合并到 quest_defs 字典，供游戏流程使用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from game.systems.quests import QuestDef
```

- [ ] **Step 2: 写测试 helper 构建 lupa 表**

```python
# src/tests/test_lua_quest_defs.py
from __future__ import annotations

import pytest
from lupa import LuaRuntime

from game.systems.lua_quests import _quest_to_def, _pairs, _ints, _lines

pytest.importorskip("lupa")

_rt = LuaRuntime(unpack_returned_tuples=True, register_eval=False)

def T(*args, **kwargs):
    """快捷建 lupa table。"""
    return _rt.table(*args, **kwargs)
```

- [ ] **Step 3: 运行测试确认 helper 导入正常**

```bash
uv run pytest src/tests/test_lua_quest_defs.py -v -k "test_pairs or test_ints or test_lines"
```

- [ ] **Step 4: 写 `_pairs` / `_ints` / `_lines` 的测试**

```python
def test_pairs_empty():
    assert _pairs(None) == []

def test_pairs_normal():
    tbl = T(T(2000000, 3), T(100, 5))
    assert _pairs(tbl) == [(2000000, 3), (100, 5)]

def test_ints_empty():
    assert _ints(None) == []

def test_ints_normal():
    assert _ints(T(0, 3000)) == [0, 3000]

def test_lines_empty():
    assert _lines(None) == []

def test_lines_normal():
    assert _lines(T("你好", "冒险家")) == ["你好", "冒险家"]
```

- [ ] **Step 5: 实现 `_pairs` / `_ints` / `_lines`**

```python
def _pairs(v) -> List[Tuple[int, int]]:
    """lupa 数组 [[id, count], ...] → [(int, int), ...]"""
    out: List[Tuple[int, int]] = []
    if v is None:
        return out
    for i in range(1, len(v) + 1):
        p = v[i]
        if p is None:
            continue
        out.append((int(p[1]), int(p[2])))
    return out

def _ints(v) -> List[int]:
    """lupa 数组 → [int, ...]"""
    out: List[int] = []
    if v is None:
        return out
    for i in range(1, len(v) + 1):
        out.append(int(v[i]))
    return out

def _lines(v) -> List[str]:
    """lupa 数组 → [str, ...]"""
    out: List[str] = []
    if v is None:
        return out
    for i in range(1, len(v) + 1):
        out.append(str(v[i]))
    return out
```

- [ ] **Step 6: 运行测试**

```bash
uv run pytest src/tests/test_lua_quest_defs.py -v -k "test_pairs or test_ints or test_lines"
```

- [ ] **Step 7: 写 `_quest_to_def` 的测试 — 完整翻译一条任务**

```python
def test_quest_to_def_minimal():
    """最小字段：只给 name, lvmin, kills, reward_exp。"""
    tbl = T(
        name="红药水收集",
        lvmin=1,
        kills=T(T(100, 5)),
        reward_exp=100,
        accept_lines=T("要接受吗？"),
        accept_yes=T("已接受"),
        complete_lines=T("完成了吗？"),
        complete_yes=T("奖励发放"),
        complete_stop=T("还差一些"),
    )
    d = _quest_to_def("1012100", 1, tbl)
    assert d is not None
    assert d.qid == "c_1012100_1"
    assert d.name == "红药水收集"
    assert d.lvmin == 1
    assert d.start_npc == 1012100
    assert d.end_npc == 1012100
    assert d.kills == [(100, 5)]
    assert d.reward_exp == 100
    assert d.accept_lines == ["要接受吗？"]

def test_quest_to_def_with_start_npc():
    """显式 start_npc 可覆盖文件名的 NPC id。"""
    tbl = T(name="跨 NPC 任务", start_npc=1012100, end_npc=1012110,
            accept_lines=T("ok"), complete_lines=T("done"))
    d = _quest_to_def("1012110", 1, tbl)
    assert d.start_npc == 1012100
    assert d.end_npc == 1012110

def test_quest_to_def_missing_name_is_skipped():
    """没有 name 字段的任务返回 None。"""
    tbl = T(accept_lines=T("no name"))
    assert _quest_to_def("1012100", 1, tbl) is None

def test_quest_to_def_full_fields():
    """所有可选字段完整翻译。"""
    tbl = T(
        name="完整任务",
        lvmin=10, lvmax=50, jobs=T(0, 3000),
        start_items=T(T(100, 1)),
        prereq=T(T(1000, 2)),
        kills=T(T(100, 5)),
        end_items=T(T(2000000, 3)),
        accept_items=T(T(100, 1)),
        reward_exp=500, reward_money=1000,
        reward_items=T(T(2000000, 2)),
        next_quest=2001,
        accept_lines=T("a1", "a2"),
        accept_yes=T("ay"),
        accept_no=T("an"),
        complete_lines=T("c1"),
        complete_yes=T("cy"),
        complete_stop=T("cs"),
        parent="p1", order=1, area=2,
        desc0="d0", desc1="d1", desc2="d2",
    )
    d = _quest_to_def("1012100", 1, tbl)
    assert d.lvmax == 50
    assert d.jobs == [0, 3000]
    assert d.start_items == [(100, 1)]
    assert d.prereq == [(1000, 2)]
    assert d.kills == [(100, 5)]
    assert d.end_items == [(2000000, 3)]
    assert d.accept_items == [(100, 1)]
    assert d.reward_exp == 500
    assert d.reward_money == 1000
    assert d.reward_items == [(2000000, 2)]
    assert d.next_quest == 2001
    assert d.accept_lines == ["a1", "a2"]
```

- [ ] **Step 8: 实现 `_quest_to_def`**

```python
def _quest_to_def(npc_id: str, idx: int, tbl) -> Optional[QuestDef]:
    """把 lupa table 翻译成 QuestDef；字段缺失/类型错误返回 None。"""
    try:
        name = tbl["name"]
        if not name:
            return None
        qid = f"c_{npc_id}_{idx}"
        start_npc = tbl.get("start_npc")
        if start_npc is not None:
            start_npc = int(start_npc)
        else:
            start_npc = int(npc_id)
        end_npc = tbl.get("end_npc")
        if end_npc is not None:
            end_npc = int(end_npc)
        else:
            end_npc = int(npc_id)
        return QuestDef(
            qid=qid,
            name=str(name),
            start_npc=start_npc,
            end_npc=end_npc,
            lvmin=_num(tbl.get("lvmin")),
            lvmax=_num(tbl.get("lvmax")),
            jobs=_ints(tbl.get("jobs")),
            start_items=_pairs(tbl.get("start_items")),
            prereq=_pairs(tbl.get("prereq")),
            kills=_pairs(tbl.get("kills")),
            end_items=_pairs(tbl.get("end_items")),
            accept_items=_pairs(tbl.get("accept_items")),
            reward_exp=_num(tbl.get("reward_exp")),
            reward_money=_num(tbl.get("reward_money")),
            reward_items=_pairs(tbl.get("reward_items")),
            next_quest=_num(tbl.get("next_quest")) or None,
            accept_lines=_lines(tbl.get("accept_lines")),
            accept_yes=_lines(tbl.get("accept_yes")),
            accept_no=_lines(tbl.get("accept_no")),
            complete_lines=_lines(tbl.get("complete_lines")),
            complete_yes=_lines(tbl.get("complete_yes")),
            complete_stop=_lines(tbl.get("complete_stop")),
            desc0=str(tbl.get("desc0") or ""),
            desc1=str(tbl.get("desc1") or ""),
            desc2=str(tbl.get("desc2") or ""),
            parent=str(tbl.get("parent") or ""),
            order=_num(tbl.get("order")),
            area=_num(tbl.get("area")),
        )
    except (TypeError, ValueError, AttributeError) as e:
        logging.warning("Lua quest [%s/%d] parse failed: %s", npc_id, idx, e)
        return None

def _num(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0
```

- [ ] **Step 9: 运行全部测试**

```bash
uv run pytest src/tests/test_lua_quest_defs.py -v
```

- [ ] **Step 10: 提交**

```bash
git add src/game/systems/lua_quests.py src/tests/test_lua_quest_defs.py
git commit -m "feat: Lua 任务定义翻译核心——_lua_to_py / _quest_to_def"
```

---

### Task 2: `load_lua_quest_defs` 目录扫描 + 沙箱加载

**Files:**
- Modify: `src/game/systems/lua_quests.py`（追加 `load_lua_quest_defs`）
- Test: `src/tests/test_lua_quest_defs.py`（追加加载器测试）

**Interfaces:**
- Consumes: `_quest_to_def`、`scripting._sandboxed_runtime`（通过 `from game.systems.scripting import _sandboxed_runtime`——注意这是私有成员，需确认是否可引出。或直接 `from lupa import LuaRuntime` 自己建——但 `_sandboxed_runtime` 还有禁用 os/io/package 等。为安全，最好在 `scripting.py` 暴露一个公共函数，或直接复制沙箱逻辑。）
- Produces: `load_lua_quest_defs(script_dir=None, ctx=None) -> Dict[str, QuestDef]`

**关于 `_sandboxed_runtime` 的访问**：`scripting.py` 的 `_sandboxed_runtime` 是模块私有函数（`_` 前缀）。按 AGENTS.md「不探索私有成员」，但 `lua_quests.py` 是项目内同一子包，可以直接 `from game.systems.scripting import _sandboxed_runtime`——测试也透过 `lua_quests` 间接用。或者我直接复制沙箱代码（`LuaRuntime(unpack_returned_tuples=True, register_eval=False)` + 禁用 `os/io/package/debug/dofile/loadfile`）。后者更干净（不依赖内部细节），故选用。

- [ ] **Step 1: 写 `load_lua_quest_defs` 签名和沙箱逻辑**

> 需在 Task 1 的导入区追加两行（放在 `from game.systems.quests import QuestDef` 之前）：
> ```python
> import lupa
> from lupa import LuaRuntime
>
> from game import settings
> ```

```python
_SCRIPT_DIR = settings.RESOURCE_DIR / "content" / "npc"
_FORBIDDEN = ("os", "io", "package", "debug", "dofile", "loadfile")

def _sandbox() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    g = lua.globals()
    for name in _FORBIDDEN:
        g[name] = None
    return lua


def load_lua_quest_defs(
    script_dir: Optional[Path] = None,
    ctx: Any = None,
) -> Dict[str, QuestDef]:
    """扫描 script_dir 下 *.lua，加载 quests() 翻译成 {qid: QuestDef}。"""
    script_dir = script_dir or _SCRIPT_DIR
    defs: Dict[str, QuestDef] = {}
    if not script_dir.is_dir():
        return defs
    for path in sorted(script_dir.glob("*.lua")):
        npc_id = path.stem
        try:
            lua = _sandbox()
            src = path.read_text(encoding="utf-8")
            mod = lua.execute(src, str(path))
            quests_fn = mod.get("quests")
            quests_tbl = quests_fn(ctx) if quests_fn is not None else None
            if quests_tbl is None:
                continue
            for i in range(1, len(quests_tbl) + 1):
                item = quests_tbl[i]
                if item is None:
                    continue
                d = _quest_to_def(npc_id, i, item)
                if d is not None:
                    defs[d.qid] = d
        except Exception:
            logging.warning("Lua script %s load failed", path, exc_info=True)
    return defs
```

- [ ] **Step 2: 写加载器测试——用临时目录写 Lua 脚本**

```python
import tempfile
import shutil
from pathlib import Path
from game.systems.lua_quests import load_lua_quest_defs


def test_load_lua_quest_defs_single_npc():
    """单个 NPC 脚本定义 2 个任务，返回正确的 qid 和字段。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "1012100.lua").write_text("""\
local M = {}
function M.quests(ctx)
  return {
    { name = "任务1", lvmin=1, accept_lines = {"a1"}, complete_lines = {"c1"} },
    { name = "任务2", lvmin=5, end_items = {{2000000, 3}},
      accept_lines = {"a2"}, complete_lines = {"c2"} },
  }
end
return M
""")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert len(defs) == 2
        assert "c_1012100_1" in defs
        assert defs["c_1012100_1"].name == "任务1"
        assert defs["c_1012100_1"].lvmin == 1
        assert defs["c_1012100_1"].start_npc == 1012100
        assert "c_1012100_2" in defs
        assert defs["c_1012100_2"].end_items == [(2000000, 3)]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_lua_quest_defs_two_npcs():
    """两个 NPC 脚本，各自任务都能正确加载。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "1012100.lua").write_text("""\
local M = {}
function M.quests(ctx) return {{ name = "N1", accept_lines = {"a"}, complete_lines = {"c"} }} end
return M
""")
        (tmp / "1012119.lua").write_text("""\
local M = {}
function M.quests(ctx) return {{ name = "N2", accept_lines = {"b"}, complete_lines = {"d"} }} end
return M
""")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert len(defs) == 2
        assert "c_1012100_1" in defs
        assert "c_1012119_1" in defs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_lua_quest_defs_no_quests():
    """脚本没有 quests 函数，跳过。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "empty.lua").write_text("local M = {} return M\n")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert defs == {}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_lua_quest_defs_one_bad_skip():
    """多条任务中一条翻译失败，不拖垮其余。"""
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "1012100.lua").write_text("""\
local M = {}
function M.quests(ctx)
  return {
    { name = "good", accept_lines = {"a"}, complete_lines = {"c"} },
    { },  -- 没 name → 跳过
    { name = "also_good", accept_lines = {"b"}, complete_lines = {"d"} },
  }
end
return M
""")
        defs = load_lua_quest_defs(script_dir=tmp)
        assert len(defs) == 2
        assert "c_1012100_1" in defs
        assert "c_1012100_3" in defs
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 3: 运行测试**

```bash
uv run pytest src/tests/test_lua_quest_defs.py -v
```

- [ ] **Step 4: 提交**

```bash
git add src/game/systems/lua_quests.py src/tests/test_lua_quest_defs.py
git commit -m "feat: load_lua_quest_defs 目录扫描+沙箱加载"
```

---

### Task 3: `game.py` 合并接线 + 与官方任务共存验证

**Files:**
- Modify: `src/game/game.py:106`
- Test: `src/tests/test_lua_quest_defs.py`（加整合测试，验证合并后 `collect_npc_quests` 同时找到官方和自定义任务）

**Interfaces:**
- Consumes: `load_lua_quest_defs`（from `game.systems.lua_quests`）

- [ ] **Step 1: 在 `game.py` 导入并合并**

```python
# 文件顶部加导入
from game.systems.lua_quests import load_lua_quest_defs

# _build_world() 中 quest_thread.join() 之后（第 106 行）：
self.quest_defs = quest_box.get("defs") or {}
lua_defs = load_lua_quest_defs()
if lua_defs:
    self.quest_defs = {**self.quest_defs, **lua_defs}
```

- [ ] **Step 2: 写整合测试——验证 `collect_npc_quests` 同时选中官方和自定义任务**

```python
def test_collect_npc_quests_merges_lua_and_wz():
    """collect_npc_quests 能同时找到官方和自定义任务（qid 不冲突）。"""
    from game.systems.quests import QuestLog, collect_npc_quests
    from tests.fake_assets import FakeAssets
    from types import SimpleNamespace

    # 官方任务定义（模拟 load_quest_defs 结果）
    wz_defs = {
        "1000": QuestDef(qid="1000", name="WZ任务", start_npc=1012100, end_npc=1012100,
                         lvmin=1, accept_lines=["a"], complete_lines=["c"]),
    }
    # Lua 任务定义（模拟 load_lua_quest_defs 结果）
    lua_defs = {
        "c_1012100_1": QuestDef(qid="c_1012100_1", name="Lua任务",
                                start_npc=1012100, end_npc=1012100,
                                lvmin=1, accept_lines=["b"], complete_lines=["d"]),
    }
    defs = {**wz_defs, **lua_defs}
    log = QuestLog(defs)
    player = SimpleNamespace(level=10, job=0, inventory=SimpleNamespace(
        etcs={}, consumes={}))
    items = collect_npc_quests(defs, log, "1012100", player)
    assert len(items) == 2
    qids = [it.qid for it in items]
    assert "1000" in qids
    assert "c_1012100_1" in qids
```

- [ ] **Step 3: 运行测试**

```bash
uv run pytest src/tests/test_lua_quest_defs.py::test_collect_npc_quests_merges_lua_and_wz -v
```

- [ ] **Step 4: 提交**

```bash
git add src/game/game.py src/tests/test_lua_quest_defs.py
git commit -m "feat: game.py 合并 Lua 自定义任务入 quest_defs"
```

---

### Task 4: 示例脚本 + AGENTS.md 更新

**Files:**
- Create: `resources/content/npc/1012119.lua`（示例：商店 NPC 的自定义任务）
- Modify: `resources/content/AGENTS.md`（补充自定义任务编写规范）

- [ ] **Step 1: 写示例脚本 `resources/content/npc/1012119.lua`**

```lua
-- 1012119（商店 NPC 托德）自定义任务示例
local M = {}

function M.quests(ctx)
  return {
    {
      name = "收集红药水",
      lvmin = 1,
      end_items = {{2000000, 10}},  -- 收集 10 个红药水
      reward_exp = 200,
      reward_money = 1000,
      accept_lines = {"你要帮我收集 #t2000000# 吗？"},
      accept_yes = {"太好了！收集 10 个红药水就来找我吧。"},
      accept_no = {"好吧，改变主意了再来。"},
      complete_lines = {"你收集够了！要领取奖励吗？"},
      complete_yes = {"这是你的奖励！"},
      complete_stop = {"还差一些，继续加油！"},
    },
  }
end

return M
```

- [ ] **Step 2: 更新 `resources/content/AGENTS.md`** 补充以下内容：
  - 新增 `content/npc/<npc_id>.lua` 目录及其用途
  - `quests(ctx)` 函数契约（返回任务数组，字段映射表）
  - `ctx` 参数说明（当前为 None，条件过滤靠 `lvmin`/`kills`/`end_items` 等字段）
  - qid 自动加 `c_` 前缀，NPC id 取自文件名
  - 对话文本支持 `#t#`/`#o#` 等标记

- [ ] **Step 3: 冒烟测试——启动游戏确认不报错**

```bash
uv run python -m game.main
# 走到弓箭手村，找 1012119（托德）对话，确认自定义任务出现在列表中
```

- [ ] **Step 4: 提交**

```bash
git add resources/content/npc/1012119.lua resources/content/AGENTS.md
git commit -m "feat: 示例自定义任务脚本 + AGENTS.md 编写规范"
```