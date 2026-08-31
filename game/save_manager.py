"""存档管理：把玩家状态序列化为 JSON 并写盘。

主执行绪只做快照收集（纯记忆体 dict），档案写入在后台执行绪执行，
不阻塞游戏主循环。退出时 `flush()` 同步等待最后一次写入完成。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from . import settings
from . import stats as stats_mod
from .jobs import JOBS


class SaveManager:
    """非同步存档管理：request_save 提交快照，后台线程写盘。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._pending: Optional[dict] = None
        self._thread: Optional[threading.Thread] = None

    def load(self) -> Optional[dict]:
        """读取存档。不存在或损坏时回传 None；旧档自动迁移到当前版本。"""
        if not self.path.exists():
            return None
        try:
            return self.migrate(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            return None

    @staticmethod
    def migrate(data: dict) -> dict:
        """逐级迁移旧档：v1→v2 补 job/快捷键；v2→v3 补四维与 AP。"""
        if data.get("version", 1) < 2:
            player = data.setdefault("player", {})
            player.setdefault("job", 0)
            skills = data.setdefault("skills", {})
            skills.setdefault("hotkeys", {})
            data["version"] = 2
        if data.get("version") < 3:
            player = data.setdefault("player", {})
            jobdef = JOBS.get(player.get("job", 0)) or JOBS[0]
            total_ap = max(0, int(player.get("level", 1)) - 1) * settings.AP_PER_LEVEL
            stats, ap = stats_mod.auto_allocate(
                stats_mod.base_stats(), total_ap, jobdef.auto_ap)
            player["stats"] = stats
            player["ap"] = ap
            data["version"] = 3
        return data

    def request_save(self, data: dict) -> None:
        """提交快照，非同步写盘（不阻塞主执行绪）。"""
        with self._lock:
            self._pending = data
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._drain, daemon=True)
                self._thread.start()

    def flush(self, data: Optional[dict] = None) -> None:
        """等待/完成写入（退出时使用）。

        无 data：仅等待后台线程把已排队的快照写完。
        有 data：清掉排队中的旧快照，等旧写入结束后同步写入最新。
        """
        if data is None:
            with self._lock:
                t = self._thread
            if t is not None and t.is_alive():
                t.join(timeout=5)
            return
        with self._lock:
            self._pending = None
            t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=5)
        self._write(data)

    def _drain(self) -> None:
        """后台线程：消费最新待写快照后退出。"""
        while True:
            with self._lock:
                data = self._pending
                if data is None:
                    return
                self._pending = None
            self._write(data)

    def _write(self, data: dict) -> None:
        """原子写入：先写 tmp 再 rename。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def collect_data(player, combat, map_id: str) -> dict:
        """收集所有需要存档的游戏状态为 dict。"""
        return {
            "version": 3,
            "player": {
                "level": player.level,
                "exp": player.exp,
                "hp": player.hp,
                "max_hp": player.max_hp,
                "mp": player.mp,
                "max_mp": player.max_mp,
                "job": player.job,
                "stats": dict(player.stats),
                "ap": player.ap,
                "map_id": map_id,
                "x": player.x,
                "y": player.y,
                "facing_right": player.facing_right,
            },
            "inventory": player.inventory.to_dict(),
            "skills": player.skills.to_dict(),
            "quests": player.quests.to_dict(),
            "meta": {
                "meso": combat.meso,
                "total_kills": combat.total_kills,
            },
        }