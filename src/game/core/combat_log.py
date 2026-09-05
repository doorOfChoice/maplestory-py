"""右下角战斗明细模型：击杀经验 / 拾取金币 / 拾取物品的浮动条目。

每次击杀/拾取各出一条条目（不合并）；条目存活 ttl 秒的最后 fade 秒
线性淡出后清除；总量超上限挤掉最旧一条。纯状态机不碰 pygame，
时间源可注入。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, List


@dataclass
class CombatLogEntry:
    """一条战斗明细：kind=exp/meso/item，amount 为累加后的经验/金币/数量。"""

    kind: str
    key: str            # 事件对象 id：怪 id / "meso" / 物品 id
    name: str           # 展示名（金币条目不显示名字）
    amount: int
    born: float
    ttl: float          # 存活时长（秒），最后 fade 秒淡出
    fade: float         # 淡出窗口（秒）
    _now: Callable[[], float] = field(default=0.0, repr=False)

    @property
    def age(self) -> float:
        return self._now() - self.born

    @property
    def alpha(self) -> float:
        """渲染不透明度：淡出窗口前全亮，窗口内线性降到 0。"""
        t = self.age - (self.ttl - self.fade)
        if t <= 0.0:
            return 1.0
        return max(0.0, 1.0 - t / self.fade)


class CombatLog:
    ttl: float = 3.0        # 条目存活时长（秒），到期后再经 fade 淡出
    fade: float = 1.0       # 淡出窗口（秒）
    max_entries: int = 6    # 同时保留的条目数上限

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self.entries: List[CombatLogEntry] = []

    # ── 事件入口 ─────────────────────────────────────────────────────
    def add_exp(self, mob_id: str, name: str, amount: int) -> None:
        """击杀结算：经验 ≤0（回退怪/特殊怪）不出条目。"""
        if amount > 0:
            self._push("exp", str(mob_id), name, amount)

    def add_meso(self, amount: int) -> None:
        """拾取金币结算。"""
        if amount > 0:
            self._push("meso", "meso", "", amount)

    def add_item(self, item_id: str, name: str, count: int) -> None:
        """拾取物品结算。"""
        if count > 0:
            self._push("item", str(item_id), name, count)

    # ── 维护 ─────────────────────────────────────────────────────────
    def update(self) -> None:
        """清除过期条目（时间源驱动，无需 dt）。"""
        self.entries = [e for e in self.entries if e.age < self.ttl]

    def _push(self, kind: str, key: str, name: str, amount: int) -> None:
        self.entries.append(CombatLogEntry(
            kind=kind, key=key, name=name, amount=amount,
            born=self._now(), ttl=self.ttl, fade=self.fade, _now=self._now))
        if len(self.entries) > self.max_entries:
            del self.entries[:len(self.entries) - self.max_entries]
