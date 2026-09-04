"""蜗牛投掷术（10001000）：新手可学的正式技能——SP 学习、快捷键施放、弹道掷蜗牛。"""

from __future__ import annotations

import math

import pygame

from game import settings
from game.entities.player import Player
from game.systems.combat import Combat
from game.core.jobs import sp_group_of_skill
from game.systems.skills import SkillBook

SNAIL = settings.SNAIL_THROW_SKILL_ID
ISLOT = {"01302000": "Wp", "01452002": "WpOB"}


class StarterAssets:
    def equip_info(self, item_id: str) -> dict:
        return {"islot": ISLOT.get(f"{int(item_id):08d}", "")}

    def consume_info(self, item_id: str) -> dict:
        return {}

    def item_name(self, item_id: str):
        return None

    def character_frames(self, *a, **k):
        return []

    def character_navel_px(self, *a, **k):
        return (0, 0)

    def attack_pose(self, equips):
        return "swingO1"


def make_player(monkeypatch) -> Player:
    monkeypatch.setattr(Player, "_load_anim", lambda self, pose, flip=None: None)
    return Player(StarterAssets(), 0.0, 0.0)


# ── 技能书：可学 / SP 组 / 施放数据 ──────────────────────────────────
def test_snail_throw_is_learnable_by_newbie():
    book = SkillBook(None, 0)
    assert SNAIL in book.learnable()
    assert sp_group_of_skill(SNAIL) == 100


def test_newbie_level_up_grants_sp_to_snail_group():
    book = SkillBook(None, 0)
    book.gain_sp_for_level(2, 3)
    assert book.sp_for_group(100) == 3


def test_learn_and_cast_snail_throw():
    book = SkillBook(None, 0)
    book.add_sp(100, 1)
    assert book.learn(SNAIL, 1) is True
    data = book.cast(SNAIL, 1)
    assert data is not None
    assert data["projectile"] is True
    assert data["damage"] > 0 and data["mp_con"] > 0


# ── 玩家施放接线 ─────────────────────────────────────────────────────
def test_player_cast_snail_throw_sets_projectile_pending(monkeypatch):
    p = make_player(monkeypatch)
    p.skills.add_sp(100, 1)
    assert p.skills.learn(SNAIL, 1)
    p.mp = 50
    data = p.skills.cast(SNAIL, 1)
    assert p.start_attack(data) is True
    assert p.attacking
    assert p.pending_skill is not None and p.pending_skill["projectile"]


def test_newbie_normal_attack_is_not_projectile(monkeypatch):
    p = make_player(monkeypatch)
    assert p.start_attack() is True
    assert p.pending_skill is None


# ── 弹道生成 ─────────────────────────────────────────────────────────
class SnailAssets:
    def __init__(self):
        marker = pygame.Surface((8, 8))
        self.ball = [(marker, (4, 4), 100)]

    def snail_frames(self):
        return self.ball

    def skill_ball_frames(self, sid):
        return self.ball

    def skill_hit_frames(self, sid):
        return []


class ProjectilePlayer:
    x, y = 0.0, 100.0
    facing_right = True
    level = 1

    def attack_range(self):
        return (5, 5)

    def crit_rate(self):
        return 0.0

    def crit_mult(self):
        return 1.5


def cast_data(**over) -> dict:
    d = {"id": SNAIL, "def": None, "level": 1, "mp_con": 4, "hp_con": 0,
         "damage": 1.0, "range": 0, "mob_count": 1, "bullet_count": 1,
         "projectile": True}
    d.update(over)
    if d["projectile"]:
        d["speed"] = settings.SNAIL_THROW_SPEED
        d["life"] = settings.SNAIL_THROW_LIFETIME
    return d


def test_snail_skill_spawns_snail_projectile():
    combat = Combat(SnailAssets())
    combat.spawn_arrows(ProjectilePlayer(), cast_data())
    assert len(combat.arrows) == 1
    a = combat.arrows[0]
    assert a.frames == combat.assets.ball
    assert math.isclose(math.hypot(a.vx, a.vy), settings.SNAIL_THROW_SPEED,
                        rel_tol=1e-6)
    assert a.life == settings.SNAIL_THROW_LIFETIME


def test_plain_skill_projectile_keeps_arrow_speed():
    combat = Combat(SnailAssets())
    combat.spawn_arrows(ProjectilePlayer(),
                        cast_data(id="3001005", projectile=False))
    a = combat.arrows[0]
    assert math.isclose(math.hypot(a.vx, a.vy), settings.ARROW_SPEED,
                        rel_tol=1e-6)
    assert a.life == settings.ARROW_LIFETIME
