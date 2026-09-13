"""技能分面模型：把「一个技能」拆成交付方式 + 代价 + 效果子句（纯数据，无 WZ / pygame）。

设计哲学（对齐全量 Skill.wz 的 525 个职业技能）：
· WZ 顶层节点只可靠地表达**怎么放**（交付方式：弹道/瞬发/召唤/地面/引导…），
  level 表字段表达**放了会怎样**（载荷：伤害/增益/状态/回蓝…），两者正交。
· 因此本模块不再给技能贴「单一类型」，而是让 `SkillSpec` 同时持有
  `kind`（交付）+ `effects(level)`（载荷子句列表）。执行层只认子句类型，
  不认技能 id；新增技能默认零改动。
· 所有子句为 frozen dataclass，可 `==` 比较，便于纯单元测试断言。
· 数值随等级变化，故 `cost`/`effects` 以「等级 → 结果」的可调用形式持有，
  模型本身保持不可变；惰性解析的收益（不预存 525 份表）也得以保留。

字段语义（如 x/y/prop 各技能不同）由 core.skill_semantics 的结构默认 +
声明式例外表翻译，本模块只管表达结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple, Union

# ── 交付方式（WZ 顶层节点推导；字符串与旧 cast_form 兼容）─────────────
# passive  已登记被动，不可落键
# heal     群体治愈（回血 + 对不死系伤害）
# teleport 快速移动（按方向键位移）
# buff     纯持续增益（扣消耗直接上 buff）
# projectile 弹道（ball 节点）
# instant  瞬发命中（hit / 伤害字段）
# aoe      瞬发且带 lt/rb（自身矩形结算）
# mob_status 无伤害的对怪状态（mob 节点）
# summon   召唤物（summon 节点）
# field    地面/持续区域（tile 节点）
# channel  引导技（keydown，按住连发）
# aura     团队/范围增益（affected 节点）
# move     位移技（range/冲刺）
# unsupported 无任何施放标记
DELIVERY_KINDS: Tuple[str, ...] = (
    "passive", "heal", "teleport", "buff", "projectile", "instant", "aoe",
    "mob_status", "summon", "field", "channel", "aura", "move", "unsupported",
)

# 目标选择
TARGET_SELF = "self"
TARGET_SINGLE = "single"
TARGET_MULTI = "multi"
TARGET_AREA = "area"
TARGET_PARTY = "party"

# WZ lt/rb 矩形（相对 navel）：((lt_x, lt_y), (rb_x, rb_y))
Area = Tuple[Tuple[int, int], Tuple[int, int]]


# ── 代价 ─────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Cost:
    """施放代价（全部来自 level 表）。"""
    mp: int = 0
    hp: int = 0
    item_id: str = ""          # itemCon
    item_count: int = 0        # itemConNo
    mesos: int = 0             # moneyCon
    cooldown: float = 0.0      # cooltime（秒）


# ── 效果子句 ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Proc:
    """命中/受击时按概率触发的附加效果（终极追击、必杀、闪避、暴击）。"""
    kind: str                  # final_attack|deadly|dodge|critical
    chance: int = 0            # 触发概率 %
    mult: float = 0.0          # 附带伤害倍率（final_attack/deadly）
    threshold: int = 0         # 触发阈值（必杀：目标 HP% 上限）


@dataclass(frozen=True)
class Debuff:
    """对目标施加的状态（怪物 debuff / 命中附带状态）。"""
    status: str                # freeze|poison|slow|stun|seal|...
    chance: int = 0            # 概率 %
    duration: float = 0.0      # 持续秒数（time）
    potency: int = 0           # 强度（slow 的 x、毒伤等级等）
    area: Optional[Area] = None
    max_targets: int = 1


@dataclass(frozen=True)
class Damage:
    """伤害载荷。"""
    mult: float = 1.0          # damage/100；魔法技为 1.0，实际倍率走 skill_mad
    fixed: int = 0             # 固定伤害值：>0 时无视攻击力/怪防/等级差，直接造成该值
    hits: int = 1              # attackCount（多段）
    shots: int = 1             # bulletCount（多发）
    max_targets: int = 1       # mobCount
    area: Optional[Area] = None
    element: str = ""
    magic: bool = False
    skill_mad: int = 0         # 魔法技的 Basic（mad）
    mastery: int = 0
    drain_pct: int = 0         # 生命吸收：造成伤害的 x% 回血
    status: Optional[Debuff] = None   # 命中附带怪状态
    procs: Tuple[Proc, ...] = ()


@dataclass(frozen=True)
class Buff:
    """持续增益。party=True 为团队/范围增益（affected）。"""
    mods: Dict[str, int] = field(default_factory=dict)
    duration: float = 0.0
    party: bool = False
    area: Optional[Area] = None


@dataclass(frozen=True)
class Heal:
    """治疗：pct 恢复率 %，对不死系同作伤害倍率。"""
    pct: int = 0
    area: Optional[Area] = None
    undead: bool = True


@dataclass(frozen=True)
class Summon:
    """召唤物。"""
    template: str = ""         # 召唤物 id（skill.summon 或 fallback 技能 id）
    duration: float = 0.0      # time
    attack: int = 0            # pad（物理召唤物）/ mad（魔法召唤物）
    interval: float = 0.0      # 出手间隔（素材缺省时按 settings）
    count: int = 1
    magic: bool = False        # 魔法召唤物：按怪物魔防（mdd）结算


@dataclass(frozen=True)
class Field:
    """地面/持续区域：按 interval 对区域内目标结算 effects。"""
    area: Optional[Area] = None
    duration: float = 0.0
    interval: float = 0.0
    effects: Tuple["Effect", ...] = ()


@dataclass(frozen=True)
class Move:
    """位移技。mode: teleport|dash|jump。"""
    distance: int = 0
    mode: str = "teleport"


@dataclass(frozen=True)
class Morph:
    """变身/形态改变。"""
    form: str = ""
    duration: float = 0.0
    mods: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Cleanse:
    """解除异常状态。"""
    kinds: Tuple[str, ...] = ()


Effect = Union[Damage, Buff, Debuff, Heal, Summon, Field, Move, Proc, Morph,
               Cleanse]

CostFn = Callable[[int], Cost]
EffectFn = Callable[[int], Tuple[Effect, ...]]


@dataclass(frozen=True)
class SkillSpec:
    """一个技能的分面描述（按等级惰性产出代价与效果子句）。"""
    id: str
    name: str
    desc: str
    max_level: int
    master_level: int
    kind: str = "unsupported"
    targeting: str = TARGET_SINGLE
    element: str = ""
    action: str = ""
    invisible: bool = False
    repeat: bool = False
    req: Dict[str, int] = field(default_factory=dict)
    char_level: int = 0
    cost: CostFn = lambda level: Cost()            # noqa: E731
    effects: EffectFn = lambda level: ()           # noqa: E731

    def cost_at(self, level: int) -> Cost:
        return self.cost(max(1, level))

    def effects_at(self, level: int) -> Tuple[Effect, ...]:
        return self.effects(max(1, level))

    def damage_at(self, level: int) -> Optional[Damage]:
        """取该级的伤害子句（无则 None），供执行层快速取用。"""
        for e in self.effects_at(level):
            if isinstance(e, Damage):
                return e
        return None

    def buff_at(self, level: int) -> Optional[Buff]:
        for e in self.effects_at(level):
            if isinstance(e, Buff):
                return e
        return None
