"""特性注册表：按图注入额外角色（如转职导师）的静态装配。

新增职业／NPC 时：在 jobs.py 加一个 JobDef（含 trainer_npc / starter_weapon /
技能树），再在此处登记导师的出生图注入点即可 —— 无需改动 game.py / world.py
的转职或生成逻辑。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# map_id → [(npc_id, x, y)]：脚底坐标额外生成的角色（如原版在 100000201
# 的导师赫丽娜不可达，改在出生图补一个实例）。
TRAINER_SPAWNS: Dict[str, List[Tuple[str, float, float]]] = {
    "100010000": [("1012100", -520.0, 455.0)],
}
