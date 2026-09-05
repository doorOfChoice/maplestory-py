"""装备 tooltip 纯构建器：原版分段 → 结构化 EquipTip，视图层照单渲染。

不依赖 pygame / WZ：入参为 Item 的鸭子字段（name/info/extra/tuc/slot/id）+
玩家等级/四维/职业码 + String.wz 介绍，输出 EquipTip（含图标 id、攻击/魔法力
大数字、REQ、职业可穿标记、装备分类、词条、可升级次数、介绍）。
分段与配色照原版：名称 / 交换性标记 / 攻击力·魔法力大数字 / REQ /
职业（可穿高亮）/ 装备分类 / 完整词条（强化附加标绿）/ 可升级次数 / 介绍。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Optional, Sequence, Tuple

Color = Tuple[int, int, int]

WHITE: Color = (235, 238, 245)
GRAY: Color = (150, 155, 165)
RED: Color = (255, 85, 85)
GREEN: Color = (120, 220, 130)
BLUE: Color = (140, 190, 255)
STAT_BLUE: Color = (150, 205, 255)   # 词条数值蓝（参考图词条一致）
CRIMSON: Color = (215, 70, 70)       # 攻击力提升大数字

# 装备栏位 → 分类名（纸娃娃标签共用）
SLOT_NAMES = {
    "cap": "帽子", "face": "脸饰", "earr": "耳环", "top": "上衣",
    "overall": "连身衣", "pants": "裤子", "shoes": "鞋子",
    "glove": "手套", "cape": "披风", "ring": "戒指",
    "shield": "盾牌", "weapon": "武器",
}

# reqJob 位掩码 → 职业名（新手无位，仅 reqJob=0 可穿）
JOB_LABELS: Sequence[Tuple[str, int]] = (
    ("新手", 0), ("战士", 1), ("魔法师", 2),
    ("弓箭手", 4), ("飞侠", 8), ("海盗", 16),
)

# REQ 四维 → (WZ 键, 英文短名)
_REQ_STAT_KEYS: Sequence[Tuple[str, str]] = (
    ("reqSTR", "STR"), ("reqDEX", "DEX"), ("reqINT", "INT"), ("reqLUK", "LUK"),
)

# 词条行：(WZ 键, 标签, 是否按 0.1 点显示)
_STAT_ROWS: Sequence[Tuple[str, str, bool]] = (
    ("incSTR", "力量", False), ("incDEX", "敏捷", False),
    ("incINT", "智力", False), ("incLUK", "运气", False),
    ("incPAD", "攻击力", False), ("incMAD", "魔法力", False),
    ("incPDD", "防御力", False), ("incMDD", "魔防", False),
    ("incMHP", "最大血量", False), ("incMMP", "最大魔量", False),
    ("incACC", "命中", False), ("incEVA", "回避", False),
    ("incSpeed", "速度", True), ("incJump", "跳跃", True),
)


@dataclass(frozen=True)
class Seg:
    """一段同色文字；big 标记大数字（通用 tooltip 视图放大绘制）。"""
    text: str
    color: Color = WHITE
    big: bool = False


@dataclass(frozen=True)
class TipLine:
    """通用 tooltip 一行（装备之外的别处仍沿用）。"""
    segs: Tuple[Seg, ...]


@dataclass(frozen=True)
class HeroValue:
    """顶部英雄区的一条大数字（攻击力/魔法力提升）。"""
    label: str
    value: int
    color: Color


@dataclass(frozen=True)
class ReqStat:
    """一条需求数值；ok 表示玩家当前是否满足。"""
    key: str      # 英文短名（STR/DEX/...）
    need: int
    ok: bool


@dataclass(frozen=True)
class StatRow:
    """一条词条；total = 基础 + 强化，extra 为强化附加部分（0 表示无）。"""
    label: str
    total: int
    extra: int
    tenth: bool


@dataclass(frozen=True)
class EquipTip:
    """装备 tooltip 完整结构（视图层照单渲染）。"""
    name: str
    item_id: str
    slot: Optional[str]
    flags: Tuple[str, ...]                 # 商城物品 / 固有装备物品 / 不可交换 ...
    heroes: Tuple[HeroValue, ...]          # 攻击力/魔法力提升大数字
    req_level: Optional[int]
    req_level_ok: bool
    req_stats: Tuple[ReqStat, ...]         # 仅非零需求
    jobs: Tuple[Tuple[str, bool], ...]     # (职业名, 当前职业可穿)
    category: str
    stats: Tuple[StatRow, ...]
    tuc: int
    note: str                              # String.wz 介绍（可空）


def _i(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _signed(v: float, tenth: bool = False) -> str:
    """词条数值文本：tenth 时按 0.1 点换算（15→1.5、10→1）。"""
    if tenth:
        v = v / 10.0
    num = f"{int(v)}" if float(v) == int(v) else f"{v:.1f}"
    return f"+{num}" if v > 0 else num


def build_item_tip(item: Any, level: int, stats: Mapping[str, int],
                   job: Optional[int], desc: str = "") -> EquipTip:
    """构建装备 tooltip。stats 传玩家四维合计（含装备），不足需求标红。"""
    info: Mapping[str, Any] = getattr(item, "info", None) or {}
    extra: Mapping[str, int] = getattr(item, "extra", None) or {}
    name = getattr(item, "name", "") or ""
    item_id = str(getattr(item, "id", ""))

    flags = []
    if _i(info.get("cash")):
        flags.append("商城物品")
    if _i(info.get("only")):
        flags.append("固有装备物品")
    if any(_i(info.get(k)) for k in ("tradeBlock", "notSale", "equipTradeBlock")):
        flags.append("不可交换")

    heroes = []
    pad = _i(info.get("incPAD")) + _i(extra.get("incPAD"))
    mad = _i(info.get("incMAD")) + _i(extra.get("incMAD"))
    if pad:
        heroes.append(HeroValue("攻击力提升", pad,
                                CRIMSON if pad > 0 else RED))
    if mad:
        heroes.append(HeroValue("魔法力提升", mad,
                                BLUE if mad > 0 else RED))

    req_level = _i(info.get("reqLevel")) or None
    req_stats = []
    for key, short in _REQ_STAT_KEYS:
        need = _i(info.get(key))
        if need:
            req_stats.append(ReqStat(short, need,
                                     stats.get(key[3:].lower(), 0) >= need))

    req_job = _i(info.get("reqJob"))
    jobs = tuple((label, not req_job or (bit and bool(req_job & bit)))
                 for label, bit in JOB_LABELS)

    slot = getattr(item, "slot", None)
    stats_rows = []
    for key, label, tenth in _STAT_ROWS:
        base, ex = _i(info.get(key)), _i(extra.get(key))
        total = base + ex
        if not total and not ex:
            continue
        stats_rows.append(StatRow(label, total, ex, tenth))

    return EquipTip(
        name=name, item_id=item_id, slot=slot, flags=tuple(flags),
        heroes=tuple(heroes), req_level=req_level,
        req_level_ok=(level >= req_level if req_level else True),
        req_stats=tuple(req_stats), jobs=jobs,
        category=SLOT_NAMES.get(slot, "") if slot else "",
        stats=tuple(stats_rows), tuc=_i(getattr(item, "tuc", 0)),
        note=desc,
    )


def tip_with_note(tip: EquipTip, extra: str) -> EquipTip:
    """在介绍尾部追加一行提示（如「点击穿上」）。"""
    if not extra:
        return tip
    note = (tip.note + "\n" if tip.note else "") + extra
    return replace(tip, note=note)
