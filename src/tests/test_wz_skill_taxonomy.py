"""WZ 全量技能分类冒烟：525 个职业技能都能落到一种交付方式（无 WZ 自动 skip）。

seam：game.core.skill_semantics.delivery/effects + game.systems.skills.load_skill_defs。
"""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from game import settings
from game.core import skill_semantics as sem
from game.core.skill_spec import DELIVERY_KINDS, Damage, Field

needs_wz = pytest.mark.skipif(
    not (settings.WZ_DIR / "Skill.wz").exists(), reason="需要 WZ 资产")

_SPECIAL = {"BFSkill.img", "ItemSkill.img", "MCGuardian.img", "MCSkill.img",
            "MobSkill.img"}


class _WzStub:
    """只开 Skill/String 两张图的最小资产桩（分类不触碰 pygame）。"""

    def __init__(self):
        from wzpy.wz_file import WzFile
        self.wz = {
            "Skill": WzFile.open(str(settings.WZ_DIR / "Skill.wz"),
                                 region=settings.REGION),
            "String": WzFile.open(str(settings.WZ_DIR / "String.wz"),
                                  region=settings.REGION),
        }


def _load_all():
    from game.systems.skills import load_skill_defs
    assets = _WzStub()
    ids = []
    for img_name in assets.wz["Skill"].root.images.keys():
        if img_name in _SPECIAL:
            continue
        node = assets.wz["Skill"].root.images.get(img_name).parse().get("skill")
        if node is None:
            continue
        ids.extend(c.name for c in node.children() if c.name.isdigit())
    return load_skill_defs(assets, ids), ids


@needs_wz
def test_every_job_skill_classified_without_unsupported():
    """全部职业技能都落到已知交付方式，无 unsupported（框架全量覆盖）。"""
    defs, ids = _load_all()
    assert len(defs) == len(ids) and len(ids) >= 500
    kinds = {sem.delivery(d, d.max_level) for d in defs.values()}
    assert kinds <= set(DELIVERY_KINDS)
    unsupported = [d.id for d in defs.values()
                   if sem.delivery(d, d.max_level) == "unsupported"]
    assert unsupported == []


@needs_wz
def test_archer_tree_classification_and_payloads():
    """弓箭手线：召唤/状态/多发/地面/解异常按 WZ 结构正确归类。"""
    defs, _ = _load_all()

    def kind(sid):
        return sem.delivery(defs[sid], defs[sid].max_level)

    assert kind("3001005") == "projectile"       # 二连射（无 ball 多发）
    assert kind("3111002") == "summon"           # 替身术
    assert kind("3111005") == "summon"           # 银鹰召唤
    assert kind("3121006") == "summon"           # 火凤凰
    assert kind("3121007") == "mob_status"       # 击退箭
    assert kind("3121009") == "buff"             # 勇士的意志（含 Cleanse）

    # 烈火箭：弹道 + 地面燃烧子句共存
    fire = sem.effects(defs["3111003"], defs["3111003"].max_level)
    assert any(isinstance(e, Field) for e in fire)
    assert any(isinstance(e, Damage) for e in fire)

    # 弓箭手线不再有 unsupported
    archer = [d for d in defs.values()
              if d.id.startswith(("300", "310", "311", "312")) and len(d.id) == 7]
    assert archer
    assert all(sem.delivery(d, d.max_level) != "unsupported" for d in archer)
