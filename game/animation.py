"""共用動畫引擎：單幀累積型（Animation）與無狀態選幀（frame_at）。

Animation 支援兩種幀格式：
  - 二元組 ``(Surface, delay_ms)``
  - 三元組 ``(Surface, origin, delay_ms)``
delay 永遠是 tuple 的最後一個元素（``f[-1]``）。
"""

from __future__ import annotations

from typing import List, Tuple, Union

_Frame = Union[Tuple, List]

# 支援的幀格式：最後一個元素永遠是 delay_ms
#   (Surface, delay_ms)
#   (Surface, origin, delay_ms)


class Animation:
    """狀態機型動畫：保有 frame + accum 狀態，每幀呼叫 advance(dt) 推進。

    loop=True   → 永遠循環播放，advance 回傳 True 表示繞回首幀
    loop=False  → 播完後 done=True，advance 回傳 True 表示已播完
    """

    def __init__(self, frames: List[_Frame], loop: bool = True):
        self.frames = list(frames)
        self.loop = loop
        self.frame = 0
        self.accum = 0.0
        self.done = not self.frames

    @property
    def delay(self) -> int:
        """當前幀的 delay（毫秒）。"""
        return self.frames[self.frame][-1]

    @property
    def surface(self):
        """當前幀 Surface；無幀時回傳 None。"""
        return self.frames[self.frame][0] if self.frames else None

    def restart(self) -> None:
        self.frame = 0
        self.accum = 0.0
        self.done = not self.frames

    def advance(self, dt: float) -> bool:
        """推進動畫。回傳 True 表示繞回（loop）或播完（non-loop）。"""
        if self.done or not self.frames:
            return True
        self.accum += dt * 1000.0
        wrapped = False
        while self.accum >= self.delay:
            self.accum -= self.delay
            if self.loop:
                if self.frame >= len(self.frames) - 1:
                    wrapped = True
                self.frame = (self.frame + 1) % len(self.frames)
            else:
                if self.frame >= len(self.frames) - 1:
                    self.frame = 0
                    self.accum = 0.0
                    self.done = True
                    wrapped = True
                    break
                self.frame += 1
        return wrapped

    @staticmethod
    def frame_at(frames: List[_Frame], t_ms: float) -> int:
        """無狀態選幀：依總 delay 取模後逐幀累加定位。

        適合傳送門、任務燈泡、金幣旋轉等「不保有幀狀態」的動畫。
        """
        if not frames:
            return 0
        total = sum(f[-1] for f in frames) or 1
        ms = t_ms % total
        for i, f in enumerate(frames):
            if ms < f[-1]:
                return i
            ms -= f[-1]
        return 0