"""任务系统：解析 Quest.wz（Check/Act/Say/QuestInfo）→ QuestDef 数据模型。

· QuestDef：单一任务的全部静态数据 —— 接取条件（给予 NPC / 等级 / 职业 / 前置任务 /
  所需物品）、完成条件（交付 NPC / 击杀 mob / 收集 item）、接取奖励（Act/0）、
  完成奖励（Act/1：exp / meso / 物品，负数=收回）、nextQuest 连锁、Say 对话文本。
· 文本标记渲染：把官方 Say 文本（#b/#r/#k 颜色、#p# NPC名、#t# 物品名、#m# 地图名、
  #o# 怪物名、#L..#l# 选项、\\n 换行）解析成可绘制的纯文本行。
· QuestLog：玩家运行时的任务状态机 —— 未接 / 进行中 / 已完成，进度计数（击杀 / 收集）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from game.render.assets import Assets
from game.core.localize import to_simplified

# 任务状态
Q_AVAILABLE = "available"    # 可接取（条件满足，由 NPC 提供）
Q_ACCEPTED = "accepted"      # 进行中
Q_COMPLETED = "completed"    # 已完成


def _get(node, key):
    return node.get(key) if node is not None else None


def _int(node) -> int:
    if node is None:
        return 0
    try:
        return int(node.value)
    except (TypeError, ValueError):
        return 0


def _str(node) -> str:
    if node is None:
        return ""
    try:
        return to_simplified(str(node.value))
    except (TypeError, ValueError):
        return ""


def _child_map(sub) -> Dict[str, Any]:
    """WzSubProperty 的命名子节点 → dict。"""
    if sub is None:
        return {}
    return {c.name: c for c in sub.children()}


def _list_pairs(sub, key_id: str = "id", key_count: str = "count") -> List[Tuple[int, int]]:
    """解析形如 item/0/{id,count} 的列表。"""
    out: List[Tuple[int, int]] = []
    if sub is None:
        return out
    for c in sub.children():
        m = _child_map(c)
        if key_id in m:
            out.append((_int(m[key_id]), _int(m.get(key_count))))
    return out


def _parse_jobs(job_sub) -> List[int]:
    """job 节点下 0..N 的职业限制；无限制返回空列表。"""
    if job_sub is None:
        return []
    return [_int(c) for c in job_sub.children() if c.name.isdigit()]


def _say_lines(sub) -> List[str]:
    """把 Say 节点下的 0..N 个数字子节点按顺序收集成文本行。"""
    lines: List[str] = []
    if sub is None:
        return lines
    kids = sorted((c for c in sub.children() if c.name.isdigit()),
                  key=lambda c: int(c.name))
    for c in kids:
        v = _str(c)
        if v:
            lines.append(v)
    return lines


@dataclass
class QuestDef:
    qid: str
    name: str = ""
    parent: str = ""
    order: int = 0
    area: int = 0
    # ── 接取条件（Check/0）──────────────────────────────
    start_npc: Optional[int] = None
    lvmin: int = 0
    lvmax: int = 0            # 0 = 不限
    jobs: List[int] = field(default_factory=list)   # 空 = 不限
    start_items: List[Tuple[int, int]] = field(default_factory=list)  # 接取需持有
    prereq: List[Tuple[object, int]] = field(default_factory=list)    # (quest qid, state)
    # ── 完成条件（Check/1）──────────────────────────────
    end_npc: Optional[int] = None
    kills: List[Tuple[int, int]] = field(default_factory=list)        # (mob, count)
    end_items: List[Tuple[int, int]] = field(default_factory=list)    # (item, count)
    # ── 接取奖励（Act/0）────────────────────────────────
    accept_items: List[Tuple[int, int]] = field(default_factory=list)
    # ── 完成奖励（Act/1）────────────────────────────────
    reward_exp: int = 0
    reward_money: int = 0
    reward_items: List[Tuple[int, int]] = field(default_factory=list) # 负数=收回
    next_quest: Optional[int] = None
    # ── Say 对话 ────────────────────────────────────────
    accept_lines: List[str] = field(default_factory=list)
    accept_yes: List[str] = field(default_factory=list)
    accept_no: List[str] = field(default_factory=list)
    complete_lines: List[str] = field(default_factory=list)
    complete_yes: List[str] = field(default_factory=list)
    complete_stop: List[str] = field(default_factory=list)   # 条件未满足时的提示
    # ── Lua 驱动 ─────────────────────────────────────────
    script: Optional[str] = None  # 设为脚本名（如 "advance"）时，NPC 对话由 Lua 会话驱动
    # ── QuestInfo 描述 ──────────────────────────────────
    desc0: str = ""           # 接取前提示
    desc1: str = ""           # 进行中描述
    desc2: str = ""           # 完成描述

    # ── 便捷查询 ────────────────────────────────────────
    def kill_req(self, mob_id: int) -> int:
        for mid, count in self.kills:
            if mid == mob_id:
                return count
        return 0

    def item_req(self, item_id: int) -> int:
        for iid, count in self.end_items:
            if iid == item_id:
                return count
        return 0


def load_quest_defs(assets: Assets,
                    qids: Optional[Iterable[str]] = None,
                    on_progress=None) -> Dict[str, QuestDef]:
    """从 Quest.wz 解析任务 → {qid: QuestDef}。失败静默跳过。

    ``qids`` 给定时只解析这些任务的子树（parse_partial 按顶层节点名跳过
    其余 block）；为 None 时解析全部。``on_progress(done, total)`` 每 100 个
    任务回报一次，末尾补齐 done == total，供开屏进度条细化。
    """
    wz = assets.wz["Quest"]
    root = wz.root
    check_img = root.images.get("Check.img")
    act_img = root.images.get("Act.img")
    say_img = root.images.get("Say.img")
    info_img = root.images.get("QuestInfo.img")
    if check_img is None:
        return {}

    if qids is None:
        check = check_img.parse()
        act = act_img.parse() if act_img is not None else None
        say = say_img.parse() if say_img is not None else None
        info = info_img.parse() if info_img is not None else None
        wanted = [n.name for n in check.children() if n.name.isdigit()]
    else:
        wanted = [q for q in qids if str(q).isdigit()]
        only = frozenset(wanted)
        check = check_img.parse_partial(only=only)
        act = act_img.parse_partial(only=only) if act_img is not None else None
        say = say_img.parse_partial(only=only) if say_img is not None else None
        info = info_img.parse_partial(only=only) if info_img is not None else None

    defs: Dict[str, QuestDef] = {}
    total = len(wanted)
    for i, qid in enumerate(wanted):
        node = check.get(qid)
        if node is not None:
            try:
                d = _parse_one(qid, node, act, say, info)
            except Exception:
                d = None
            if d is not None:
                defs[qid] = d
        if on_progress is not None and (i + 1) % 100 == 0:
            on_progress(i + 1, total)
    if on_progress is not None and total:
        on_progress(total, total)
    return defs


_HANGUL_RE = re.compile(r"[\uac00-\ud7a3\u3131-\u318e]")


def is_garbled_name(name: str) -> bool:
    """判定乱码/未本地化任务名：含韩文残留，或有 2 处以上 '?' 占位符。

    单个 '?' 多为标题党式标点（如「欺骗骗子!?」），不视为乱码。
    """
    return bool(_HANGUL_RE.search(name)) or name.count("?") >= 2


def filter_world_quest_defs(defs: Dict[str, QuestDef], npc_ids: set,
                            mob_ids: set) -> Dict[str, QuestDef]:
    """按世界真实存在性过滤官方任务：给予/交付 NPC 与击杀怪必须出现在地图 life 中。

    ``npc_ids`` / ``mob_ids`` 为字符串集合（来自 core.life_index 的 Map.wz 扫描）。
    收集类目标（end_items）不在此判定 —— 物品可获得性无法由 life 数据推出。
    韩文残留 / ? 占位的乱码名任务一并剔除（此类多为已下线活动任务）。
    """
    out: Dict[str, QuestDef] = {}
    for qid, d in defs.items():
        if is_garbled_name(d.name):
            continue
        if d.start_npc is None or str(d.start_npc) not in npc_ids:
            continue
        if d.end_npc is not None and str(d.end_npc) not in npc_ids:
            continue
        if any(str(mid) not in mob_ids for mid, _ in d.kills):
            continue
        out[qid] = d
    return out


def _parse_one(qid: str, node, act, say, info) -> Optional[QuestDef]:
    s0 = _get(node, "0")
    s1 = _get(node, "1")

    start_items = _list_pairs(_get(s0, "item"))
    prereq = []
    q_req = _get(s0, "quest")
    if q_req is not None:
        for c in q_req.children():
            m = _child_map(c)
            if "id" in m:
                st = _get(m, "state")
                prereq.append((_int(m["id"]), _int(st)))

    kills = _list_pairs(_get(s1, "mob"))
    end_items = _list_pairs(_get(s1, "item"))

    # Act
    a0 = act.get(qid) if act is not None else None
    act0 = _get(a0, "0") if a0 is not None else None
    act1 = _get(a0, "1") if a0 is not None else None
    accept_items = _list_pairs(_get(act0, "item"))
    reward_items = _list_pairs(_get(act1, "item"))
    reward_exp = _int(_get(act1, "exp"))
    reward_money = _int(_get(act1, "money"))
    next_q = _get(act1, "nextQuest")
    next_quest = _int(next_q) if next_q is not None else None

    # Say
    sy = say.get(qid) if say is not None else None
    say0 = _get(sy, "0") if sy is not None else None
    say1 = _get(sy, "1") if sy is not None else None
    accept_lines = _say_lines(say0)
    accept_yes = _say_lines(_get(say0, "yes"))
    accept_no = _say_lines(_get(say0, "no"))
    complete_lines = _say_lines(say1)
    complete_yes = _say_lines(_get(say1, "yes"))
    stop_node = _get(say1, "stop")
    # stop 可能是 {0:{0:...}} 或 {npc:{0:...}} / {item:{0:...}}
    complete_stop = _collect_stop(stop_node)

    # QuestInfo
    inf = info.get(qid) if info is not None else None
    name = _str(_get(inf, "name"))
    if not name:
        name = f"任务 {qid}"
    return QuestDef(
        qid=qid,
        name=name,
        parent=_str(_get(inf, "parent")),
        order=_int(_get(inf, "order")),
        area=_int(_get(inf, "area")),
        start_npc=_int(_get(s0, "npc")) if _get(s0, "npc") is not None else None,
        lvmin=_int(_get(s0, "lvmin")),
        lvmax=_int(_get(s0, "lvmax")),
        jobs=_parse_jobs(_get(s0, "job")),
        start_items=start_items,
        prereq=prereq,
        end_npc=_int(_get(s1, "npc")) if _get(s1, "npc") is not None else None,
        kills=kills,
        end_items=end_items,
        accept_items=accept_items,
        reward_exp=reward_exp,
        reward_money=reward_money,
        reward_items=reward_items,
        next_quest=next_quest,
        accept_lines=accept_lines,
        accept_yes=accept_yes,
        accept_no=accept_no,
        complete_lines=complete_lines,
        complete_yes=complete_yes,
        complete_stop=complete_stop,
        desc0=_str(_get(inf, "0")),
        desc1=_str(_get(inf, "1")),
        desc2=_str(_get(inf, "2")),
    )


def _collect_stop(stop_node) -> List[str]:
    if stop_node is None:
        return []
    lines: List[str] = []
    for key in ("npc", "item", "0"):
        sub = _get(stop_node, key)
        if sub is not None:
            lines.extend(_say_lines(sub))
    if not lines:
        lines = _say_lines(stop_node)
    return lines


@dataclass(frozen=True)
class NpcQuest:
    """某个 NPC 名下的一条可交互任务（供列表/菜单展示）。"""
    qid: str
    title: str
    level: int = 0
    state: str = "offer"      # offer=可接取 / complete=可交付


def collect_npc_quests(defs: Dict[str, QuestDef], log: "QuestLog",
                       npc_id, player) -> List[NpcQuest]:
    """收集该 NPC 的可交付 + 可接取任务，交付排在前（供选择菜单）。

    ``npc_id`` 以字符串比较；不属本 NPC 的任务一律忽略。
    """
    out: List[NpcQuest] = []
    for qid, d in defs.items():
        if d.end_npc is not None and str(d.end_npc) == npc_id \
                and log.is_accepted(qid) and log.can_complete(qid, player):
            out.append(NpcQuest(qid=qid, title=d.name, level=d.lvmin,
                                state="complete"))
        elif d.start_npc is not None and str(d.start_npc) == npc_id \
                and not log.started(qid) and log.can_start(qid, player):
            out.append(NpcQuest(qid=qid, title=d.name, level=d.lvmin,
                                state="offer"))
    out.sort(key=lambda q: 0 if q.state == "complete" else 1)
    return out


# ════════════════════════════════════════════════════════════════════
# 文本标记渲染
# ════════════════════════════════════════════════════════════════════

# 名称标记：\x23 为 ASCII '#'
_NAME_RE = re.compile(r"#([ptmoi])(\d+)#")
# 裸数字标记（如 desc 里残留的 #4000004#）：未带字母前缀，尽力按物品名解析
_BARE_NUM_RE = re.compile(r"#(\d+)#")
# 选项标记：#L0# ... #l（整体去掉）
_CHOICE_RE = re.compile(r"#L\d+#|#l")
# 颜色标记：#b #r #g #d #k 与强调对 #e/#n
_COLOR_RE = re.compile(r"#[brgdken]")


_NAME_COLORS = {"p": "d", "t": "b", "i": "b", "m": "g", "o": "r"}


def render_markup(text: str, assets: Optional[Assets] = None,
                  map_name=None, npc_name=None, item_name=None,
                  mob_name=None, colors: bool = False) -> str:
    """把官方 Say 文本解析成可读文本（替换名称、\\n 转换行、去选项标记）。

    #p<id># → NPC 名 / #t<id># → 物品名 / #m<id># → 地图名 / #o<id># → 怪物名。
    colors=False（默认）：剥掉 #b/#r/#k 等颜色码，输出纯文本（日志、气泡）。
    colors=True：保留手写颜色码，且实体名自动包上 _NAME_COLORS 对应色，
    交由渲染层（core.markup.split_colors）分段着色。
    """
    if not text:
        return ""

    def _sub(m: re.Match) -> str:
        kind, nid = m.group(1), int(m.group(2))
        nm: Optional[str] = None
        if kind == "p" and npc_name is not None:
            nm = npc_name(nid)
        elif kind in ("t", "i") and item_name is not None:
            nm = item_name(nid) or f"#{nid}"
        elif kind == "m" and map_name is not None:
            nm = map_name(nid) or f"#{nid}"
        elif kind == "o" and mob_name is not None:
            nm = mob_name(nid) or f"#{nid}"
        if nm is None:
            return f"#{nid}"
        if colors and kind in _NAME_COLORS:
            return f"#{_NAME_COLORS[kind]}{nm}#k"
        return nm

    def _bare(m: re.Match) -> str:
        nid = int(m.group(1))
        if item_name is not None:
            return item_name(nid) or str(nid)
        return str(nid)

    out = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    out = _CHOICE_RE.sub("", out)
    if not colors:
        out = _COLOR_RE.sub("", out)
    out = _NAME_RE.sub(_sub, out)
    out = _BARE_NUM_RE.sub(_bare, out)
    return out.strip()


_ICON_CODE_RE = re.compile(r"#c(\d+)#")


def split_item_icons(text: str) -> List[Tuple[str, object]]:
    """把文本按 #c<物品id># 内联图标码切成 ("t", str) / ("i", int) 段序列。"""
    text = text or ""
    out: List[Tuple[str, object]] = []
    pos = 0
    for m in _ICON_CODE_RE.finditer(text):
        if m.start() > pos:
            out.append(("t", text[pos:m.start()]))
        out.append(("i", int(m.group(1))))
        pos = m.end()
    if pos < len(text):
        out.append(("t", text[pos:]))
    return out


def wrap_lines(text: str, width_px, font, _wrap) -> List[str]:
    """按可用宽度把多段（\\n 分隔）文本折行。"""
    lines: List[str] = []
    for seg in text.split("\n"):
        lines.extend(_wrap(seg.strip(), width_px, font))
    return lines


# ════════════════════════════════════════════════════════════════════
# 任务状态机
# ════════════════════════════════════════════════════════════════════

class QuestLog:
    """玩家任务状态。由 Player 持有；Game 在 NPC 对话 / 击杀 / 拾取时调用。"""

    def __init__(self, defs: Dict[str, QuestDef]):
        self.defs = defs
        self.status: Dict[str, str] = {}        # qid → Q_ACCEPTED / Q_COMPLETED
        self.kills: Dict[str, Dict[int, int]] = {}   # qid → {mob_id: count}
        # 收集进度：直接读背包 etc 数量，这里仅缓存上限用
        self.accepted_order: List[str] = []     # 记录接取顺序（任务日志用）

    # ── 查询 ────────────────────────────────────────────────────────
    def is_accepted(self, qid: str) -> bool:
        return self.status.get(qid) == Q_ACCEPTED

    def is_completed(self, qid: str) -> bool:
        return self.status.get(qid) == Q_COMPLETED

    def started(self, qid: str) -> bool:
        return qid in self.status

    def quest(self, qid: str) -> Optional[QuestDef]:
        return self.defs.get(qid)

    def can_start(self, qid: str, player) -> bool:
        """接取条件：等级 / 职业 / 前置任务 / 所需物品。"""
        d = self.defs.get(qid)
        if d is None or self.started(qid) or d.start_npc is None:
            return False
        if d.lvmin and player.level < d.lvmin:
            return False
        if d.lvmax and player.level > d.lvmax:
            return False
        if d.jobs and player.job not in d.jobs:
            return False
        for q, state in d.prereq:
            # 前置任务不在启用集内（未开放）→ 视为满足；
            # 否则 state>=2 表示需已完成，state==1 表示需已接取
            if str(q) not in self.defs:
                continue
            if state >= 2 and not self.is_completed(str(q)):
                return False
            if state == 1 and not self.started(str(q)):
                return False
        for item_id, count in d.start_items:
            if self._item_count(player, item_id) < count:
                return False
        return True

    def can_complete(self, qid: str, player) -> bool:
        """完成条件：击杀数量 / 收集数量（end_items）。"""
        d = self.defs.get(qid)
        if d is None or not self.is_accepted(qid):
            return False
        for mid, count in d.kills:
            if self.kills.get(qid, {}).get(mid, 0) < count:
                return False
        for item_id, count in d.end_items:
            if self._item_count(player, item_id) < count:
                return False
        return True

    def kill_progress(self, qid: str, mob_id: int) -> int:
        return self.kills.get(qid, {}).get(mob_id, 0)

    def item_progress(self, player, qid: str, item_id: int) -> int:
        d = self.defs.get(qid)
        if d is None:
            return 0
        return min(self._item_count(player, item_id), d.item_req(item_id))

    @staticmethod
    def _item_count(player, item_id: int) -> int:
        inv = player.inventory
        key = f"{int(item_id):08d}"
        for table in (inv.etcs, inv.consumes):
            item = table.get(key)
            if item is not None:
                return item.count
        return 0

    # ── 动作 ────────────────────────────────────────────────────────
    def force_complete(self, qid: str) -> None:
        """无奖励直接把任务置为已完成（用于转职等 Lua 驱动的特殊流程）。

        与 complete 不同：不检查接受状态/条件、不发任何奖励，仅改状态，
        使该任务不再出现在可接列表与任务日志的进行中区。
        """
        self.status[qid] = Q_COMPLETED

    def accept(self, qid: str, player) -> bool:
        if not self.can_start(qid, player):
            return False
        self.status[qid] = Q_ACCEPTED
        self.kills.setdefault(qid, {})
        self.accepted_order.append(qid)
        # Act/0：接取时赠送物品
        for item_id, count in self.defs[qid].accept_items:
            self._give_item(player, item_id, count)
        return True

    def complete(self, qid: str, player, combat=None, assets=None,
                 audio=None) -> bool:
        """完成任务：套用 Act/1 奖励（exp / meso / 物品；负数收回）。"""
        d = self.defs.get(qid)
        if d is None or not self.can_complete(qid, player):
            return False
        # 收回完成条件物品（end_items 与奖励里的负数可能是同一批，避免重复扣除）
        taken_ids = set()
        for item_id, count in d.end_items:
            self._take_item(player, item_id, count)
            taken_ids.add(item_id)
        # 奖励物品（负数=收回；若已随 end_items 扣过则跳过）
        for item_id, count in d.reward_items:
            if count < 0:
                if item_id in taken_ids:
                    continue
                self._take_item(player, item_id, -count)
            else:
                self._give_item(player, item_id, count)
        self.status[qid] = Q_COMPLETED
        if d.reward_exp and player is not None:
            player.gain_exp(d.reward_exp)
        if d.reward_money and combat is not None:
            combat.meso += d.reward_money
        if audio is not None:
            audio.play("QuestClear", 0.6)
        return True

    # ── 进度钩子 ────────────────────────────────────────────────────
    def abandon(self, qid: str) -> None:
        """放弃进行中任务：状态、接取顺序与击杀进度全清（任务日志用）。"""
        if self.status.get(qid) != Q_ACCEPTED:
            return
        del self.status[qid]
        self.kills.pop(qid, None)
        if qid in self.accepted_order:
            self.accepted_order.remove(qid)

    def on_kill(self, mob_id: int) -> None:
        """击杀怪物：为所有需要该怪的进行中任务计数。"""
        for qid, d in self.defs.items():
            if not self.is_accepted(qid):
                continue
            if d.kill_req(mob_id) > 0:
                rec = self.kills.setdefault(qid, {})
                rec[mob_id] = min(rec.get(mob_id, 0) + 1, d.kill_req(mob_id))

    # ── 内部 ────────────────────────────────────────────────────────
    @staticmethod
    def _give_item(player, item_id: int, count: int) -> None:
        from game.systems.inventory import make_item
        key = f"{int(item_id):08d}"
        player.inventory.add(make_item(key, player.assets, count))

    @staticmethod
    def _take_item(player, item_id: int, count: int) -> None:
        inv = player.inventory
        key = f"{int(item_id):08d}"
        for table in (inv.etcs, inv.consumes):
            item = table.get(key)
            if item is None:
                continue
            item.count -= count
            if item.count <= 0:
                del table[key]
            break

    # ── 序列化 ───────────────────────────────────────────────────
    def to_dict(self) -> dict:
        kills = {qid: {str(mid): cnt for mid, cnt in mobs.items()}
                 for qid, mobs in self.kills.items()}
        return {
            "status": dict(self.status),
            "kills": kills,
            "accepted_order": list(self.accepted_order),
        }

    def from_dict(self, data: dict) -> None:
        self.status = dict(data.get("status", {}))
        self.kills = {qid: {int(mid): cnt for mid, cnt in mobs.items()}
                      for qid, mobs in data.get("kills", {}).items()}
        self.accepted_order = list(data.get("accepted_order", []))
