"""foothold 线段碰撞 + 重力 + 跳跃 + 爬梯。

MapleStory 的可行走面是一组带 prev/next 链接的线段（foothold）。
本模块实现最贴近原版行为的简化版：
  · 下落时只在与某条线段"本帧穿过"的情况下着陆（= 原版单向平台：可上跳穿越、落下时停在顶部）
  · 站在平台上时跟随坡度（每次更新都找脚下最近的支撑面）
  · 下跳（↓+跳）在一段时间内忽略当前平台的 layer
  · 梯子（ladderRope.l=True）：靠近时按 ↑/↓ 爬升/下降
  · 竖直墙：初始化时把同 x 相连的竖直 foothold 合并成墙链（区间），
    x 有序索引，阻挡判定只在被穿过的墙链上跑（O(log n)）

墙判定 = 原版规则（纯脚底相对，不做语义猜测、不用身体盒）：
  · 墙顶不高于脚底（ytop >= feet - EPS）：平台边缘 stub，可走出坠落
  · 墙底在脚底上方（ybottom < feet - EPS）：上层平台悬挂边缘，横向穿过
  · 其余（底扎在脚平面、顶高出脚）：落地实墙/台阶立面，挡住
行走续命只认 foothold prev/next 链接（linked_continuation / walk_surface）：
前景坡、悬垂平台等无链接的邻近面不参与贴坡，从根上消除"最近面吸附"闪烁。
"""

from __future__ import annotations

import bisect
from typing import Any, Dict, List, Optional, Tuple

from game import settings


class Foothold:
    """一条可行走线段。y_at(x) 做线性插值（竖直线段返回最小值）。"""

    __slots__ = ("fid", "layer", "platform", "x1", "y1", "x2", "y2", "prev", "next")

    def __init__(self, data: Dict[str, int]):
        self.fid = int(data["id"])
        self.layer = int(data["layer"])
        self.platform = int(data["platform"])
        self.x1 = int(data["x1"])
        self.y1 = int(data["y1"])
        self.x2 = int(data["x2"])
        self.y2 = int(data["y2"])
        self.prev = int(data.get("prev") or -1)
        self.next = int(data.get("next") or -1)

    @property
    def xmin(self) -> float:
        return float(min(self.x1, self.x2))

    @property
    def xmax(self) -> float:
        return float(max(self.x1, self.x2))

    def covers(self, x: float) -> bool:
        return self.xmin - 1.0 <= x <= self.xmax + 1.0

    def y_at(self, x: float) -> float:
        dx = self.x2 - self.x1
        if dx == 0:
            return float(min(self.y1, self.y2))
        return self.y1 + (self.y2 - self.y1) * (x - self.x1) / dx

    @property
    def ymin(self) -> float:
        return float(min(self.y1, self.y2))

    @property
    def ymax(self) -> float:
        return float(max(self.y1, self.y2))


class WallChain:
    """同一 (layer, x) 处相连（间隙 ≤2px）竖直 foothold 合并成的一整面墙。

    layer 是关键：MapleStory 每一层是独立平面，玩家只与所站 layer 的墙
    发生横向碰撞；其它 layer 的竖直边只是前后景深，永不阻挡。
    """

    __slots__ = ("layer", "x", "ytop", "ybottom")

    def __init__(self, layer: int, x: float, ytop: float, ybottom: float):
        self.layer = layer
        self.x = x
        self.ytop = ytop
        self.ybottom = ybottom


class Physics:
    def __init__(self, foothold_data: List[Dict[str, int]],
                 rope_data: List[Dict[str, Any]],
                 bounds: Optional[Dict[str, int]] = None):
        self.footholds: List[Foothold] = [Foothold(d) for d in foothold_data]
        self.by_id: Dict[int, Foothold] = {f.fid: f for f in self.footholds}
        self.ropes = rope_data
        # VR 边界硬钳制（出图兜底），不再让"墙外无地面"兼职边界判定
        r = settings.PLAYER_BODY_HALF_W
        if bounds is not None:
            self.vr_left: Optional[float] = float(bounds["left"]) + r
            self.vr_right: Optional[float] = float(bounds["right"]) - r
        else:
            self.vr_left = self.vr_right = None
        # 竖直墙（x1==x2）：不可站立/落点，只用于水平阻挡。
        # 按 (layer, x) 分组合并成墙链，每层各自按 x 排序供二分查询。
        self.chains: List[WallChain] = self._build_chains()
        self.chains_by_layer: Dict[int, List[WallChain]] = {}
        for w in self.chains:
            self.chains_by_layer.setdefault(w.layer, []).append(w)
        self.wall_xs_by_layer: Dict[int, List[float]] = {
            lay: [w.x for w in ws] for lay, ws in self.chains_by_layer.items()
        }
        # 未指定所属层的查询（外部工具/测试）退回全层链，逐层各自不合并
        self.chains.sort(key=lambda w: w.x)
        self.wall_xs: List[float] = [w.x for w in self.chains]

    def _layer_chains(self, layer: Optional[int]
                      ) -> Tuple[List[WallChain], List[float]]:
        if layer is not None and layer in self.chains_by_layer:
            return self.chains_by_layer[layer], self.wall_xs_by_layer[layer]
        if layer is not None:
            return [], []          # 该层没有墙
        return self.chains, self.wall_xs

    def _build_chains(self) -> List[WallChain]:
        groups: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
        for f in self.footholds:
            if f.x1 == f.x2:
                groups.setdefault((f.layer, f.x1), []).append((f.ymin, f.ymax))
        chains: List[WallChain] = []
        for (layer, x), spans in groups.items():
            spans.sort()
            top, bottom = spans[0]
            for a, b in spans[1:]:
                if a <= bottom + 2.0:
                    bottom = max(bottom, b)
                else:
                    chains.append(WallChain(layer, float(x), top, bottom))
                    top, bottom = a, b
            chains.append(WallChain(layer, float(x), top, bottom))
        chains.sort(key=lambda w: (w.layer, w.x))
        return chains

    # ── 支撑面查询 ────────────────────────────────────────────────
    def landing_candidate(self, x: float, prev_feet: float, now_feet: float,
                          ignore_layers=None) -> Optional[Foothold]:
        """下落时本帧穿过(或刚好到达)的最近支撑面。

        ignore_layers: 下跳期间要忽略的平台 layer 集合。
        """
        ignore = ignore_layers or set()
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        lo, hi = (prev_feet - 1.0, now_feet + 1.0)
        for f in self.footholds:
            if f.x1 == f.x2 or f.layer in ignore or not f.covers(x):
                continue
            y_a = f.y_at(x)
            if lo <= y_a <= hi:
                if best is None or y_a < best_y:
                    best, best_y = f, y_a
        return best

    def grounded_surface(self, x: float, feet: float) -> Optional[Foothold]:
        """站立时脚下（±容差内）最近的支撑面。用于贴坡 / 跨平台衔接。"""
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        for f in self.footholds:
            if f.x1 == f.x2 or not f.covers(x):
                continue
            y_a = f.y_at(x)
            d = y_a - feet
            if -2.5 <= d <= 9.0:
                if best is None or y_a < best_y:
                    best, best_y = f, y_a
        return best

    def spawn_surface(self, x: float, feet: float,
                      tol: Optional[float] = None) -> Optional[Foothold]:
        """出生点贴地：portal 标注的 y 常落在地面线上下数 px（WZ 作者摆位），
        首帧没有下落穿线信息，故在容差内对覆盖 x 的面做双向最近吸附。
        只在出生/传送落位使用，不参与常规行走/下落（保持单向平台语义）。"""
        lim = settings.SPAWN_SNAP_TOL if tol is None else tol
        best: Optional[Foothold] = None
        best_d: Optional[float] = None
        for f in self.footholds:
            if f.x1 == f.x2 or not f.covers(x):
                continue
            d = abs(f.y_at(x) - feet)
            if d <= lim and (best is None or d < best_d):
                best, best_d = f, d
        return best

    def top_landing(self, x: float, feet: float,
                    max_rise: float = 34.0) -> Optional[Foothold]:
        """绳/梯顶端出绳：找 x 处位于脚底上方 max_rise 内（或平齐）的支撑面，
        取其中最贴近脚底的一条。"""
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        for f in self.footholds:
            if f.x1 == f.x2 or not f.covers(x):
                continue
            y_a = f.y_at(x)
            if feet - max_rise <= y_a <= feet + 2.0:
                if best is None or y_a > best_y:
                    best, best_y = f, y_a
        return best

    def surface_under(self, x: float, y: float,
                      tol: float = 25.0) -> Optional[Foothold]:
        """找 x 处 y 附近最接近的支撑面（用于怪物落地/巡逻范围钳制）。"""
        best: Optional[Foothold] = None
        best_d = tol
        for f in self.footholds:
            if f.x1 == f.x2 or not f.covers(x):
                continue
            d = abs(f.y_at(x) - y)
            if d <= best_d:
                best, best_d = f, d
        return best

    # ── 链接续段（行走拓扑）────────────────────────────────────────
    def linked_continuation(self, f: Foothold,
                            moving_right: bool) -> Optional[Foothold]:
        """从 f 的行进方向端点沿 prev/next 链接（可穿过连续竖直段，
        即"墙链=梯级侧影"）走到首个水平续段。没有链接则 None。

        链接是作者写下的通行说明书：相连 = 允许步过/走落；
        不相连的邻近面（如前景坡道横跨路面）与此查询完全无关。
        """
        d = f.next if moving_right else f.prev
        came_from = f.fid
        for _ in range(8):
            if not d or d < 0:
                return None
            nxt = self.by_id.get(d)
            if nxt is None or nxt.fid == came_from:
                return None
            if nxt.x1 != nxt.x2:
                return nxt
            # 竖直段：从 came_from 那端进入，从另一端穿出
            if nxt.prev == came_from:
                came_from, d = nxt.fid, nxt.next
            elif nxt.next == came_from:
                came_from, d = nxt.fid, nxt.prev
            else:
                return None
        return None

    def walk_surface(self, cur: Optional[Foothold], x: float,
                     direction: int,
                     ignore_layers=None) -> Optional[Foothold]:
        """行走帧的"脚下是谁"：只认当前链，不做最近面吸附。

        1) cur 仍覆盖 x → 就是它（坡面 y_at 插值自然抬/降脚）；
        2) 已越过端点 → 仅当存在链接续段、且高差在一级台阶内 → 续段
           （方向 0 时两端链接都可作为落点，避免原地/垂直降落悬空）；
        3) 其余（开放边缘 / 无链接的高差 / 被下跳忽略的层）→ None=坠落。
        """
        if cur is None:
            return None
        ignore = ignore_layers or set()
        if cur.layer in ignore:
            return None
        if cur.covers(x):
            return cur
        dirs = [direction] if direction else [1, -1]
        for d in dirs:
            cont = self.linked_continuation(cur, d > 0)
            if cont is None or cont.layer in ignore or not cont.covers(x):
                continue
            edge_x = cur.xmax if d > 0 else cur.xmin
            dy = cont.y_at(x) - cur.y_at(edge_x)
            if abs(dy) > settings.PLAYER_STEP_UP:
                continue  # 高落差不自动走下/上：交给重力+落地检测
            return cont
        return None

    # ── 水平阻挡（竖直墙）──────────────────────────────────────────
    def wall_block(self, old_x: float, new_x: float,
                   prev_feet: float, now_feet: float,
                   cur_fh: Optional[Foothold] = None,
                   layer: Optional[int] = None) -> float:
        """本帧水平移动撞到竖直墙时，把 x 钳在墙面外。

        只查询"玩家所在 layer"的墙链（二分定位）——别的层是前后景，
        永不横向阻挡。判定用的是"x 到达墙面那一刻"插值出的脚底高度，
        高速下落贴墙也不漏判。同帧穿过多个阻挡墙时取最先碰到的那面。

        cur_fh（当前所站 foothold）传入时，"链接续段在一级台阶内"的
        梯级 riser 被豁免：放行，由 walk_surface 把脚底抬上去。
        layer 缺省取 cur_fh.layer；两者皆无（外部查询）→ 退回全层链。
        """
        if layer is None and cur_fh is not None:
            layer = cur_fh.layer
        chains, xs = self._layer_chains(layer)
        if not chains:
            return self._vr_clamp(new_x)
        r = settings.PLAYER_BODY_HALF_W
        if new_x > old_x:
            lo = bisect.bisect_left(xs, old_x - 1.0)
            hi = bisect.bisect_right(xs, new_x + r + 1.0)
            hit: Optional[WallChain] = None
            for w in chains[lo:hi]:
                if not (old_x <= w.x and new_x > w.x - r):
                    continue
                feet = self._feet_at_cross(old_x, new_x, prev_feet, now_feet,
                                           w.x - r)
                if not self._blocks(w, feet) or \
                        self._step_exempt(cur_fh, w, feet, True):
                    continue
                if hit is None or w.x < hit.x:
                    hit = w
            return self._vr_clamp(hit.x - r if hit is not None else new_x)
        if new_x < old_x:
            lo = bisect.bisect_left(xs, new_x - r - 1.0)
            hi = bisect.bisect_right(xs, old_x + 1.0)
            hit = None
            for w in chains[lo:hi]:
                if not (old_x >= w.x and new_x < w.x + r):
                    continue
                feet = self._feet_at_cross(old_x, new_x, prev_feet, now_feet,
                                           w.x + r)
                if not self._blocks(w, feet) or \
                        self._step_exempt(cur_fh, w, feet, False):
                    continue
                if hit is None or w.x > hit.x:
                    hit = w
            return self._vr_clamp(hit.x + r if hit is not None else new_x)
        return self._vr_clamp(new_x)

    def _step_exempt(self, cur: Optional[Foothold], w: WallChain,
                     feet: float, moving_right: bool) -> bool:
        """被挡的墙链恰是当前段的链接梯级 riser、续段高差在一步内 → 放行。"""
        if cur is None:
            return False
        cont = self.linked_continuation(cur, moving_right)
        if cont is None:
            return False
        edge_x = cur.xmax if moving_right else cur.xmin
        if abs(w.x - edge_x) > 2.0:
            return False
        rise = feet - cont.y_at(w.x + (settings.PLAYER_BODY_HALF_W
                                       if moving_right
                                       else -settings.PLAYER_BODY_HALF_W))
        return 0.0 <= rise <= settings.PLAYER_STEP_UP

    def _vr_clamp(self, x: float) -> float:
        if self.vr_left is None:
            return x
        return min(max(x, self.vr_left), self.vr_right)

    def touching_wall(self, x: float, feet_y: float, direction: int,
                      layer: Optional[int] = None) -> Optional[float]:
        """身体半宽前沿是否抵着一面会阻挡的墙（贴墙下滑/蹬墙跳判用）。

        同样只在玩家所属 layer 的墙链里找。返回墙面 x；没有则 None。
        """
        chains, xs = self._layer_chains(layer)
        if not chains:
            return None
        r = settings.PLAYER_BODY_HALF_W
        px = x + direction * r
        lo = bisect.bisect_left(xs, px - 3.0)
        hi = bisect.bisect_right(xs, px + 3.0)
        for w in chains[lo:hi]:
            if self._blocks(w, feet_y):
                return w.x
        return None

    @staticmethod
    def _feet_at_cross(old_x: float, new_x: float, prev_feet: float,
                       now_feet: float, edge: float) -> float:
        """脚底高度按"x 位移到墙面边缘那一刻"在帧间线性插值。"""
        if new_x == old_x:
            return now_feet
        t = (edge - old_x) / (new_x - old_x)
        t = min(1.0, max(0.0, t))
        return prev_feet + (now_feet - prev_feet) * t

    def _blocks(self, w: WallChain, feet_y: float) -> bool:
        """墙链在给定脚底高度上是否阻挡水平移动（纯脚底相对，无身体盒）。

        只挡"扎在你所站地面层"的实体墙，一条高度判据即可：
          · 墙顶 >= 脚底-EPS → 顶面不高于脚：这是你正站着的平台边缘 stub，
            可走出坠落（ytop≈feet 或整面墙在脚下）。
          · 墙底 < 脚底-EPS → 整面墙悬挂在脚上方：上层平台的边缘 riser，
            MS 无下蹲、上层地面永远可从下方横向穿过，放行。
          · 其余（顶高于脚 且 底落在脚平面或以下）→ 落地实墙 / 台阶立面，挡。
        """
        eps = settings.WALL_FEET_EPS
        if w.ytop >= feet_y - eps:
            return False
        if w.ybottom < feet_y - eps:
            return False
        return True

    # ── 梯子 / 绳索 ───────────────────────────────────────────────
    @staticmethod
    def rope_center_x(r: Dict[str, Any]) -> float:
        """绳/梯的攀爬中心线 x（细绳的线略偏图像左缘右侧）。"""
        return float(r["x"]) + (0.0 if r.get("ladder") else 6.0)

    def rope_at(self, x: float, y: float) -> Optional[Dict[str, Any]]:
        """靠近任意绳/梯（含细绳 l=0）时返回其数据，可按 ↑/↓ 攀爬。

        y 为角色 navel。检测范围在绳端基础上外扩 FEET_OFFSET + CLIMB_TOP_OVERSHOOT：
        站在绳底/绳顶地面时（脚底在端点上，navel 距绳端约一个 FEET_OFFSET），
        navel 也能命中绳身，顶端平台可略高于绳顶也覆盖到。
        """
        best: Optional[Dict[str, Any]] = None
        best_dx: float = 20.0
        reach = settings.FEET_OFFSET + settings.CLIMB_TOP_OVERSHOOT
        for r in self.ropes:
            cx = self.rope_center_x(r)
            dx = abs(cx - x)
            if (dx < best_dx
                    and float(r["y1"]) - reach <= y <= float(r["y2"]) + reach):
                best, best_dx = r, dx
        return best

    # 兼容旧调用名
    def ladder_at(self, x: float, y: float) -> Optional[Dict[str, Any]]:
        return self.rope_at(x, y)
