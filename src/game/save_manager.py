"""存档管理：把玩家状态序列化为 JSON 并写盘。

主执行绪只做快照收集（纯记忆体 dict），档案写入在后台执行绪执行，
不阻塞游戏主循环。退出时 `flush()` 同步等待最后一次写入完成。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from game import settings
from game.core import stats as stats_mod
from game.core.jobs import JOBS


class SaveRegistry:
    """存档组件注册表：新增可存档系统只需 register，无需改动 collect_data。

    每个条目描述一个「命名子组件」：
      · collect  从 (player, combat) 快照中抽取 dict（序列化）
      · apply    把 dict 还原回目标对象（反序列化）

    collect_data 遍历所有登记条目拼接；restore 逐个还原。加载路径与
    组件自身 to_dict/from_dict 契约一致，可独立测试、可插拔。
    """

    def __init__(self) -> None:
        self._collect: Dict[str, Callable[[object, object], dict]] = {}
        self._apply: Dict[str, Callable[[object, object, dict], None]] = {}

    def register(self, key: str,
                 collect: Callable[[object, object], dict],
                 apply: Callable[[object, object, dict], None]) -> None:
        """登记一个组件。collect 抽 dict；apply 把 dict 写回组件。"""
        self._collect[key] = collect
        self._apply[key] = apply

    def extend(self, base: dict, player, combat) -> dict:
        """把当前登记的所有组件快照合并进 base，回传 base。"""
        for key, fn in self._collect.items():
            base[key] = fn(player, combat)
        return base

    def restore(self, player, combat, data: dict) -> None:
        """按登记把 data 里对应键还原进组件（缺键则跳过）。"""
        for key, fn in self._apply.items():
            if key in data:
                fn(player, combat, data[key])


# 内置存档组件：背包 / 技能 / 任务 / 世界元数据（金币·击杀）。
REGISTRY = SaveRegistry()
REGISTRY.register(
    "inventory",
    lambda p, c: p.inventory.to_dict(),
    lambda p, c, d: p.inventory.from_dict(d, getattr(p, "assets", None)))
REGISTRY.register(
    "skills", lambda p, c: p.skills.to_dict(),
    lambda p, c, d: p.skills.from_dict(d))
REGISTRY.register(
    "quests", lambda p, c: p.quests.to_dict(),
    lambda p, c, d: p.quests.from_dict(d))
REGISTRY.register(
    "meta",
    lambda p, c: {"meso": c.meso, "total_kills": c.total_kills},
    lambda p, c, d: (setattr(c, "meso", d.get("meso", 0)),
                     setattr(c, "total_kills", d.get("total_kills", 0))))



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
        """逐级迁移旧档：v1→v2 补 job/快捷键；v2→v3 补四维与 AP；v3→v4 补仓库。"""
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
        if data.get("version") < 4:
            data.setdefault("inventory", {}).setdefault("storage", [])
            data["version"] = 4
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
        """收集所有需要存档的游戏状态为 dict。

        玩家核心字段与地图直接组合，其余可存档组件由 REGISTRY 自动拼接，
        新增系统时注册即可，无需改动本方法。
        """
        data = {
            "version": 4,
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
        }
        return REGISTRY.extend(data, player, combat)