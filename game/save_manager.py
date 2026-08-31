"""存檔管理：把玩家狀態序列化為 JSON 並寫盤。

主執行緒只做快照收集（純記憶體 dict），檔案寫入在後台執行緒執行，
不阻塞遊戲主循環。退出時 `flush()` 同步等待最後一次寫入完成。
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional


class SaveManager:
    """非同步存檔管理：request_save 提交快照，後台線程寫盤。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._pending: Optional[dict] = None
        self._thread: Optional[threading.Thread] = None

    def load(self) -> Optional[dict]:
        """讀取存檔。不存在或損壞時回傳 None。"""
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def request_save(self, data: dict) -> None:
        """提交快照，非同步寫盤（不阻塞主執行緒）。"""
        with self._lock:
            self._pending = data
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._drain, daemon=True)
                self._thread.start()

    def flush(self, data: Optional[dict] = None) -> None:
        """等待/完成寫入（退出時使用）。

        無 data：僅等待後台線程把已排隊的快照寫完。
        有 data：清掉排隊中的舊快照，等舊寫入結束後同步寫入最新。
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
        """後台線程：消費最新待寫快照後退出。"""
        while True:
            with self._lock:
                data = self._pending
                if data is None:
                    return
                self._pending = None
            self._write(data)

    def _write(self, data: dict) -> None:
        """原子寫入：先寫 tmp 再 rename。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def collect_data(player, combat, map_id: str) -> dict:
        """收集所有需要存檔的遊戲狀態為 dict。"""
        return {
            "version": 1,
            "player": {
                "level": player.level,
                "exp": player.exp,
                "hp": player.hp,
                "max_hp": player.max_hp,
                "mp": player.mp,
                "max_mp": player.max_mp,
                "job": player.job,
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