"""职业注册表：职业定义、技能图定位、转职门控。

数据驱动：职业/技能树/导师/转职奖励全部集中在 JOBS，新增职业只改这里。
职业名取自 WZ 现有文本（String.wz Map.img/100000000/mapDesc「可以轉職成為弓箭手」、
Npc.img/1012100 对话「你想成為弓箭手嗎？」），不另造素材。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 纯函数 ───────────────────────────────────────────────────────────
def resolve_skill_img(skill_id: str) -> str:
    """技能 id → Skill.wz 内图名：8 位取前 4 位，7 位取前 3 位。"""
    sid = str(skill_id)
    return (sid[:4] if len(sid) == 8 else sid[:3]) + ".img"


def is_ranged_weapon(item_id: str) -> bool:
    """远程武器判定：弓(145xxxxx)/弩(146xxxxx)。"""
    try:
        return int(item_id) // 10000 in (145, 146)
    except (TypeError, ValueError):
        return False


# ── 职业注册表 ───────────────────────────────────────────────────────
@dataclass
class JobDef:
    code: int
    name: str
    tree_imgs: List[str] = field(default_factory=list)   # Skill.wz 图名
    passive_ids: List[int] = field(default_factory=list)  # 转职附赠满级的被动
    advance_lv: int = 0                                   # 转职所需人物等级
    prejob: int = 0                                       # 转职前置职业（新手）
    trainer_npc: Optional[int] = None
    starter_weapon: Optional[str] = None


JOBS: Dict[int, JobDef] = {
    0: JobDef(code=0, name="新手"),
    # 弓箭手 1 转：Skill.wz/300.img；被动 精準強化/霸王箭/百步穿楊；
    # 导师赫麗娜(1012100)；转职附赠短弓(1452000)
    3000: JobDef(
        code=3000, name="弓箭手", tree_imgs=["300.img"],
        passive_ids=[3000000, 3000001, 3000002],
        advance_lv=10, trainer_npc=1012100, starter_weapon="1452000",
    ),
}


def can_advance(player, jobdef: JobDef) -> bool:
    """转职门控：当前为前置职业（新手）且等级达标。"""
    return (player.job == jobdef.prejob
            and player.level >= jobdef.advance_lv)


def skill_ids_for_job(assets, code: int) -> List[str]:
    """枚举职业技能树的全部技能 id（需 WZ，integration 用）。"""
    jobdef = JOBS.get(code)
    if jobdef is None:
        return []
    ids: List[str] = []
    for img_name in jobdef.tree_imgs:
        try:
            image = assets.wz["Skill"].root.images.get(img_name)
            if image is None:
                continue
            node = image.parse().get("skill")
            if node is None:
                continue
            ids.extend(c.name for c in node.children() if c.name.isdigit())
        except Exception:
            continue
    return ids
