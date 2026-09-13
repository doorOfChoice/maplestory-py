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


def is_wall_foothold(x1: float, y1: float, x2: float, y2: float) -> bool:
    """该 foothold 是否为墙：纯竖直，或斜率过大的近垂直斜段。

    地图常把立面误写成 1~7px 宽的极陡斜段（斜率可达 4~12），若当坡走会单帧
    垂直瞬移。阈值取 FOOTHOLD_WALL_SLOPE，只吃掉真正的立面，普通台阶（~1.9）不受影响。
    """
    dx = abs(x2 - x1)
    if dx == 0:
        return True
    return abs(y2 - y1) >= settings.FOOTHOLD_WALL_SLOPE * dx


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
    def is_wall(self) -> bool:
        """墙：不可站立、不贴坡，只做水平阻挡。"""
        return is_wall_foothold(self.x1, self.y1, self.x2, self.y2)

    @property
    def is_vertical(self) -> bool:
        """纯竖直（x1==x2）：作者显式写的梯级/墙，可被链接续段穿过。"""
        return self.x1 == self.x2

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
        # 地图边缝缺口：VR bounds 常宽于最外侧可行走 foothold，两者之间的
        # 边缝没有任何地面，走到即坠出世界。把可行走 vr 边界收紧到最外侧
        # 非墙 foothold 边缘、再内缩一个贴图半宽，令身体边缘贴平台边即停
        # （原版此处是墙，且边缝处没有墙体贴图可遮悬出的半身）。
        if self.vr_left is not None:
            horiz = [f for f in self.footholds if not f.is_wall]
            if horiz:
                m = settings.PLAYER_VISUAL_HALF_W
                self.vr_left = max(self.vr_left,
                                   min(f.xmin for f in horiz) + m)
                self.vr_right = min(self.vr_right,
                                    max(f.xmax for f in horiz) - m)
        # 竖直墙（纯竖直 + 近垂直斜段）：不可站立/落点，只用于水平阻挡。
        # 按 (layer, 代表 x) 分组合并成墙链，每层各自按 x 排序供二分查询。
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
        groups: Dict[Tuple[int, float], List[Tuple[float, float]]] = {}
        for f in self.footholds:
            if f.is_wall:
                # 近垂直斜段取其宽度中点作代表 x（纯竖直时两边相同）
                wx = (f.x1 + f.x2) / 2.0
                groups.setdefault((f.layer, wx), []).append((f.ymin, f.ymax))
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
                          ignore_layers=None, prev_x: Optional[float] = None,
                          band: bool = True) -> Optional[Foothold]:
        """下落时本帧穿过(或刚好到达)的最近支撑面。

        ignore_layers: 下跳期间要忽略的平台 layer 集合。
        prev_x / band: 水平大位移（如受击击退）上坡方向受击时，坡面随 x
        抬升快过垂直下落，当前 x 的垂直穿线带会一直错过线（等 vy>=0 时脚已
        深陷坡体）。故当带 prev_x 时补一条"沿迹穿越"判定：面相对脚追上来
        （脚从面上方穿到下方）→ 判穿过；从下方上升掠过（脚上升快过面，如跳跃
        截断）不接。band=False 时只用沿迹判定、跳过垂直带（上升帧专用）。
        """
        ignore = ignore_layers or set()
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        lo, hi = (prev_feet - 1.0, now_feet + 1.0)
        for f in self.footholds:
            if f.is_wall or f.layer in ignore or not f.covers(x):
                continue
            y_a = f.y_at(x)
            hit = band and lo <= y_a <= hi
            if not hit and prev_x is not None and prev_x != x:
                xp = min(max(prev_x, f.xmin), f.xmax)
                y_prev = f.y_at(xp)
                # 沿迹穿越只在「面相对脚追上来 / 脚从面上方穿到下方」时成立；
                # 从下方上升掠过（脚上升快过面）不得被吸附，否则跳跃会被截断。
                hit = (prev_feet <= y_prev + 1.0
                       and now_feet >= y_a - 1.0
                       and now_feet - y_a >= prev_feet - y_prev)
            if hit and (best is None or y_a < best_y):
                best, best_y = f, y_a
        return best

    def grounded_surface(self, x: float, feet: float) -> Optional[Foothold]:
        """站立时脚下（±容差内）最近的支撑面。用于贴坡 / 跨平台衔接。"""
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        for f in self.footholds:
            if f.is_wall or not f.covers(x):
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
            if f.is_wall or not f.covers(x):
                continue
            d = abs(f.y_at(x) - feet)
            if d <= lim and (best is None or d < best_d):
                best, best_d = f, d
        return best

    def teleport_vertical_surface(self, x: float, feet: float,
                                  distance: float,
                                  up: bool = True) -> Optional[Foothold]:
        """瞬移垂直落点：距脚底 distance 内、最贴近脚底的水平面。

        up=True 取脚底上方最近（y 最大），否则取下方最近（y 最小）。层不参与
        筛选——链可以在 layer 间穿行，同高的前后景平台也是可行走地面（与
        grounded_surface 的层无关语义一致）。range 内没有平台则返回 None，
        调用方原地不动，避免穿墙或掉出世界。"""
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        for f in self.footholds:
            if f.is_wall or not f.covers(x):
                continue
            y_a = f.y_at(x)
            if up:
                if not (feet - distance <= y_a <= feet - 1.0):
                    continue
                closer = best_y is None or y_a > best_y
            else:
                if not (feet + 1.0 <= y_a <= feet + distance):
                    continue
                closer = best_y is None or y_a < best_y
            if closer:
                best, best_y = f, y_a
        return best

    def nearest_surface_in_range(self, x: float, feet: float,
                                 distance: float) -> Optional[Foothold]:
        """瞬移落点兜底：x 处距脚底 distance 内、上/下最近的平台（不含同高脚底）。

        水平瞬移终点没有同高/链接平台时用它找可落面——更高或更低的平台都算，
        取垂直距离最近的一侧，保证瞬移必定以站在平台上结束。"""
        below = self.teleport_vertical_surface(x, feet, distance, up=False)
        above = self.teleport_vertical_surface(x, feet, distance, up=True)
        if below is None:
            return above
        if above is None:
            return below
        below_d = below.y_at(x) - feet
        above_d = feet - above.y_at(x)
        return below if below_d <= above_d else above

    def top_landing(self, x: float, feet: float,
                    max_rise: float = 34.0) -> Optional[Foothold]:
        """绳/梯顶端出绳：找 x 处位于脚底上方 max_rise 内（或平齐）的支撑面，
        取其中最贴近脚底的一条。"""
        best: Optional[Foothold] = None
        best_y: Optional[float] = None
        for f in self.footholds:
            if f.is_wall or not f.covers(x):
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
            if f.is_wall or not f.covers(x):
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
            if not nxt.is_wall:
                return nxt
            if not nxt.is_vertical:
                return None          # 近垂直斜段=墙：链接中断（拦住/走空）
            # 纯竖直梯级：从 came_from 那端进入，从另一端穿出
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
        2) 已越过端点 → 沿链接续段前进到首个覆盖 x 的段、且高差在一级
           台阶内 → 该段（中间可跳过比一帧步长还窄的短段；方向 0 时两端
           链接都可作为落点，避免原地/垂直降落悬空）；
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
            edge_x = cur.xmax if d > 0 else cur.xmin
            cont = self.linked_continuation(cur, d > 0)
            # 中间续段可能比一帧步长还窄（落点整个跳过它），沿链接继续
            # 前进到首个真正覆盖 x 的段再判高差；否则原地返回 None 会
            # 误判坠落（真实案例：101010000 底部 4px 窄桥）。
            for _ in range(8):
                if cont is None or cont.layer in ignore:
                    break
                if cont.covers(x):
                    dy = cont.y_at(x) - cur.y_at(edge_x)
                    if abs(dy) <= settings.PLAYER_STEP_UP:
                        return cont
                    break  # 高落差不自动走下/上：交给重力+落地检测
                cont = self.linked_continuation(cont, d > 0)
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

    def wall_overlap_clamp(self, x: float, feet: float, direction: int,
                           layer: Optional[int] = None) -> float:
        """把已嵌入阻挡墙的身体沿来向推到墙外（瞬移落点兜底）。

        步进中的 wall_block 允许链接台阶豁免（爬楼梯），个别地图里与链续段
        同高的实体墙会被误豁免而穿进去。此处在落点按「来向」把身体推回近侧
        墙面外：右行取最左的重叠墙左面，左行取最右的右面。"""
        chains, _ = self._layer_chains(layer)
        r = settings.PLAYER_BODY_HALF_W
        hit: Optional[float] = None
        for w in chains:
            if not self._blocks(w, feet):
                continue
            if not (w.x - r < x < w.x + r):
                continue
            cand = w.x - r if direction >= 0 else w.x + r
            if hit is None:
                hit = cand
            elif direction >= 0:
                hit = min(hit, cand)
            else:
                hit = max(hit, cand)
        return self._vr_clamp(x if hit is None else hit)

    def deembed_walls(self, x: float, feet: float,
                      layer: Optional[int] = None) -> float:
        """把已嵌进阻挡墙的身体推到最近一侧墙外（竖直瞬移落点兜底）。

        与 wall_overlap_clamp 的「按来向推回近侧」不同：竖直/无方向的落点没有
        来向，故按身体中心相对墙面的位置取更近的一侧推出（x 在墙左侧推左、
        右侧推右），多面墙迭代到不再重叠。"""
        chains, _ = self._layer_chains(layer)
        r = settings.PLAYER_BODY_HALF_W
        for _ in range(4):
            moved = False
            for w in chains:
                if not self._blocks(w, feet):
                    continue
                if not (w.x - r < x < w.x + r):
                    continue
                x = w.x - r if x <= w.x else w.x + r
                moved = True
            if not moved:
                break
        return self._vr_clamp(x)

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
