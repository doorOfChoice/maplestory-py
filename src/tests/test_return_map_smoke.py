"""WZ 冒烟：地图 info.returnMap 可读（回程卷轴哨兵落点；无 WZ 环境自动 skip）。"""
from __future__ import annotations

import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Map.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_describe_exposes_return_map():
    from wzpy.map import MapRenderer
    from wzpy.wz_file import WzFile
    wz = WzFile.open(str(settings.WZ_DIR / "Map.wz"), region=settings.REGION)
    try:
        desc = MapRenderer(wz).describe("300000012")
        assert desc["returnMap"] == 300000010
    finally:
        wz.close()
