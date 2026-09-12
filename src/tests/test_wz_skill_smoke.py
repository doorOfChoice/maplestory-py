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
    from game.render.assets import Assets
    from game.core.jobs import skill_ids_for_job
    from game.systems.skills import load_skill_defs
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
def test_magician_tree_loads_magic_bolt():
    """真实 200.img：法师技能树含魔法弹（有 ball 贴图），cast 标记 magic/projectile。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.core.jobs import skill_ids_for_job
    from game.systems.skills import SkillBook, load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        ids = skill_ids_for_job(assets, 2000)
        assert "2001004" in ids and "2001002" in ids
        defs = load_skill_defs(assets, ["2001004", "2001003", "2001002"])
        assert defs["2001004"].name == "魔法弹"
        assert defs["2001004"].stat(1, "mad") == 20
        assert defs["2001003"].stat(1, "time") > 0     # 魔法铠甲是 buff
        assert assets.skill_ball_frames("2001004")
        book = SkillBook(assets, 2000, defs=defs)
        book.add_sp(200, 1)
        assert book.learn("2001004", 10)
        data = book.cast("2001004", 10)
        assert data["magic"] is True and data["projectile"] is True
    finally:
        assets.close()


@needs_wz
def test_magician_magic_claw_has_no_ball_is_not_projectile():
    """真实 200.img：魔法双击无 ball 节点，cast 标记 magic 但不生成弹道。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import SkillBook, load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        defs = load_skill_defs(assets, ["2001004", "2001005"])
        assert defs["2001005"].has_ball is False
        assert not assets.skill_ball_frames("2001005")
        book = SkillBook(assets, 2000, defs=defs)
        book.add_sp(200, 20)
        assert book.learn("2001004", 1)     # 双击前置：魔法弹 1 级
        assert book.learn("2001005", 10)
        data = book.cast("2001005", 10)
        assert data["magic"] is True and not data.get("projectile")
        assert data.get("cone_attack") is True       # 瞬发扇形
    finally:
        assets.close()


@needs_wz
def test_magician_advance_grants_wand_and_magic_range():
    """转职法师：附赠木制短杖（装 Wp、incMAD>0），魔法区间随 INT 与武器 MAD 生效。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.entities.player import Player
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        p = Player(assets, 0.0, 0.0)
        p.advance_to(settings.MAGICIAN_JOB, assets)
        weapon = p.inventory.equipped.get("weapon")
        assert p.job == settings.MAGICIAN_JOB
        assert weapon is not None
        assert int(weapon.id) == int(settings.MAGICIAN_STARTER_WAND)
        assert weapon.stat("incMAD") > 0
        p.stats["int"] = 40
        lo, hi = p.magic_attack_range()
        assert 1 <= lo <= hi and hi > 1
    finally:
        assets.close()


@needs_wz
def test_bowman_second_third_job_trees_load():
    """2/3/4 转（猎人/神射手/弓手大师）技能树自 WZ 正常加载，转职附赠被动满级生效。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.core.jobs import JOBS, skill_ids_for_job
    from game.systems.skills import SkillBook
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        assert "3101005" in skill_ids_for_job(assets, 3100)
        assert "3111006" in skill_ids_for_job(assets, 3110)
        hunter = SkillBook(assets, 3100)
        hunter.on_advance(JOBS[3000])       # 累积一转被动（霸王箭产 crit_mult）
        hunter.on_advance(JOBS[3100])
        assert hunter.levels["3100000"] == hunter.defs["3100000"].max_level
        hm = hunter.passive_mods()
        assert hm["acc"] > 0 and hm["crit_mult"] >= 200
        assert hm["mastery"] > 0            # 精準之弓 mastery 生效
        bm = SkillBook(assets, 3110)
        bm.on_advance(JOBS[3110])
        assert bm.levels["3110001"] == bm.defs["3110001"].max_level
        assert "3121006" in skill_ids_for_job(assets, 3120)
        bm4 = SkillBook(assets, 3120)
        bm4.on_advance(JOBS[3120])
        assert bm4.levels["3120005"] == bm4.defs["3120005"].max_level
        assert bm4.passive_mods()["acc"] > 0
    finally:
        assets.close()


@needs_wz
def test_buff_skill_level_has_time_field():
    """真实 buff 技能：疾風步(3001003) level 表含 time（秒，70s）与 mpCon。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        d = load_skill_defs(assets, ["3001003"])["3001003"]
        assert d.stat(1, "time") == 70
        assert d.stat(1, "mpCon") == 8
    finally:
        assets.close()


@needs_wz
def test_real_buff_skills_map_to_player_mods():
    """真实 buff：集中術 acc/eva→平坦命中回避、楓葉祝福 x→stat_pct、召唤不产玩家增益。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.core.skill_effects import buff_mods
    from game.systems.skills import load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        ids = ["3001003", "3121000", "3121006"]
        defs = load_skill_defs(assets, ids)

        def mods(sid):
            d = defs[sid]
            lv = d.max_level
            return buff_mods(sid, lambda k, d=d, lv=lv: d.stat(lv, k, 0))

        m = mods("3001003")
        assert m["acc_flat"] > 0 and m["eva_flat"] > 0
        assert mods("3121000") == {"stat_pct": 15}
        assert mods("3121006") == {}          # 召唤：pad 不作用于玩家
    finally:
        assets.close()


@needs_wz
def test_bowman_passive_mods_reads_real_fields():
    """真实被动：转职后 passive_mods 解析 霸王箭的 prop/damage、精準強化 x。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import load_skill_defs, SkillBook
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        defs = load_skill_defs(assets, ["3000000", "3000001", "3000002"])
        book = SkillBook(assets, 3000, defs=defs)
        book.on_advance(__import__("game.core.jobs", fromlist=["JOBS"]).JOBS[3000])
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
    from game.render.assets import Assets
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
def test_magician_passive_mods_reads_real_fields():
    """真实被动：法师 2000000/2000001 需 SP 学，学满后 passive_mods 出 mp_regen/mp。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import SkillBook
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        book = SkillBook(assets, 2000)
        assert "2000000" in book.learnable()
        assert "2000001" in book.learnable()
        book.add_sp(200, 100)
        for _ in range(book.defs["2000000"].max_level):
            book.learn("2000000", 200)
        for _ in range(book.defs["2000001"].max_level):
            book.learn("2000001", 200)
        assert book.levels["2000000"] == 16
        assert book.passive_mods() == {"mp_regen": 32, "mp": 20}
    finally:
        assets.close()


@needs_wz
def test_map_mobs_have_no_status_skill_refs():
    """本 WZ 怪物 img 无 skill 引用节点：解析返回空表（映射缺省静默）。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.entities.monster import parse_mob_status_skills
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        mob_ids = {str(int(l["id"])) for l in assets.life}
        for mid in mob_ids:
            img = assets.wz["Mob"].root.images.get(f"{mid.zfill(7)}.img")
            node = img.parse().get("skill") if img is not None else None
            assert parse_mob_status_skills(node) == []
    finally:
        assets.close()
