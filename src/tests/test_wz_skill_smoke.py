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
        lo, hi = p.magic_attack_range(skill_mad=20)
        assert 1 <= lo <= hi and hi > 1
    finally:
        assets.close()


@needs_wz
def test_magician_second_job_semantics_from_wz():
    """真实 WZ：技能元素、群体治愈恢复率、毒雾术中毒、神之保护减伤、
    怪物 elemAttr/undead 均按 WZ 字段解析。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.core import skill_effects
    from game.systems.skills import SkillBook, load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        ids = ["2101002", "2101003", "2101004", "2101005",
               "2201004", "2201005", "2301002", "2301003", "2301005"]
        defs = load_skill_defs(assets, ids)
        assert defs["2101004"].element == "f"      # 火焰箭
        assert defs["2101005"].element == "s"      # 毒雾术
        assert defs["2201004"].element == "i"      # 冰冻术
        assert defs["2201005"].element == "l"      # 雷电术
        assert defs["2301005"].element == "h"      # 圣箭术

        # 群体治愈：恢复率取 level.hp；毒雾术：prop% 概率中毒 time 秒
        book = SkillBook(assets, 2300, defs=defs)
        book.add_sp(230, 10)
        book.learn("2301002", 120)
        heal = book.cast("2301002", 120)
        assert heal["form"] == "heal" and heal["heal_pct"] == 10 and heal["area"]
        # 神之保护：x=物理减伤%，登记进 dmg_reduce
        d = defs["2301003"]
        assert skill_effects.buff_mods(
            "2301003", lambda k: d.stat(d.max_level, k, 0)) == {"dmg_reduce": 30}

        fire = SkillBook(assets, 2100, defs=defs)
        fire.add_sp(210, 10)
        assert fire.learn("2101005", 120)
        poison = fire.cast("2101005", 120)
        assert poison["poison_prop"] == 31 and poison["poison_time"] == 4.0
        assert poison["element"] == "s" and poison["magic"] is True
        # 缓速术（火毒）同 冰雷 一样登记为 slow
        assert skill_effects.DEBUFF_SKILLS.get("2101003") == "slow"

        # 怪物属性：菇菇寶貝 弱火（F3）、不死系标记来自 info/undead
        assert assets.mob_info("0130100")["stats"].get("elemAttr") == "F3"
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
def test_magician_second_job_trees_load():
    """法师二转三系树自 WZ 加载，转职附赠 SP 进各自组池（被动不附赠）。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.core.jobs import JOBS, skill_ids_for_job
    from game.systems.skills import SkillBook
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        assert "2101004" in skill_ids_for_job(assets, 2100)   # 火焰箭
        assert "2201004" in skill_ids_for_job(assets, 2200)   # 冰冻术
        assert "2301005" in skill_ids_for_job(assets, 2300)   # 圣箭术
        for code, group in ((2100, 210), (2200, 220), (2300, 230)):
            book = SkillBook(assets, code)
            book.on_advance(JOBS[code])
            assert book.sp_for_group(group) == 4
            assert book.levels == {}          # 无附赠被动
    finally:
        assets.close()


@needs_wz
def test_thunder_bolt_exposes_wz_area_box():
    """真实 220.img：雷电术 cast 暴露 lt/rb=150×50 自身 AOE；冰冻术无 lt/rb → 扇形。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import SkillBook, load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        defs = load_skill_defs(assets, ["2201005", "2201004"])
        book = SkillBook(assets, 2200, defs=defs)
        book.add_sp(220, 2)
        assert book.learn("2201005", 30)
        assert book.cast("2201005", 30)["area"] == ((-150, -50), (150, 50))
        assert book.learn("2201004", 30)
        assert book.cast("2201004", 30)["area"] is None
    finally:
        assets.close()


@needs_wz
def test_magician_second_support_skills_wired_to_wz():
    """真实 220.img：冰冻术判为魔法攻击+冻结、缓速术判为减速 debuff、
    魔力吸收为被动、快速移动为已实装瞬移且作为缓速术前置受门控。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.core import skill_effects
    from game.core.jobs import skill_ids_for_job
    from game.systems.skills import SkillBook
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        assert "2201002" in skill_ids_for_job(assets, 2200)
        assert skill_effects.is_passive("2200000")
        book = SkillBook(assets, 2200)
        assert "2201002" in book.skills_for_group(220)   # 快速移动已实装，进技能窗
        assert "2201002" in book.learnable()
        book.add_sp(220, 20)
        assert book.learn("2201004", 120)
        cold = book.cast("2201004", 120)
        assert cold["magic"] is True and cold["freeze"] == 1.0
        # 缓速术前置 快速移动≥5：未点前置不可学
        assert book.learn("2201003", 120) is False
        for _ in range(5):
            assert book.learn("2201002", 120)
        assert book.learn("2201003", 120)
        slow = book.cast("2201003", 120)
        assert slow["form"] == "mob_status" and slow["status"] == "slow"
        assert slow["slow_x"] < 0 and slow["area"]
    finally:
        assets.close()


@needs_wz
def test_magician_cast_form_derived_from_wz_structure():
    """真实 WZ：三系魔法师技能按顶层节点结构推导施放形态，action 亦被解析。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import SkillBook, load_skill_defs, cast_form
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        ids = ["2001002", "2001004", "2001005",
               "2101003", "2101004",
               "2200000", "2201002", "2201003", "2201004", "2201005",
               "2301001", "2301005"]
        defs = load_skill_defs(assets, ids)

        def form(sid):
            d = defs[sid]
            return cast_form(d, d.max_level)

        assert form("2001002") == "buff" and defs["2001002"].action == "alert2"
        assert form("2001004") == "projectile"
        assert form("2001005") == "instant"
        assert form("2101004") == "projectile" and defs["2101004"].action == "shoot1"
        assert form("2101003") == "mob_status"
        assert form("2200000") == "passive"
        assert form("2201002") == "teleport"             # 只有 range
        assert form("2201003") == "mob_status"           # mob 节点
        assert form("2201004") == "instant"              # hit + time(冻结)
        assert form("2201005") == "aoe"                  # hit + lt/rb
        assert form("2301005") == "projectile"

        # 快速移动（2101002/2201002/2301001）三系均已实装并进技能窗
        for job, group, sid in ((2100, 210, "2101002"),
                                (2200, 220, "2201002"),
                                (2300, 230, "2301001")):
            book = SkillBook(assets, job)
            assert sid in book.skills_for_group(group)
            assert sid in book.learnable()
    finally:
        assets.close()


@needs_wz
def test_magician_level_help_parsed_from_string_wz():
    """真实 WZ：level.hs 指向 String.wz 的 hN，逐级说明被解析进 SkillDef.help()。"""
    pygame.init()
    pygame.display.set_mode((8, 8))
    from game.render.assets import Assets
    from game.systems.skills import load_skill_defs
    assets = Assets(settings.TRAINER_SPAWN_MAP)
    try:
        defs = load_skill_defs(assets, ["2001004", "2000000", "2201004"])
        assert "基本攻击力20" in defs["2001004"].help(1)
        assert "MP6" in defs["2001004"].help(1)
        # 2000000 的 level 表只有 hs、无任何数值字段：逐级说明是唯一效果描述
        assert defs["2000000"].help(1)
        assert defs["2201004"].help(1)
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
