"""NPC 寒暄台词表。

官方客户端的 NPC 对话脚本不在 WZ 资产里（在 Quest/*.js 中），故按 NPC 人设
手写台词：每个 NPC 若干套，每次对话随机取一套；未收录的 NPC 回退到通用池，
保证不同 NPC 的对话内容不再千篇一律。

Lua 脚本可通过导出 dialogues() 注册台词池，启动时合并进 DIALOGUES。
"""

from __future__ import annotations

import random
from typing import Dict, List

# npc_id → 台词套组（每套为若干行）
DIALOGUES: Dict[str, List[List[str]]] = {
    
}

# 通用池：未收录 NPC 的寒暄（随机取一套）
GENERIC: List[List[str]] = [
    ["你好呀，冒险者！今天天气真适合练功。"],
    ["有什么需要帮忙的吗？我只是个过路人。",
     "不过要是聊到枫之谷的八卦，我可就不困了。"],
    ["前面是怪物的地盘，小心脚下。"],
    ["呵呵，看你装备渐佳，是个人物。",
     "有空常来坐坐。"],
]


def register_lua_dialogue(npc_id: str, lines: List[List[str]]) -> None:
    """把 Lua 脚本的台词池合并进 DIALOGUES。"""
    DIALOGUES[str(npc_id)] = [list(s) for s in lines]


def get_dialog(npc_id: str, npc_name: str = "") -> List[str]:
    """取该 NPC 的一套寒暄台词（随机）；未收录则回退通用池。"""
    pool = DIALOGUES.get(str(npc_id)) or GENERIC
    return list(random.choice(pool))
