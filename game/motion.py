"""运动辅助：速度渐近（approach）与跳跃缓冲 / 土狼时间（JumpFeather）。

纯状态、不依赖任何资源，便于针对公开接口写单元测试：
  · approach：把当前值朝目标值移动最多 max_delta，用于水平速度缓动。
  · JumpFeather：记录「已按下跳跃」与「离开地面」两个窗口，
    can_jump 只在 缓冲内 +（在地面 或 离开地面尚在土狼窗口内） 时为真。
"""

from __future__ import annotations


def approach(value: float, target: float, max_delta: float) -> float:
    """把 value 朝 target 移动，每步最多移动 max_delta。

    不是直接跳到 target，而是渐近逼近——这是「丝滑」的来源：
    起落都有缓动，不会瞬间从 0 跳到全速或从全速骤停。
    """
    if value < target:
        return min(value + max_delta, target)
    if value > target:
        return max(value - max_delta, target)
    return target


class JumpFeather:
    """跳跃手感：按压缓冲（press 后短暂内存） + 土狼时间（离地后仍可跳）。

    buffer ：按跳跃键后保留的可起跳窗口（秒），允许在落地前一瞬按跳。
    coyote ：离开地面后仍可起跳的窗口（秒），允许刚走出平台边缘再按跳。
    """

    __slots__ = ("buffer_time", "coyote_time", "buffer", "coyote")

    def __init__(self, buffer_time: float = 0.12, coyote_time: float = 0.08):
        self.buffer_time = buffer_time
        self.coyote_time = coyote_time
        self.buffer = 0.0
        self.coyote = 0.0

    def press(self) -> None:
        """按下跳跃：立即进入按压缓冲窗口。"""
        self.buffer = self.buffer_time

    def tick(self, dt: float, on_ground: bool) -> None:
        """每帧推进：在地面刷新土狼窗口，否则两者随时间衰减。"""
        if on_ground:
            self.coyote = self.coyote_time
        else:
            self.coyote = max(0.0, self.coyote - dt)
        self.buffer = max(0.0, self.buffer - dt)

    @property
    def buffered(self) -> bool:
        """本次按键是否仍在缓冲窗口内（供每帧重试起跳）。"""
        return self.buffer > 0.0

    def can_jump(self, on_ground: bool) -> bool:
        """缓冲内 且（在地面 或 仍在土狼窗口）→ 可以起跳。"""
        return self.buffer > 0.0 and (on_ground or self.coyote > 0.0)

    def consume(self) -> None:
        """成功起跳后清空缓冲与土狼窗口，避免重复起跳。"""
        self.buffer = 0.0
        self.coyote = 0.0
