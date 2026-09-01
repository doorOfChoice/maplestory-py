"""物品 / 背包 / 装备栏：数据模型与属性计算。

· Item：一次掉落或一件装备（装备每件独立，消耗品按数量堆叠）。
· Inventory：消耗品堆叠表 + 装备列表 + 已装备栏位；穿脱装备只改数据，
  外观由 Player.equips 列表驱动（装备栏变更后调用 Player.refresh_equips）。
· 属性：武器 incPAD → 攻击力；防具 incPDD → 防御力；incSTR/DEX 等留作扩展。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import settings


# islot（Character.wz info/islot，两字符令牌的拼接，如 "WpSi"/"MaPn"）
# → 装备栏位。按令牌解析并按优先级取第一个命中的栏位。
_SLOT_BY_TOKEN = {
    "Wp": "weapon", "Ma": "top", "Pn": "pants", "So": "shoes",
    "Gv": "glove", "Cp": "cap", "Ca": "cape", "Sr": "cape",
    "Si": "shield", "Ri": "ring", "Ao": "overall", "Ay": "face",
    "Af": "face", "Ae": "face", "Ea": "earr",
}


def islot_to_slot(islot: str) -> Optional[str]:
    """把 islot 字符串映射到装备栏位；无法识别返回 None。

    复合栏位优先：MaPn（连身衣）应整体落到 overall，而不是被 Ma 命中成上衣。
    """
    if not islot:
        return None
    tokens = [islot[i:i + 2] for i in range(0, len(islot) - 1, 2)]
    if "Ma" in tokens and "Pn" in tokens:
        return "overall"
    for tok in tokens:
        slot = _SLOT_BY_TOKEN.get(tok)
        if slot is not None:
            return slot
    return None

# 装备栏位显示顺序
SLOT_ORDER = ("cap", "face", "earr", "top", "overall", "pants",
              "shoes", "glove", "cape", "ring", "shield", "weapon")

STAT_KEYS = ("incPAD", "incMAD", "incPDD", "incSTR", "incDEX",
             "incINT", "incLUK", "incHP", "incMP")


def item_kind(item_id: str) -> str:
    try:
        cat = int(item_id) // 1000000
    except (TypeError, ValueError):
        return "etc"
    if 1000000 <= int(item_id) < 2000000:
        return "equip"
    if cat == 2:
        return "consume"
    return "etc"


def make_item(item_id: str, assets, count: int = 1,
              name: Optional[str] = None) -> Item:
    """从 WZ 数据构建 Item（装备读属性表，消耗品读恢复 spec）。

    id 统一补零到 8 位：怪物掉落表的 id 是 7 位（如 "1040013"），
    而 Character.wz 的部件图名是 8 位（"01040013.img"）——不补零的
    id 会让角色合成器找不到部件，穿上去等于没穿。
    """
    kind = item_kind(item_id)
    if kind == "equip":
        info = assets.equip_info(item_id) or {}
    elif kind == "consume":
        ci = assets.consume_info(item_id) or {}
        info = {"spec": ci.get("spec") or {}}
    else:
        info = {}
    if name is None:
        name = assets.item_name(item_id) or f"物品 {item_id}"
    try:
        norm_id = f"{int(item_id):08d}"
    except (TypeError, ValueError):
        norm_id = str(item_id)
    return Item(id=norm_id, name=name, count=count, kind=kind, info=info)


@dataclass
class Item:
    id: str
    name: str = ""
    count: int = 1
    kind: str = "etc"
    info: Dict[str, Any] = field(default_factory=dict)   # 装备属性 / 消耗品 spec

    @property
    def slot(self) -> Optional[str]:
        """装备栏位（islot → slot）；非装备返回 None。"""
        return islot_to_slot(self.info.get("islot") or "")

    def stat(self, key: str) -> int:
        try:
            return int(self.info.get(key) or 0)
        except (TypeError, ValueError):
            return 0


class Inventory:
    """消耗品（id → 数量）+ 装备（散件列表）+ 已装备栏位。"""

    def __init__(self):
        self.consumes: Dict[str, Item] = {}      # id → Item(count 堆叠)
        self.etcs: Dict[str, Item] = {}          # 其他材料（矿石等，堆叠）
        self.equips: List[Item] = []             # 未装备的装备散件
        self.equipped: Dict[str, Item] = {}      # slot → Item

    # ── 收纳 ───────────────────────────────────────────────────────
    def add(self, item: Item) -> bool:
        """入包。返回是否成功（装备栏满 / 无法归类则 False）。"""
        if item.kind == "consume":
            cur = self.consumes.get(item.id)
            if cur is not None:
                cur.count += item.count
            else:
                self.consumes[item.id] = item
            return True
        if item.kind == "etc":
            cur = self.etcs.get(item.id)
            if cur is not None:
                cur.count += item.count
            else:
                self.etcs[item.id] = item
            return True
        if item.kind == "equip":
            if len(self.equips) >= settings.INVENTORY_EQUIP_CAP:
                return False
            self.equips.append(item)
            return True
        return False

    # ── 消耗品 ─────────────────────────────────────────────────────
    def use_consume(self, item_id: str) -> Optional[dict]:
        """使用一个消耗品，返回其 spec（hp/mp 恢复）；用完自动移除。"""
        item = self.consumes.get(item_id)
        if item is None or item.count <= 0:
            return None
        item.count -= 1
        spec = dict(item.info.get("spec") or {})
        if item.count <= 0:
            del self.consumes[item_id]
        return spec

    # ── 取出（扔出 / 转移用）───────────────────────────────────────
    def take_stack(self, item_id: str) -> Optional[Item]:
        """整堆取出消耗品/其他材料；不存在返回 None。"""
        for table in (self.consumes, self.etcs):
            cur = table.get(item_id)
            if cur is not None:
                del table[item_id]
                return cur
        return None

    def pop_equip(self, index: int) -> Optional[Item]:
        """取出背包中第 index 件散件装备。"""
        if 0 <= index < len(self.equips):
            return self.equips.pop(index)
        return None

    def pop_equipped(self, slot: str) -> Optional[Item]:
        """从装备栏直接取下某栏位（不占背包，扔出用）。"""
        return self.equipped.pop(slot, None)

    # ── 穿脱 ───────────────────────────────────────────────────────
    def equip(self, index: int) -> bool:
        """装备 equips[index]；同栏位旧装备自动脱下换回。

        连身衣(overall)与 上衣(top)/裤子(pants) 互斥：穿连身衣时
        自动脱下上衣和裤子，穿上上衣或裤子时自动脱下连身衣。
        """
        if not (0 <= index < len(self.equips)):
            return False
        item = self.equips.pop(index)
        slot = item.slot
        if slot is None:
            self.equips.append(item)
            return False
        old = self.equipped.get(slot)
        self.equipped[slot] = item
        if old is not None:
            self.equips.append(old)
        # overall ↔ top/pants 互斥
        if slot == "overall":
            for s in ("top", "pants"):
                self._move_to_bag(s)
        elif slot in ("top", "pants"):
            self._move_to_bag("overall")
        return True

    def _move_to_bag(self, slot: str) -> None:
        item = self.equipped.pop(slot, None)
        if item is not None and len(self.equips) < settings.INVENTORY_EQUIP_CAP:
            self.equips.append(item)
        elif item is not None:
            self.equipped[slot] = item

    def unequip(self, slot: str) -> bool:
        item = self.equipped.pop(slot, None)
        if item is None or len(self.equips) >= settings.INVENTORY_EQUIP_CAP:
            if item is not None:
                self.equipped[slot] = item
            return False
        self.equips.append(item)
        return True

    def equip_ids(self) -> List[str]:
        """当前外观装备 id 列表（含默认身体/头发/脸），供 Player 渲染。"""
        ids = list(settings.DEFAULT_EQUIPS[:4])     # body / head / face / hair 基底
        for slot in SLOT_ORDER:
            item = self.equipped.get(slot)
            if item is not None:
                ids.append(item.id)
        return ids

    # ── 属性汇总 ───────────────────────────────────────────────────
    def stat_sum(self, key: str) -> int:
        return sum(i.stat(key) for i in self.equipped.values())

    def bonus(self, key: str) -> int:
        """装备词条（str/dex/int/luk/hp/mp 等直接键）求和。"""
        return self.stat_sum(key)

    def attack(self) -> int:
        return self.stat_sum("incPAD")

    def defense(self) -> int:
        return self.stat_sum("incPDD")

    def total_items(self) -> int:
        return (sum(i.count for i in self.consumes.values())
                + sum(i.count for i in self.etcs.values())
                + len(self.equips))

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "consumes": {k: v.count for k, v in self.consumes.items()},
            "etcs": {k: v.count for k, v in self.etcs.items()},
            "equips": [i.id for i in self.equips],
            "equipped": {k: v.id for k, v in self.equipped.items()},
        }

    @classmethod
    def from_dict(cls, data: dict, assets=None) -> Inventory:
        inv = cls()
        for id_, count in data.get("consumes", {}).items():
            item = (make_item(id_, assets, count) if assets
                    else Item(id=id_, count=count, kind="consume"))
            inv.consumes[id_] = item
        for id_, count in data.get("etcs", {}).items():
            item = (make_item(id_, assets, count) if assets
                    else Item(id=id_, count=count, kind="etc"))
            inv.etcs[id_] = item
        for eid in data.get("equips", []):
            item = make_item(eid, assets) if assets else Item(id=eid, kind="equip")
            inv.equips.append(item)
        for slot, eid in data.get("equipped", {}).items():
            item = make_item(eid, assets) if assets else Item(id=eid, kind="equip")
            if assets and item.slot is not None:
                inv.equipped[item.slot] = item
            elif not assets:
                inv.equipped[slot] = item
        return inv
