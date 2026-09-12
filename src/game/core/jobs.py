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
    advance_sp: int = 0                                   # 转职附赠 SP（进本职业组池，原版 5/4/4）
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
    # 法师 1 转：Skill.wz/200.img；被动 魔力恢复/魔力强化 为 SP 学习（非附赠）；
    # 导师汉斯(1032001，魔法图书馆 101000003，经脚本门 enterMagiclibrar 直达)；
    # 转职附赠木制短杖(1372005，需求 Lv8 无属性要求)；魔法伤害走独立魔法区间
    # （见 player.magic_attack_range）。
    2000: JobDef(
        code=2000, name="法师", tree_imgs=["200.img"],
        advance_lv=10, advance_sp=5, trainer_npc=1032001, starter_weapon="1372005",
        hp_gain=12, mp_gain=20, auto_ap={"int": 4, "luk": 1},
    ),
    # 法师 2 转三系：火毒法师/冰雷法师/牧师。Skill.wz/210/220/230.img；沿用同一
    # 导师汉斯 1032001（魔法图书馆 101000003），转职时三系中选一；被动 魔力吸收
    # 与 1 转一致采 SP 学习（不附赠）；已有短杖故不补发。
    2100: JobDef(
        code=2100, name="火毒法师", tree_imgs=["210.img"],
        advance_lv=30, advance_sp=4, prejob=2000, trainer_npc=1032001,
        hp_gain=12, mp_gain=20, auto_ap={"int": 4, "luk": 1},
    ),
    2200: JobDef(
        code=2200, name="冰雷法师", tree_imgs=["220.img"],
        advance_lv=30, advance_sp=4, prejob=2000, trainer_npc=1032001,
        hp_gain=12, mp_gain=20, auto_ap={"int": 4, "luk": 1},
    ),
    2300: JobDef(
        code=2300, name="牧师", tree_imgs=["230.img"],
        advance_lv=30, advance_sp=4, prejob=2000, trainer_npc=1032001,
        hp_gain=12, mp_gain=20, auto_ap={"int": 4, "luk": 1},
    ),
    # 弓箭手 1 转：Skill.wz/300.img；被动 精準強化/霸王箭/百步穿楊；
    # 导师赫丽娜(1012100)；转职附赠木弓(1452002，需求 Lv10 无属性要求，
    # 短弓 1452000 需求 Lv25/DEX80 转职时穿不上)
    3000: JobDef(
        code=3000, name="弓箭手", tree_imgs=["300.img"],
        passive_ids=[3000000, 3000001, 3000002],
        advance_lv=10, advance_sp=5, trainer_npc=1012100, starter_weapon="1452002",
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
    # 弓箭手 2 转：猎人。Skill.wz/310.img；被动 精準之弓/終極之弓；
    # 沿用同一导师赫丽娜，等级门槛 Lv30；已有武器故不再补发初始武器。
    3100: JobDef(
        code=3100, name="猎人", tree_imgs=["310.img"],
        passive_ids=[3100000, 3100001],
        advance_lv=30, advance_sp=4, prejob=3000, trainer_npc=1012100,
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
    # 弓箭手 3 转：神射手。Skill.wz/311.img；被动 疾风步/致命箭；门槛 Lv70。
    3110: JobDef(
        code=3110, name="神射手", tree_imgs=["311.img"],
        passive_ids=[3110000, 3110001],
        advance_lv=70, advance_sp=4, prejob=3100, trainer_npc=1012100,
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
    # 弓箭手 4 转：弓手大师。Skill.wz/312.img（楓葉祝福/召喚鳳凰/烈火箭系进阶，
    # 龙魂之箭/暴風神射等）；被动 弓術精通；门槛 Lv120。
    3120: JobDef(
        code=3120, name="弓手大师", tree_imgs=["312.img"],
        passive_ids=[3120005],
        advance_lv=120, advance_sp=4, prejob=3110, trainer_npc=1012100,
        hp_gain=20, mp_gain=12, auto_ap={"dex": 1},
    ),
}


def can_advance(player, jobdef: JobDef) -> bool:
    """转职门控：当前为前置职业（新手）且等级达标。"""
    return (player.job == jobdef.prejob
            and player.level >= jobdef.advance_lv)


def jobs_for_trainer(npc_id, player_job: Optional[int] = None) -> List["JobDef"]:
    """回传导师 npc_id 名下、此刻可由玩家转职的目标职业列表（保持注册顺序）。

    给定 player_job 时只取前置职业恰为玩家当前职业的那一阶；一个导师可对应多个
    分支（汉斯 1032001 → 火毒/冰雷/牧师），也可跨转线性多阶（赫丽娜一人承担
    弓手 1/2/3/4 转）。不给 player_job 时返回该导师的全部职业。
    """
    return [jd for jd in JOBS.values()
            if jd.trainer_npc is not None and str(jd.trainer_npc) == str(npc_id)
            and (player_job is None or jd.prejob == player_job)]


def job_for_trainer(npc_id, player_job: Optional[int] = None) -> Optional["JobDef"]:
    """回传导师 npc_id 对应的**首个**转职目标职业（无则 None）。

    分支职业（法师二转）请改用 jobs_for_trainer 取全量；本函数保留给线性职业链
    与 NPC 自带 talk() 脚本的单目标语义。
    """
    jobs = jobs_for_trainer(npc_id, player_job)
    return jobs[0] if jobs else None


def jobdef_for_advance_quest(qid: str) -> Optional["JobDef"]:
    """转职任务 qid（adv_<code>）→ 对应目标职业；非转职任务返回 None。

    分支职业下 qid 是唯一能区分「玩家点了哪一系」的事实来源（同一教官的
    job_for_trainer 只能给出第一个分支），故 NPC 会话据此定位目标职业。
    """
    if not str(qid).startswith("adv_"):
        return None
    try:
        return JOBS.get(int(str(qid)[4:]))
    except (TypeError, ValueError):
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
