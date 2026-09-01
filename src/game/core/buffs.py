"""Buff 与状态异常：玩家侧的持续增益/减益（纯数据，不触碰 pygame）。

· BuffList：技能施加的属性修正 buff，mods 键约定为
  str/dex/int/luk（四维）、atk/def（攻防加值）、crit（暴击率 %）。
  同 skill_id 重复施加 = 刷新持续时间（数值不叠加）。
· StatusList：怪物技能造成的异常状态 —— poison（每秒按强度扣血）、
  stun（锁移动/跳跃/攻击）、slow（移速倍率）。同种重复上取更长
  剩余与更高强度。
结算入口在 player.py：total_stats/attack_value/defense_value 读取
mod_sum；update 内 tick 推进并施加中毒伤害。渲染（图标条）在 ui.py。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from game import settings


@dataclass
class Buff:
    skill_id: str
    name: str
    total: float
    remaining: float
    mods: Dict[str, int] = field(default_factory=dict)


class BuffList:
    def __init__(self):
        self._buffs: Dict[str, Buff] = {}

    def apply(self, skill_id: str, name: str, duration: float,
              mods: Dict[str, int]) -> None:
        """上 buff：同 id 覆盖刷新（持续时间重置、数值以最新为准）。"""
        self._buffs[skill_id] = Buff(skill_id, name, duration, duration,
                                     dict(mods))

    def tick(self, dt: float) -> None:
        for sid in list(self._buffs):
            b = self._buffs[sid]
            b.remaining -= dt
            if b.remaining <= 0:
                del self._buffs[sid]

    def mod_sum(self, key: str) -> int:
        return sum(b.mods.get(key, 0) for b in self._buffs.values())

    def active(self) -> List[Buff]:
        """当前生效中的 buff（按技能 id 排序，供 HUD 图标条）。"""
        return sorted(self._buffs.values(), key=lambda b: b.skill_id)

    def clear(self) -> None:
        self._buffs.clear()


@dataclass
class Status:
    kind: str
    remaining: float
    potency: float


class StatusList:
    KINDS = ("poison", "stun", "slow")

    def __init__(self):
        self._st: Dict[str, Status] = {}
        self._poison_acc = 0.0

    def apply(self, kind: str, duration: float, potency: float = 0.0) -> None:
        """上异常：同种取 max(剩余)、max(强度)；未知类型忽略。"""
        if kind not in self.KINDS or duration <= 0:
            return
        cur = self._st.get(kind)
        if cur is None:
            self._st[kind] = Status(kind, duration, potency)
        else:
            cur.remaining = max(cur.remaining, duration)
            cur.potency = max(cur.potency, potency)

    def tick(self, dt: float) -> int:
        """推进计时，返回本帧应扣的中毒伤害（先结算后过期）。"""
        dmg = 0
        poison = self._st.get("poison")
        if poison is not None:
            self._poison_acc += dt
            while self._poison_acc >= settings.POISON_TICK:
                self._poison_acc -= settings.POISON_TICK
                dmg += int(poison.potency)
        for kind in list(self._st):
            s = self._st[kind]
            s.remaining -= dt
            if s.remaining <= 0:
                del self._st[kind]
        return dmg

    def has(self, kind: str) -> bool:
        return kind in self._st

    def locked(self) -> bool:
        return "stun" in self._st

    def speed_mult(self) -> float:
        return settings.SLOW_MULT if "slow" in self._st else 1.0

    def active(self) -> List[Status]:
        return sorted(self._st.values(), key=lambda s: s.kind)

    def clear(self) -> None:
        self._st.clear()
        self._poison_acc = 0.0
