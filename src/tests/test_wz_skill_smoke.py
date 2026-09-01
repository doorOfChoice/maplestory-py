"""WZ 冒烟：真实 Skill.wz 弓箭手树解析（无 WZ 环境自动 skip）。"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from game import settings

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Skill.wz").exists(), reason="需要 WZ 资产")


@needs_wz
def test_bowman_tree_contains_bowman_skills():
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    from game.jobs import skill_ids_for_job
    from game.skills import load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        ids = skill_ids_for_job(assets, 3000)
        assert "3001004" in ids
        defs = load_skill_defs(assets, ["3001004", "3001005"])
        assert defs["3001004"].name == "断魂箭"
        assert defs["3001005"].req == {"3001004": 1}
        assert defs["3001004"].stat(1, "mpCon") == 7
        assert defs["3001005"].stat(1, "bulletCount") == 2
        assert assets.skill_ball_frames("3001004")
        assert assets.skill_icon("3001004") is not None
    finally:
        assets.close()


@needs_wz
def test_buff_skill_level_has_time_field():
    """真实 buff 技能：疾風步(3001003) level 表含 time（秒，70s）与 mpCon。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    from game.skills import load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        d = load_skill_defs(assets, ["3001003"])["3001003"]
        assert d.stat(1, "time") == 70
        assert d.stat(1, "mpCon") == 8
    finally:
        assets.close()


@needs_wz
def test_bowman_passive_mods_reads_real_fields():
    """真实被动：转职后 passive_mods 解析 霸王箭的 prop/damage、精準強化 x。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    from game.skills import load_skill_defs, SkillBook
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        defs = load_skill_defs(assets, ["3000000", "3000001", "3000002"])
        book = SkillBook(assets, 3000, defs=defs)
        book.on_advance(__import__("game.jobs", fromlist=["JOBS"]).JOBS[3000])
        mods = book.passive_mods()
        # 霸王箭(3000001) 满级 prop=40、damage=200；精準強化(3000000) x=16
        assert mods["crit"] == 40
        assert mods["crit_mult"] == 200
        assert mods["acc"] == 16
        assert mods.get("range", 0) > 0
    finally:
        assets.close()



    """MobSkill.img 含毒(125)/晕(123)/减速(126) 技能，level 表带 time/prop。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        img = assets.wz["Skill"].root.images.get("MobSkill.img")
        node = img.parse()
        for sid in ("123", "125", "126"):
            assert node.get(sid) is not None
        poison_lv1 = node.get("125/level/1")
        assert poison_lv1 is not None
        assert getattr(poison_lv1.get("time"), "value", None) > 0
        assert getattr(poison_lv1.get("prop"), "value", None) > 0
    finally:
        assets.close()


@needs_wz
def test_map_mobs_have_no_status_skill_refs():
    """本 WZ 怪物 img 无 skill 引用节点：解析返回空表（映射缺省静默）。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.assets import Assets
    from game.monster import parse_mob_status_skills
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        mob_ids = {str(int(l["id"])) for l in assets.life}
        for mid in mob_ids:
            img = assets.wz["Mob"].root.images.get(f"{mid.zfill(7)}.img")
            node = img.parse().get("skill") if img is not None else None
            assert parse_mob_status_skills(node) == []
    finally:
        assets.close()
