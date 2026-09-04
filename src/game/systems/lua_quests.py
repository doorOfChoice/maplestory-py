"""Lua NPC 内容翻译器：把 content/npc/*.lua 的 entries() 分流到各系统。

扫描脚本目录，加载每个 Lua 脚本，调用 entries(ctx) 拿到带类型的条目数组：
- type="quest"    → 翻译成 QuestDef 合并到 quest_defs，走任务状态机
- type="teleport" → 注册到 travel 的 NPC 传送目的地表（出租车），走统一对话菜单
条目缺省 type 视为 "quest"；未知类型跳过并记录 warning。

同时支持 shops()：返回 [{shop_id, items: [{item_id, price}, ...]}, ...]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import lupa
from lupa import LuaRuntime

from game import settings
from game.core import travel
from game.core.jobs import JOBS
from game.systems.quests import QuestDef
from game.systems.shop import register_lua_shop, register_shop_profile

# 内容脚本目录：resources/content/npc/<npc_id>.lua
_SCRIPT_DIR = settings.RESOURCE_DIR / "content" / "npc"

# 沙箱里禁止的系统库/加载函数（与 conversation.py 保持一致）
_FORBIDDEN = ("os", "io", "package", "debug", "dofile", "loadfile")


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


def _prereq(v) -> List[Tuple[object, int]]:
    """prereq [[qid, state], ...]：数字 qid（官方任务）保 int，其余保字符串。

    自定义任务 qid 形如 c_1012119_1，转 int 会炸，故与 _pairs 分开处理；
    QuestLog.can_start 统一按 str(q) 比对，两种形态都认。
    """
    out: List[Tuple[object, int]] = []
    if v is None:
        return out
    for i in range(1, len(v) + 1):
        p = v[i]
        if p is None:
            continue
        q = p[1]
        try:
            q = int(q)
        except (TypeError, ValueError):
            q = str(q)
        out.append((q, int(p[2])))
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


def _num(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _quest_to_def(npc_id: str, idx: int, tbl) -> Optional[QuestDef]:
    """把 lupa table 翻译成 QuestDef；字段缺失/类型错误返回 None。"""
    try:
        name = tbl["name"]
        if not name:
            return None
        qid = f"c_{npc_id}_{idx}"
        start_npc = tbl["start_npc"]
        if start_npc is not None:
            start_npc = int(start_npc)
        else:
            start_npc = int(npc_id)
        end_npc = tbl["end_npc"]
        if end_npc is not None:
            end_npc = int(end_npc)
        else:
            end_npc = int(npc_id)
        return QuestDef(
            qid=qid,
            name=str(name),
            start_npc=start_npc,
            end_npc=end_npc,
            lvmin=_num(tbl["lvmin"]),
            lvmax=_num(tbl["lvmax"]),
            jobs=_ints(tbl["jobs"]),
            start_items=_pairs(tbl["start_items"]),
            prereq=_prereq(tbl["prereq"]),
            kills=_pairs(tbl["kills"]),
            end_items=_pairs(tbl["end_items"]),
            accept_items=_pairs(tbl["accept_items"]),
            reward_exp=_num(tbl["reward_exp"]),
            reward_money=_num(tbl["reward_money"]),
            reward_items=_pairs(tbl["reward_items"]),
            next_quest=_num(tbl["next_quest"]) or None,
            accept_lines=_lines(tbl["accept_lines"]),
            accept_yes=_lines(tbl["accept_yes"]),
            accept_no=_lines(tbl["accept_no"]),
            complete_lines=_lines(tbl["complete_lines"]),
            complete_yes=_lines(tbl["complete_yes"]),
            complete_stop=_lines(tbl["complete_stop"]),
            desc0=str(tbl["desc0"] or ""),
            desc1=str(tbl["desc1"] or ""),
            desc2=str(tbl["desc2"] or ""),
            parent=str(tbl["parent"] or ""),
            order=_num(tbl["order"]),
            area=_num(tbl["area"]),
        )
    except (TypeError, ValueError, AttributeError) as e:
        logging.warning("Lua quest [%s/%d] parse failed: %s", npc_id, idx, e)
        return None


def _sandbox() -> LuaRuntime:
    lua = LuaRuntime(unpack_returned_tuples=True, register_eval=False)
    g = lua.globals()
    for name in _FORBIDDEN:
        g[name] = None
    return lua


def _load_lua_shops(npc_id: str, lua: LuaRuntime, mod) -> None:
    """从 Lua 脚本注册商店定义（货架明细 + 买价 + 显示名）。"""
    shops_fn = mod["shops"]
    if shops_fn is None:
        return
    shops_tbl = shops_fn()
    if shops_tbl is None:
        return
    shop_ids: List[str] = []
    for i in range(1, len(shops_tbl) + 1):
        shop = shops_tbl[i]
        if shop is None:
            continue
        shop_id = str(shop["shop_id"] or f"{npc_id}_shop_{i}")
        name = str(shop["name"]) if shop["name"] else None
        items_tbl = shop["items"]
        item_list: List[Tuple[str, int]] = []
        if items_tbl is not None:
            for j in range(1, len(items_tbl) + 1):
                item = items_tbl[j]
                if item is None:
                    continue
                item_id = str(item["item_id"] or "")
                price = _num(item["price"])
                if item_id:
                    item_list.append((item_id, price))
        register_shop_profile(shop_id, name, item_list)
        shop_ids.append(shop_id)
    if shop_ids:
        register_lua_shop(npc_id, shop_ids)


def _entry_type(tbl) -> str:
    """条目类型字段；缺省视为 "quest"。"""
    try:
        t = tbl["type"]
    except (TypeError, LookupError):
        return "quest"
    return str(t) if t else "quest"


def _load_lua_entries(npc_id: str, mod, defs: Dict[str, QuestDef]) -> None:
    """entries() 分流：quest → QuestDef，teleport → travel 传送注册表。"""
    entries_fn = mod["entries"]
    if entries_fn is None:
        return
    entries_tbl = entries_fn(None)
    if entries_tbl is None:
        return
    teleports: List[Tuple[str, str]] = []
    for i in range(1, len(entries_tbl) + 1):
        item = entries_tbl[i]
        if item is None:
            continue
        etype = _entry_type(item)
        if etype == "quest":
            d = _quest_to_def(npc_id, i, item)
            if d is not None:
                defs[d.qid] = d
        elif etype == "teleport":
            label, mid = item["label"], item["map"]
            if label and mid:
                teleports.append((str(label), str(mid)))
            else:
                logging.warning("Lua teleport [%s/%d] missing label/map", npc_id, i)
        else:
            logging.warning("Lua entry [%s/%d] unknown type: %s", npc_id, i, etype)
    if teleports:
        travel.register_teleports(npc_id, teleports)


def load_lua_quest_defs(
    script_dir: Optional[Path] = None,
) -> Dict[str, QuestDef]:
    """扫描 script_dir 下 *.lua，加载 entries()/shops() 并分流到各系统。

    返回 {qid: QuestDef}；teleport 条目副作用进 travel 注册表。
    """
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
            _load_lua_entries(npc_id, mod, defs)
            # 加载商店定义
            _load_lua_shops(npc_id, lua, mod)
        except Exception:
            logging.warning("Lua script %s load failed", path, exc_info=True)
    return defs


def build_advance_quest_defs() -> Dict[str, QuestDef]:
    """为每个有导师的职业生成「转职任务」QuestDef（script=advance 驱动）。

    转职任务 = 一个无杀怪/收集条件的特殊任务：对话由 Lua 会话（advance.lua）驱动，
    完成时改真身职业。lvmin 置 0 使新手任何时候都能在导师处看到该任务并得到
    「等级不足」的引导（Lua 脚本内的 weak 分支）；jobs 限制为前置职业，转职后
    自然不再出现在列表。
    """
    defs: Dict[str, QuestDef] = {}
    for jd in JOBS.values():
        if jd.trainer_npc is None:
            continue
        qid = f"adv_{jd.code}"
        defs[qid] = QuestDef(
            qid=qid,
            name=f"转职：{jd.name}",
            start_npc=jd.trainer_npc,
            end_npc=jd.trainer_npc,
            lvmin=0,
            jobs=[jd.prejob],
            script="advance",
        )
    return defs
