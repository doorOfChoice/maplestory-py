"""战斗快捷栏数据：把「技能槽 + 绑定消耗品」折成 HUD 可直绘的槽位列表。

纯逻辑（不碰 pygame / 素材）：UI 层拿 HotbarSlot 画图标、冷却遮罩与余量，
解决「技能在冷却吗 / 绑了哪瓶药 / 还剩几瓶」战斗中全盲的问题。冷却读数
来自 SkillBook.cooldowns / cooldown_totals（剩余与总时长，算遮罩比例）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from game.core.keybindings import (SKILL_SLOT_COUNT, display_key,
                                   item_id_of_action)


@dataclass(frozen=True)
class HotbarSlot:
    kind: str                 # skill | item
    ref_id: str               # 技能 id / 物品 id
    label: str                # 键帽文本（如 1 / Q / W）
    name: str = ""            # 悬停/兜底文本
    cd_remain: float = 0.0    # 技能冷却剩余（秒）
    cd_total: float = 0.0     # 本次冷却总时长（遮罩比例）
    count: Optional[int] = None   # 消耗品持有数（None = 查不到）

    @property
    def cooling(self) -> bool:
        return self.cd_remain > 0.0


def build_hotbar(player, bindings) -> List[HotbarSlot]:
    """按技能槽 1..N 顺序 + 物品绑定排一份槽位快照（无数据即空列表）。"""
    slots: List[HotbarSlot] = []
    if player is None or bindings is None:
        return slots
    book = getattr(player, "skills", None)
    if book is not None:
        levels = getattr(book, "levels", {})
        for n in range(1, SKILL_SLOT_COUNT + 1):
            sid = book.hotkeys.get(n)
            if sid is None or not levels.get(sid, 0):
                continue
            key = bindings.slot_key(n)
            remain = float(book.cooldowns.get(sid, 0.0) or 0.0)
            total = float(getattr(book, "cooldown_totals", {})
                          .get(sid, remain) or 0.0)
            d = book.defs.get(sid)
            slots.append(HotbarSlot(
                kind="skill", ref_id=sid,
                label=display_key(key) if key and key > 0 else str(n),
                name=d.name if d is not None else sid,
                cd_remain=max(0.0, remain), cd_total=max(remain, total)))
    inv = getattr(player, "inventory", None)
    for action, key in sorted(bindings.keys.items()):
        item_id = item_id_of_action(action)
        if item_id is None or key is None or key <= 0:
            continue
        count: Optional[int] = None
        name = ""
        if inv is not None:
            cur = inv.consumes.get(item_id)
            count = cur.count if cur is not None else 0
            name = cur.name if cur is not None else ""
        slots.append(HotbarSlot(kind="item", ref_id=item_id,
                                label=display_key(key), name=name,
                                count=count))
    return slots
