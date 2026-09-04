"""世界生命体索引：轻量扫描 Map.wz 全部地图的 life 节点，收集真实出现过的 NPC / 怪物 ID。

只做 parse_partial(only={life, info}) 的属性树遍历，不解码任何影像 —— 全量 4000+ 张
地图约 1.5 秒（对比全解析 ~30 秒）。用于开放任务池时过滤掉给予/交付 NPC 或击杀怪
根本不在本世界的官方任务。
"""

from __future__ import annotations

from typing import Callable, Optional, Set, Tuple

_ONLY = frozenset({"life", "info"})
_REPORT_EVERY = 200


def _prop_str(node) -> str:
    if node is None:
        return ""
    try:
        return str(node.value)
    except (TypeError, ValueError):
        return ""


def collect_life_ids(map_wz, on_progress: Optional[Callable[[int, int], None]] = None
                     ) -> Tuple[Set[str], Set[str]]:
    """扫描 Map.wz → (npc_ids, mob_ids)，均为字符串 ID 集合。失败返回空集。

    ``on_progress(done, total)`` 每 ``_REPORT_EVERY`` 张图回报一次，末尾补齐
    done == total，供开屏进度条细化。
    """
    npc_ids: Set[str] = set()
    mob_ids: Set[str] = set()
    try:
        map_dir = map_wz.root.get("Map")
    except Exception:
        return npc_ids, mob_ids
    if map_dir is None:
        return npc_ids, mob_ids
    images = []
    for sub in map_dir.subdirs:
        try:
            images.extend((sub, name, img) for name, img
                          in map_dir.child(sub).images.items()
                          if name.endswith(".img"))
        except Exception:
            continue
    total = len(images)
    for i, (_sub, _name, img) in enumerate(images):
        try:
            root = img.parse_partial(only=_ONLY)
        except Exception:
            continue
        life = root.get("life")
        if life is not None:
            for item in life.children():
                kind = _prop_str(item.get("type"))
                lid = _prop_str(item.get("id"))
                if not lid:
                    continue
                if kind == "n":
                    npc_ids.add(lid)
                elif kind == "m":
                    mob_ids.add(lid)
        if on_progress is not None and (i + 1) % _REPORT_EVERY == 0:
            on_progress(i + 1, total)
    if on_progress is not None and total:
        on_progress(total, total)
    return npc_ids, mob_ids
