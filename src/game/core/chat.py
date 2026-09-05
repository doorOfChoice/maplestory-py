"""聊天框模型：纯状态机，不碰 pygame 事件与世界对象。

设计：聚焦态 / 输入缓冲 / 滚动日志三份状态收敛在 Chat 一处，
game.py 只做事件路由（谁在聚焦就把键交给谁），渲染层（render/chat.py）
只读本状态。日志行带 kind（player/system/error）供着色；
面板带闲置超时：无操作满 LOG_TTL_SECONDS 后 expire() 清空日志使其消失
（时间源可注入，便于测试）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional

# 日志最多保留的最近行数（超出丢弃最旧）
MAX_LOG_LINES = 10
# 输入缓冲最大长度（防粘贴超长串坏布局）
MAX_INPUT_CHARS = 120
# 日志面板无操作自动消失的静默时长（秒）
LOG_TTL_SECONDS = 5.0


@dataclass(frozen=True)
class ChatLine:
    kind: str      # player / system / error
    text: str


class Chat:
    __slots__ = ("focused", "text", "lines", "last_active", "_now")

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self.focused: bool = False
        self.text: str = ""
        self.lines: List[ChatLine] = []
        self._now = now
        self.last_active: float = now()

    # ── 活跃时间 ───────────────────────────────────────────────────
    def touch(self) -> None:
        """任何操作都刷新活跃时间（面板消失从最后一次操作起算）。"""
        self.last_active = self._now()

    # ── 聚焦态 ─────────────────────────────────────────────────────
    def open(self) -> None:
        self.focused = True
        self.touch()

    def close(self) -> None:
        """关闭只清缓冲，日志保留。"""
        self.focused = False
        self.text = ""

    # ── 输入缓冲 ───────────────────────────────────────────────────
    def type(self, chars: str) -> None:
        """TEXTINPUT 段进缓冲（逐字符或 IME 整段同一入口）。"""
        room = MAX_INPUT_CHARS - len(self.text)
        if room > 0:
            self.text += chars[:room]
        self.touch()

    def backspace(self) -> None:
        if self.text:
            self.text = self.text[:-1]
        self.touch()

    def submit(self) -> Optional[str]:
        """发送：返回本轮文本并清空缓冲；空内容返回 None。"""
        text, self.text = self.text, ""
        self.touch()
        return text if text else None

    # ── 日志 ───────────────────────────────────────────────────────
    def add(self, kind: str, text: str) -> None:
        self.lines.append(ChatLine(kind, text))
        if len(self.lines) > MAX_LOG_LINES:
            del self.lines[:len(self.lines) - MAX_LOG_LINES]
        self.touch()

    def expire(self) -> None:
        """静默超过 LOG_TTL_SECONDS 即清空日志（面板自动消失）；聚焦中暂停。"""
        if self.focused:
            return
        if self._now() - self.last_active >= LOG_TTL_SECONDS:
            self.lines.clear()
