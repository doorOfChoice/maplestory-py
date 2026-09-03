"""转职状态与存档 v2：job/快捷键入档、v1 旧档迁移。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from game.save_manager import SaveManager
from game.systems.skills import SkillBook
from game.systems.skills import SkillDef


def fake_player(job: int = 3000) -> SimpleNamespace:
    book = SkillBook(None, job, defs={
        "3001004": SkillDef("3001004", "断魂箭", "", [{"mpCon": 7}] * 20, 20),
    })
    book.add_sp(300, 2)
    book.levels["3001004"] = 3
    book.hotkeys[1] = "3001004"
    return SimpleNamespace(
        level=12, exp=30, hp=100, max_hp=120, mp=30, max_mp=40,
        job=job, stats={"str": 4, "dex": 54, "int": 4, "luk": 4}, ap=4,
        x=100.0, y=200.0, facing_right=True,
        inventory=SimpleNamespace(to_dict=lambda: {"consumes": {}, "etcs": {},
                                                   "equips": [], "equipped": {}}),
        skills=book,
        quests=SimpleNamespace(to_dict=lambda: {"status": {}, "kills": {},
                                                "accepted_order": []}),
    )


def test_save_v3_roundtrip():
    """collect_data 含 job/四维/AP；load 后一致。"""
    player = fake_player()
    combat = SimpleNamespace(meso=50, total_kills=3)
    data = SaveManager.collect_data(player, combat, "100000000")
    assert data["version"] == 4
    assert data["player"]["job"] == 3000
    assert data["player"]["stats"]["dex"] == 54
    assert data["player"]["ap"] == 4
    assert data["skills"]["hotkeys"] == {"1": "3001004"}

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "save.json"
        sm = SaveManager(path)
        sm.flush(data)
        loaded = sm.load()
    assert loaded["player"]["job"] == 3000
    book = SkillBook(None, loaded["player"]["job"], defs=player.skills.defs)
    book.from_dict(loaded["skills"])
    assert book.hotkeys == {1: "3001004"}
    assert book.levels == {"3001004": 3}


def test_migrate_v1_defaults():
    """v1 旧档（无 job/hotkeys/四维）载入时逐级迁移到 v3，不崩。"""
    v1 = {
        "version": 1,
        "player": {"level": 5, "exp": 0, "hp": 50, "max_hp": 100,
                   "mp": 10, "max_mp": 50, "map_id": "100010000",
                   "x": 10.0, "y": 20.0},
        "inventory": {},
        "skills": {"sp": 1, "levels": {"1001004": 1}},
        "quests": {},
        "meta": {"meso": 0, "total_kills": 0},
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "save.json"
        path.write_text(json.dumps(v1), encoding="utf-8")
        loaded = SaveManager(path).load()
    assert loaded["version"] == 4
    assert loaded["player"]["job"] == 0
    assert loaded["skills"]["hotkeys"] == {}
    # Lv5 新手：(5-1)×5=20 AP 按权重全进力量
    assert loaded["player"]["stats"]["str"] == 24
    assert loaded["player"]["ap"] == 0


def test_migrate_null_job_normalized():
    """job 为 null 的脏档（v4）载入时归一为 0（新手），不阻断转职门控。"""
    data = SaveManager.collect_data(fake_player(job=None),
                                    SimpleNamespace(meso=0, total_kills=0),
                                    "100010000")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "save.json"
        sm = SaveManager(path)
        sm.flush(data)
        loaded = sm.load()
    assert loaded["player"]["job"] == 0
