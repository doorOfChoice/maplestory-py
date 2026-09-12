"""特性注册表：按图注入额外角色（如转职导师）的静态装配。

新增职业／NPC 时：在 jobs.py 加一个 JobDef（含 trainer_npc / starter_weapon /
技能树），再在此处登记导师的出生图注入点即可 —— 无需改动 game.py / world.py
的转职或生成逻辑。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# map_id → [(npc_id, x, y)]：脚底坐标额外生成的角色。教官房已可由 WZ 门直达
# （见 SCRIPT_PORTALS），故当前为空；保留此注册点供原版不可达的 NPC 使用。
TRAINER_SPAWNS: Dict[str, List[Tuple[str, float, float]]] = {}

# 脚本门登记：script 名 → (目标地图 id, 落点门名或 None=目标图 sp)。
# WZ 里这些门只给 script 名、没有 tm，去向在此写死；启动期由 game 注册进
# travel（见 travel.register_portal_scripts）。
SCRIPT_PORTALS: Dict[str, Tuple[str, Optional[str]]] = {
    "enterMagiclibrar": ("101000003", None),   # 魔法密林 → 法师导师 汉斯
    "enterAchter": ("100000201", None),        # 弓箭手村 → 弓箭手导师 赫丽娜
}
