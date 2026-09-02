"""怪物巡逻：应能在整条相连的可行走平台上走动，而不是被钳在出生点那一小段。"""

import pygame

from game.entities.monster import Monster
from game.core.physics import Physics


def fh(fid, layer, x1, y1, x2, y2, prev=-1, next=-1, platform=0):
    return {"id": fid, "layer": layer, "platform": platform,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "prev": prev, "next": next}


def make(segs):
    return Physics(segs, [], bounds={"left": -1000, "right": 2000,
                                         "top": 0, "width": 3000, "height": 500})


class FakeAssets:
    """无需 WZ 的最小资产桩：只提供怪物移动/站立的两帧。"""

    def __init__(self):
        self._surf = pygame.Surface((12, 12))

    def mob_info(self, mob_id):
        return {"name": "Test", "stats": {"hp": 50, "exp": 5,
                                          "weaponAttack": 10, "speed": 0},
                "drops": []}

    def mob_frames(self, mob_id, action, flip=False):
        return [(self._surf, 100)] if action in ("move", "stand") else []

    def mob_origin(self, mob_id, action):
        return (0, 0)


class _FakeAudio:
    """间谍对象：记录 play() 被调用时的音效名和音量。"""

    def __init__(self):
        self.calls = []

    def play(self, name, volume=0.7):
        self.calls.append((name, volume))

    def play_mob_death(self, mob_id, volume=0.5):
        self.calls.append((f"MobDeath/{mob_id}", volume))


# 一条 5 段连续平台（每段 90px）在同一 layer，prev/next 相连
CHAIN = [fh(1, 0, 0, 0, 90, 0, next=2),
         fh(2, 0, 90, 0, 180, 0, prev=1, next=3),
         fh(3, 0, 180, 0, 270, 0, prev=2, next=4),
         fh(4, 0, 270, 0, 360, 0, prev=3, next=5),
         fh(5, 0, 360, 0, 450, 0, prev=4)]


def test_mob_max_hp_comes_from_stats_hp():
    """怪物生命上限应读取 stats 的 hp 字段（wzpy 输出契约），而非默认 10 兜底。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    assert mob.max_hp == 50


def test_patrol_roams_across_chained_platform():
    """怪物生在平台中段，却能巡逻到两端，而非卡在出生点那一小段。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    lo = hi = mob.x
    for _ in range(1200):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        lo = min(lo, mob.x)
        hi = max(hi, mob.x)
    assert hi > 350   # 走到了右端（跨过多段）
    assert lo < 100   # 走到了左端（跨过多段）


# ── 重力：从高台边缘走到断口应真的掉下去、落到下层平台 ─────────────
# 高台 y=100 只铺到 x=100；经竖直 riser（fh2/fh3）连到 y=160 的低台（fh4），
# 高差 60px > 一级台阶 36px，walk_surface 拒绝自动下步 → 应转为下落。
CLIFF = [fh(1, 0, 0, 100, 100, 100, next=2),
         fh(2, 0, 100, 100, 100, 130, prev=1, next=3),   # 竖直 riser
         fh(3, 0, 100, 130, 100, 160, prev=2, next=4),   # 竖直 riser
         fh(4, 0, 100, 160, 300, 160, prev=3)]


def test_does_not_fall_off_ledge_turns_back():
    """怪物走上高台边缘（断口）时应折返，而不是掉到低台或悬空。"""
    ph = make(CLIFF)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 50, "y": 100, "cy": 100,
                                     "rx0": 0, "rx1": 300}, 0, ph)
    hi_x = mob.x
    for _ in range(400):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        hi_x = max(hi_x, mob.x)
        assert mob.cy == 100  # 始终站在高台高度，不下落
    assert hi_x <= 100  # 巡逻在高台右缘折返，不越过断口


def test_death_sound_played_once_on_mob_die():
    """怪物死亡时应在首次 update 播放一次 MobDeath 音效，之后不再重复。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                     "rx0": 0, "rx1": 450}, 0, ph)
    audio = _FakeAudio()
    mob.take_hit(999, from_x=210)  # HP 归零，触发 die()
    assert mob.dead
    # 首次 update：应播放死亡音效
    mob.update(0.05, player_x=100000, player_y=0, mobs=[], audio=audio)
    assert audio.calls == [("MobDeath/100101", 0.5)]
    # 后续 update：不应再播放
    mob.update(0.05, player_x=100000, player_y=0, mobs=[], audio=audio)
    assert audio.calls == [("MobDeath/100101", 0.5)]


def test_death_sound_not_played_without_audio():
    """怪物死亡时若未传入 audio，不应报错。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                     "rx0": 0, "rx1": 450}, 0, ph)
    mob.take_hit(999, from_x=210)
    mob.update(0.05, player_x=100000, player_y=0, mobs=[])  # 无 audio
