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


# 双手武器类别：双手剑/双手斧/双手锤/长枪/铁戟（长杖 138 原版用单手姿态）
TWO_HANDED_CATEGORIES = (140, 141, 142, 143, 144)


def is_two_handed_weapon(item_id: str) -> bool:
    """双手武器判定：攻击动画使用 swingT*/stabT* 姿态的类别。"""
    try:
        return int(item_id) // 10000 % 1000 in TWO_HANDED_CATEGORIES
    except (TypeError, ValueError):
        return False


# ── 职业注册表 ───────────────────────────────────────────────────────
@dataclass
class JobDef:
    code: int
    name: str
    tree_imgs: List[str] = field(default_factory=list)   # Skill.wz 图名
    # 树内白名单：None = 全树加载；给定则只取列出的技能 id
    # （1000.img 是占位树，混满乘骑/合成等杂项，新手只露蜗牛投掷术）
    skill_ids: Optional[List[str]] = None
    passive_ids: List[int] = field(default_factory=list)  # 转职附赠满级的被动
    advance_lv: int = 0                                   # 转职所需人物等级
    prejob: int = 0                                       # 转职前置职业（新手）
    trainer_npc: Optional[int] = None
    starter_weapon: Optional[str] = None
    hp_gain: int = 15                                     # 每级 HP 成长
    mp_gain: int = 10                                     # 每级 MP 成长
    auto_ap: Dict[str, int] = field(                      # 一键自动加点权重
        default_factory=lambda: {"str": 1})


JOBS: Dict[int, JobDef] = {
    # 新手技能树：Skill.wz/1000.img 的 10001000（台版名「嫩寶丟擲術」，即经典
    # 蜗牛投掷术；该树只有图标占位，数值表由 skills.py 合成）
    0: JobDef(code=0, name="新手", tree_imgs=["1000.img"],
              skill_ids=["10001000"]),
    # 弓箭手 1 转：Skill.wz/300.img；被动 精準強化/霸王箭/百步穿楊；
    # 导师赫丽娜(1012100)；转职附赠木弓(1452002，需求 Lv10 无属性要求，
    # 短弓 1452000 需求 Lv25/DEX80 转职时穿不上)
    3000: JobDef(
        code=3000, name="弓箭手", tree_imgs=["300.img"],
        passive_ids=[3000000, 3000001, 3000002],
        advance_lv=10, trainer_npc=1012100, starter_weapon="1452002",
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
    # 弓箭手 2 转：猎人。Skill.wz/310.img；被动 精準之弓/終極之弓；
    # 沿用同一导师赫丽娜，等级门槛 Lv30；已有武器故不再补发初始武器。
    3100: JobDef(
        code=3100, name="猎人", tree_imgs=["310.img"],
        passive_ids=[3100000, 3100001],
        advance_lv=30, prejob=3000, trainer_npc=1012100,
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
    # 弓箭手 3 转：神射手。Skill.wz/311.img；被动 疾风步/致命箭；门槛 Lv70。
    3110: JobDef(
        code=3110, name="神射手", tree_imgs=["311.img"],
        passive_ids=[3110000, 3110001],
        advance_lv=70, prejob=3100, trainer_npc=1012100,
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
}


def can_advance(player, jobdef: JobDef) -> bool:
    """转职门控：当前为前置职业（新手）且等级达标。"""
    return (player.job == jobdef.prejob
            and player.level >= jobdef.advance_lv)


def job_for_trainer(npc_id, player_job: Optional[int] = None) -> Optional["JobDef"]:
    """回传导师 npc_id 对应的转职目标职业（无则 None）。

    给定 player_job 时按职业链解析：返回以该 NPC 为导师、且前置职业恰为玩家
    当前职业的那一阶（赫丽娜一人承担 1/2/3 转）；已达最高阶或职业不符则 None。
    不给 player_job 时回退旧语义：首个匹配该导师的职业。
    """
    for jd in JOBS.values():
        if jd.trainer_npc is None or str(jd.trainer_npc) != str(npc_id):
            continue
        if player_job is None or jd.prejob == player_job:
            return jd
    return None


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
    if jobdef.skill_ids is not None:
        allow = set(jobdef.skill_ids)
        ids = [i for i in ids if i in allow]
    return ids


def job_chain(code: int) -> List[JobDef]:
    """职业链：沿 prejob 上溯到根，回传有技能树的职业（旧→新，如 猎人 → [弓箭手, 猎人]）。

    新手（无 tree_imgs）不入链；用于累积加载各转技能树与逐转 SP 归集。
    """
    out: List[JobDef] = []
    seen: set = set()
    cur = code
    while cur in JOBS and cur not in seen:
        seen.add(cur)
        jd = JOBS[cur]
        if jd.tree_imgs:
            out.append(jd)
        if jd.prejob == cur:
            break
        cur = jd.prejob
    out.reverse()
    return out


def sp_group_of_skill(skill_id: str) -> int:
    """技能 id → 所属 SP 职业组（技能图前三位，如 3101002→310、3000000→300）。"""
    return int(resolve_skill_img(skill_id)[:3])


def job_sp_group(code: int) -> int:
    """职业代码 → SP 职业组（3000→300、3110→311）。

    新手特殊：其技能在 1000.img（id 前缀组 100），与 sp_group_of_skill 对齐。
    """
    return 100 if code == 0 else code // 10


def skill_ids_for_chain(assets, code: int) -> List[str]:
    """职业链上所有职业的技能 id 并集（累积多转技能树，需 WZ）。"""
    ids: List[str] = []
    for jd in job_chain(code):
        ids.extend(skill_ids_for_job(assets, jd.code))
    return ids
