"""foothold 线段碰撞 + 重力 + 跳跃 + 爬梯。

MapleStory 的可行走面是一组带 prev/next 链接的线段（foothold）。
本模块实现最贴近原版行为的简化版：
  · 下落时只在与某条线段"本帧穿过"的情况下着陆（= 原版单向平台：可上跳穿越、落下时停在顶部）
  · 站在平台上时跟随坡度（每次更新都找脚下最近的支撑面）
  · 下跳（↓+跳）在一段时间内忽略当前平台的 layer
  · 梯子（ladderRope.l=True）：靠近时按 ↑/↓ 爬升/下降
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import settings


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


class Physics:
    def __init__(self, foothold_data: List[Dict[str, int]],
                 rope_data: List[Dict[str, Any]]):
        self.footholds: List[Foothold] = [Foothold(d) for d in foothold_data]
        self.by_id: Dict[int, Foothold] = {f.fid: f for f in self.footholds}
        self.ropes = rope_data
        # 竖直墙（x1==x2）：不可站立/落点，只用于水平阻挡
        self.walls: List[Foothold] = [f for f in self.footholds
                                      if f.x1 == f.x2]

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

    # ── 水平阻挡（竖直墙）──────────────────────────────────────────
    def wall_block(self, old_x: float, new_x: float, feet_y: float) -> float:
        """本帧水平移动撞到竖直墙时，把 x 钳在墙面外。

        竖直墙是地形侧壁（ymin=上沿，ymax=下沿），默认一律阻挡——不许穿透：
          · 墙外任何深度都没有落脚点（地图边界墙）→ 任何高度都挡，防出图
          · 墙脚以下（墙在身体上方，从墙下走过）→ 放行
          · 两侧有同层地面（走道从地形前方/中间穿过）→ 放行
          · 开放边缘：墙链底没有延伸到落点平台之下（开放台阶/浮空岛草沿）
            → 放行走出边缘坠落 / 跳跃越过
          · 其余（实心崖壁：墙链延伸到落点平台之下）→ 挡住，不许穿透
        """
        r = settings.PLAYER_BODY_HALF_W
        for w in self.walls:
            moving_right = new_x > old_x
            if moving_right:
                crossed = old_x <= w.x1 and new_x > w.x1 - r
            else:
                crossed = old_x >= w.x1 and new_x < w.x1 + r
            if not crossed:
                continue
            clamped = w.x1 - r if moving_right else w.x1 + r
            # 边界墙：墙外任何高度都没有落脚点
            if not self._support_beyond(w.x1, moving_right, feet_y):
                return clamped
            # 墙顶上方（跳跃越过边缘；该墙属于更低的层）：放行
            if feet_y < w.ymin - 6.0:
                continue
            # 墙脚以下：墙在身体上方
            if feet_y > w.ymax + 2.0:
                continue
            # 同层地面贯穿墙的两侧
            if self._surface_spans(w.x1, moving_right, feet_y):
                continue
            # 开放台阶：走出坠落 / 跳跃越过都放行
            if self._is_open_step(w, moving_right, feet_y):
                continue
            # 实心崖面：挡住
            return clamped
        return new_x

    def _chain_bottom(self, wall) -> float:
        """从该墙段向下收集同 x 相邻的墙段，返回链底 y。"""
        bottom = wall.ymax
        cur = wall
        while True:
            nxt = next((o for o in self.walls
                        if o is not cur and abs(o.x1 - cur.x1) < 1.0
                        and abs(o.ymin - bottom) < 2.0), None)
            if nxt is None:
                return bottom
            cur = nxt
            bottom = cur.ymax

    def _is_open_step(self, wall, moving_right: bool, feet_y: float) -> bool:
        """开放边缘：墙链底没有延伸到落点平台之下（落点周围无岩体）。

        · 台阶：墙链底 == 下一级平台面（如 305→365）→ 走出坠落
        · 浮空岛草沿：墙只是平台边缘的一小段唇沿，下方是开阔空气
          （如浮空岛 245→455 水面路面）→ 走出坠落
        · 实心崖壁：墙链延伸到落点平台之下（如 365→455 但墙到 510）
          → 不是开放边缘，调用方应阻挡
        """
        drop = self._walk_off_drop(wall.x1, moving_right, feet_y)
        if drop == float("inf"):
            return False
        return self._chain_bottom(wall) <= feet_y + drop + 8.0

    def _support_beyond(self, wall_x: float, moving_right: bool,
                        feet_y: float) -> bool:
        """墙外侧紧邻处、脚底同高或更低是否存在落脚点（识别地图边界墙）。"""
        px = wall_x + (2.0 if moving_right else -2.0)
        for f in self.footholds:
            if f.x1 == f.x2 or not f.covers(px):
                continue
            if f.y_at(px) >= feet_y - 12.0:
                return True
        return False

    def _walk_off_drop(self, wall_x: float, moving_right: bool,
                       feet_y: float, ahead: float = 50.0) -> float:
        """墙外侧 ahead 范围内、低于脚底的最近支撑面落差；没有则返回 inf。"""
        best = float("inf")
        px = wall_x + (2.0 if moving_right else -2.0)
        for f in self.footholds:
            if f.x1 == f.x2:
                continue
            if moving_right:
                if f.xmax < wall_x or f.xmin > wall_x + ahead:
                    continue
            else:
                if f.xmin > wall_x or f.xmax < wall_x - ahead:
                    continue
            y = f.y_at(min(max(px, f.xmin), f.xmax))
            if y > feet_y + 2.0 and y - feet_y < best:
                best = y - feet_y
        return best

    def _surface_spans(self, wall_x: float, moving_right: bool,
                       feet_y: float) -> bool:
        """墙两侧、脚底同层（±容差）是否都有支撑面。

        地面常由多段 foothold 拼接，不能要求单条线段跨过墙的 x，
        只需两侧各自存在同层支撑（走道从地形前方/中间穿过）。
        """
        back = wall_x - 14.0 if moving_right else wall_x + 14.0
        ahead = wall_x + 4.0 if moving_right else wall_x - 4.0
        return self._ground_at(back, feet_y) and self._ground_at(ahead, feet_y)

    def _ground_at(self, x: float, feet_y: float, tol: float = 12.0) -> bool:
        """x 处脚底同层（±tol）是否存在支撑面。"""
        for f in self.footholds:
            if f.x1 == f.x2 or not f.covers(x):
                continue
            if abs(f.y_at(x) - feet_y) <= tol:
                return True
        return False

    # ── 梯子 / 绳索 ───────────────────────────────────────────────
    def rope_at(self, x: float, y: float) -> Optional[Dict[str, Any]]:
        """靠近任意绳/梯（含细绳 l=0）时返回其数据，可按 ↑/↓ 攀爬。"""
        best: Optional[Dict[str, Any]] = None
        best_dx: float = 20.0
        for r in self.ropes:
            rx = float(r["x"])
            # 细绳的攀爬线略偏图像左缘右侧
            cx = rx + (6.0 if not r.get("ladder") else 0.0)
            dx = abs(cx - x)
            if dx < best_dx and float(r["y1"]) - 12.0 <= y <= float(r["y2"]) + 12.0:
                best, best_dx = r, dx
        return best

    # 兼容旧调用名
    def ladder_at(self, x: float, y: float) -> Optional[Dict[str, Any]]:
        return self.rope_at(x, y)
