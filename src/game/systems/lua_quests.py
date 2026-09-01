"""Lua 自定义任务定义翻译器：把 content/npc/*.lua 的 quests() 返回值翻译成 QuestDef。

扫描脚本目录，加载每个 Lua 脚本，调用 quests(ctx) 拿到任务数组，
逐条翻译成 QuestDef 后合并到 quest_defs 字典，供游戏流程使用。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from game.systems.quests import QuestDef


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
