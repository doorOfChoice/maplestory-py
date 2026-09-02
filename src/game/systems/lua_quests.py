"""Lua 自定义任务定义翻译器：把 content/npc/*.lua 的 quests() 返回值翻译成 QuestDef。

扫描脚本目录，加载每个 Lua 脚本，调用 quests(ctx) 拿到任务数组，
逐条翻译成 QuestDef 后合并到 quest_defs 字典，供游戏流程使用。

同时支持 shops() 和 dialogues()：
- shops() 返回 [{shop_id, items: [{item_id, price}, ...]}, ...]
- dialogues() 返回 [[line1, line2], [line3, line4], ...]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import lupa
from lupa import LuaRuntime

from game import settings
from game.core.jobs import JOBS
from game.systems.quests import QuestDef
from game.systems.shop import register_lua_shop
from game.systems.dialogues import register_lua_dialogue

# 内容脚本目录：resources/content/npc/<npc_id>.lua
_SCRIPT_DIR = settings.RESOURCE_DIR / "content" / "npc"

# 沙箱里禁止的系统库/加载函数（与 scripting.py 保持一致）
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
            prereq=_pairs(tbl["prereq"]),
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
    """从 Lua 脚本注册商店定义。"""
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
        items_tbl = shop["items"]
        if items_tbl is not None:
            item_list: List[Tuple[str, int]] = []
            for j in range(1, len(items_tbl) + 1):
                item = items_tbl[j]
                if item is None:
                    continue
                item_id = str(item["item_id"] or "")
                price = _num(item["price"])
                if item_id:
                    item_list.append((item_id, price))
            # 将 Lua 定义的物品写入 SHOPS（如果该 shop_id 尚不存在）
            from game.systems.shop import SHOPS
            if shop_id not in SHOPS:
                SHOPS[shop_id] = [it[0] for it in item_list]
        shop_ids.append(shop_id)
    if shop_ids:
        register_lua_shop(npc_id, shop_ids)


def _load_lua_dialogues(npc_id: str, lua: LuaRuntime, mod) -> None:
    """从 Lua 脚本注册对话台词池。"""
    dialogues_fn = mod["dialogues"]
    if dialogues_fn is None:
        return
    dialogues_tbl = dialogues_fn()
    if dialogues_tbl is None:
        return
    lines_pool: List[List[str]] = []
    for i in range(1, len(dialogues_tbl) + 1):
        group = dialogues_tbl[i]
        if group is None:
            continue
        lines = _lines(group)
        if lines:
            lines_pool.append(lines)
    if lines_pool:
        register_lua_dialogue(npc_id, lines_pool)


def load_lua_quest_defs(
    script_dir: Optional[Path] = None,
    ctx: Any = None,
) -> Dict[str, QuestDef]:
    """扫描 script_dir 下 *.lua，加载 quests() 翻译成 {qid: QuestDef}。

    同时加载 shops() 和 dialogues()（如果脚本导出的话）。
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
            # 加载任务定义
            quests_fn = mod["quests"]
            if quests_fn is not None:
                quests_tbl = quests_fn(ctx)
                if quests_tbl is not None:
                    for i in range(1, len(quests_tbl) + 1):
                        item = quests_tbl[i]
                        if item is None:
                            continue
                        d = _quest_to_def(npc_id, i, item)
                        if d is not None:
                            defs[d.qid] = d
            # 加载商店定义
            _load_lua_shops(npc_id, lua, mod)
            # 加载对话定义
            _load_lua_dialogues(npc_id, lua, mod)
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
