"""怪物巡逻：应能在整条相连的可行走平台上走动，而不是被钳在出生点那一小段。"""

import pygame
import pytest

from game import settings
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


def test_patrol_bounds_inset_by_drawn_half_width():
    """巡逻边界应按贴图半宽内缩：身体边缘贴平台边折返，不半身悬出。"""

    class WideAssets(FakeAssets):
        def __init__(self):
            super().__init__()
            self._surf = pygame.Surface((60, 24))

    ph = make(CHAIN)
    mob = Monster(WideAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    assert mob.rx0 == pytest.approx(30.0)
    assert mob.rx1 == pytest.approx(420.0)


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


def test_mob_chases_only_after_beating():
    """被打一记后反击追击：哪怕巡逻方向背对玩家，也折回逼近到贴脸为止。"""
    ph = make(CHAIN)
    # flip=True → 初始朝左巡逻；玩家在右侧 300，只有追击才会向右接近
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 200, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450, "flip": True}, 0, ph)
    mob.take_hit(5, from_x=300)
    for _ in range(60):
        mob.update(0.05, player_x=300, player_y=0, mobs=[])
    assert mob.x > 200                        # 掉头朝玩家方向推进
    assert abs(300 - mob.x) <= settings.MOB_ATTACK_RANGE + 1


def test_boss_stands_ground():
    """boss 怪守位：不漫游、挨打也不追，位置纹丝不动，只有接触伤害。"""

    class BossAssets(FakeAssets):
        def mob_info(self, mob_id):
            info = FakeAssets.mob_info(self, mob_id)
            info["stats"]["boss"] = True
            return info

    ph = make(CHAIN)
    mob = Monster(BossAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    for _ in range(200):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
    mob.take_hit(5, from_x=250)
    x_after_hit = mob.x                      # 允许原版受击小击退
    for _ in range(200):
        mob.update(0.05, player_x=250, player_y=0, mobs=[])
    assert mob.x == x_after_hit              # 但绝不反击追击
    assert mob.action == "stand"


def test_chase_speed_follows_wz_speed_stat():
    """追击/移动速度取自 WZ stats.speed（有符号偏移）：+60 明显快于 -50。"""

    class SpeedAssets(FakeAssets):
        def __init__(self, spd):
            super().__init__()
            self._spd = spd

        def mob_info(self, mob_id):
            info = FakeAssets.mob_info(self, mob_id)
            info["stats"]["speed"] = self._spd
            return info

    def aggroed_mob(spd):
        ph = make(CHAIN)
        mob = Monster(SpeedAssets(spd), {"id": "0100101", "x": 200, "y": 0,
                                         "cy": 0, "rx0": 0, "rx1": 450}, 0, ph)
        mob.take_hit(5, from_x=100)          # 玩家在左 → 反击追击
        mob.update(0.3, player_x=100, player_y=0, mobs=[])   # 吃掉受击硬直
        return mob

    slow, fast = aggroed_mob(-50), aggroed_mob(60)
    for _ in range(12):
        slow.update(0.05, player_x=100, player_y=0, mobs=[])
        fast.update(0.05, player_x=100, player_y=0, mobs=[])
    slow_dist, fast_dist = 200 - slow.x, 200 - fast.x
    assert fast_dist > slow_dist             # 高 speed 属性位移更大
    assert fast_dist > 1.5 * slow_dist


def test_negative_wz_speed_still_roams_visibly():
    """回归：真实 WZ 慢怪（speed=-50）漫游 10 秒仍有可见位移，不原地卡死。"""
    class SlowAssets(FakeAssets):
        def mob_info(self, mob_id):
            info = FakeAssets.mob_info(self, mob_id)
            info["stats"]["speed"] = -50
            return info

    ph = make(CHAIN)
    mob = Monster(SlowAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    assert mob.move_speed >= settings.MOB_SPEED_MIN
    lo = hi = mob.x
    for _ in range(200):                     # 10 秒
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        lo, hi = min(lo, mob.x), max(hi, mob.x)
    assert hi - lo > 50                      # 10 秒内至少逛出 50px


def test_wander_walks_and_pauses():
    """漫游是走走停停：stand 与 move 两种动画都出现，站桩期间位置纹丝不动。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    actions = set()
    stood_still = paused = False
    prev_x, prev_action = mob.x, mob.action
    for _ in range(600):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        actions.add(mob.action)
        if mob.action == "stand" and prev_action == "stand":
            paused = True
            if mob.x != prev_x:
                stood_still = False
            else:
                stood_still = True
        prev_x, prev_action = mob.x, mob.action
    assert {"stand", "move"} <= actions     # 走走停停，不是永动钟摆
    assert paused and stood_still           # 确实存在站桩静止的时段


def test_mob_gives_up_chase_when_player_escapes():
    """追击中玩家跑出仇恨范围：怪立即放弃，回到漫游状态。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 200, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450, "flip": True}, 0, ph)
    mob.take_hit(5, from_x=300)
    mob.update(0.3, player_x=300, player_y=0, mobs=[])   # 熬过受击硬直
    mob.update(0.05, player_x=300, player_y=0, mobs=[])  # 硬直结束后才见追击
    assert mob.state == "chase"
    mob.update(0.05, player_x=100000, player_y=0, mobs=[])  # 玩家已不在范围
    assert mob.state != "chase"
    assert mob.aggro is False


def test_mob_never_chases_unprovoked():
    """玩家站在仇恨范围内不动：未挨打的怪永不进入追击，只按自己的节奏漫游。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    for _ in range(600):
        mob.update(0.05, player_x=300, player_y=0, mobs=[])
        assert mob.state != "chase"


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


# ── WZ info 行为字段：bodyAttack / firstAttack / pushed / maxMP / fs ──

def _stats_assets(**stats):
    """构造把指定 stats 注入 mob_info 的资产桩。"""

    class _Assets(FakeAssets):
        def mob_info(self, mob_id):
            info = FakeAssets.mob_info(self, mob_id)
            info["stats"].update(stats)
            return info

    return _Assets()


def test_body_attack_zero_emits_no_contact_damage():
    """bodyAttack=0 的怪物贴身也不产生接触伤害事件。"""
    ph = make(CHAIN)
    mob = Monster(_stats_assets(bodyAttack=0),
                  {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                   "rx0": 0, "rx1": 450}, 0, ph)
    mobs = []
    for _ in range(20):
        mob.update(0.05, player_x=210, player_y=0, mobs=mobs)
    assert mobs == []


def test_body_attack_defaults_to_true_and_emits_contact():
    """缺 bodyAttack 字段时按原版默认=1：贴身产生接触伤害。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    mobs = []
    for _ in range(20):
        mob.update(0.05, player_x=210, player_y=0, mobs=mobs)
    assert mobs and mobs[0]["type"] == "contact"


def test_first_attack_mob_chases_unprovoked():
    """firstAttack=1 的怪主动先制：玩家进入仇恨范围即追击，无需挨打。"""
    ph = make(CHAIN)
    mob = Monster(_stats_assets(firstAttack=1),
                  {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                   "rx0": 0, "rx1": 450}, 0, ph)
    for _ in range(60):
        mob.update(0.05, player_x=300, player_y=0, mobs=[])
    assert mob.state in ("chase", "attack")
    assert mob.x > 240                       # 主动朝玩家推进


def test_first_attack_mob_ignores_out_of_range_player():
    """先制怪在玩家超出仇恨范围时仍不追击。"""
    ph = make(CHAIN)
    mob = Monster(_stats_assets(firstAttack=1),
                  {"id": "0100101", "x": 10, "y": 0, "cy": 0,
                   "rx0": 0, "rx1": 450}, 0, ph)
    for _ in range(60):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
    assert mob.state != "chase"


def test_pushed_zero_mob_is_not_knocked_back():
    """pushed=0（不可推移）的怪受击不位移。"""
    ph = make(CHAIN)
    mob = Monster(_stats_assets(pushed=0),
                  {"id": "0100101", "x": 200, "y": 0, "cy": 0,
                   "rx0": 0, "rx1": 450}, 0, ph)
    mob.take_hit(5, from_x=300)
    assert mob.x == pytest.approx(200.0)


def test_high_pushed_mob_resists_knockback():
    """pushed 越大击退越短：50000 的怪位移远小于普通怪。"""
    ph = make(CHAIN)
    tough = Monster(_stats_assets(pushed=50000),
                    {"id": "0100101", "x": 200, "y": 0, "cy": 0,
                     "rx0": 0, "rx1": 450}, 0, ph)
    normal = Monster(FakeAssets(),
                     {"id": "0100101", "x": 200, "y": 0, "cy": 0,
                      "rx0": 0, "rx1": 450}, 0, ph)
    tough.take_hit(5, from_x=300)
    normal.take_hit(5, from_x=300)
    assert (200 - tough.x) < (200 - normal.x)
    assert (200 - tough.x) < 1.0


def test_boss_is_never_knocked_back():
    """boss 站桩：受击也不被推开。"""

    class BossAssets(FakeAssets):
        def mob_info(self, mob_id):
            info = FakeAssets.mob_info(self, mob_id)
            info["stats"]["boss"] = True
            info["stats"]["pushed"] = 1
            return info

    ph = make(CHAIN)
    mob = Monster(BossAssets(), {"id": "0100101", "x": 200, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    mob.take_hit(5, from_x=300)
    assert mob.x == pytest.approx(200.0)


def test_status_attack_consumes_mp():
    """异常技能按 mpCon 耗蓝；蓝不足时该技能不再随接触释放。"""
    ph = make(CHAIN)
    mob = Monster(_stats_assets(mp=10),
                  {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                   "rx0": 0, "rx1": 450}, 0, ph)
    mob.status_attacks = [{"kind": "poison", "prob": 100, "duration": 5,
                           "potency": 1, "mp_cost": 3}]
    mob.mp = 10
    mobs = []
    mob.update(0.05, player_x=210, player_y=0, mobs=mobs)
    assert mobs and mobs[0]["status_attacks"]
    assert mob.mp == pytest.approx(7.0)
    mob.attack_cooldown = 0.0
    mob.mp = 0
    mobs2 = []
    mob.update(0.05, player_x=mob.x, player_y=0, mobs=mobs2)
    assert mobs2 and mobs2[0]["status_attacks"] == []


def test_mob_mp_regenerates_over_time():
    """怪物按 mpRecovery 随时间回蓝，且不超过 maxMP。"""
    ph = make(CHAIN)
    mob = Monster(_stats_assets(mp=100, mpRecovery=10),
                  {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                   "rx0": 0, "rx1": 450}, 0, ph)
    mob.mp = 0
    mob.update(1.0, player_x=100000, player_y=0, mobs=[])
    assert mob.mp == pytest.approx(10.0)
    for _ in range(20):
        mob.update(1.0, player_x=100000, player_y=0, mobs=[])
    assert mob.mp == pytest.approx(100.0)


def test_frozen_mob_cannot_move_and_thaws():
    """冰冻：冻结期间不走动，时长耗尽后恢复漫游。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    mob.apply_freeze(2.0)
    start = mob.x
    for _ in range(20):                      # 1 秒，仍在冻结
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
    assert mob.x == pytest.approx(start)
    for _ in range(60):                      # 再 3 秒，已解冻
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
    assert mob.x != pytest.approx(start)


def test_slow_and_freeze_scale_effective_speed():
    """减速按倍率缩放移速，冻结归零；到期后恢复常速。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    base = mob.speed_now()
    mob.apply_slow(0.5, 10.0)
    assert mob.speed_now() == pytest.approx(base * 0.5)
    mob.apply_freeze(5.0)
    assert mob.speed_now() == 0.0
    for _ in range(120):                     # 5 秒后解冻
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
    assert mob.speed_now() == pytest.approx(base * 0.5)


def test_frozen_mob_emits_no_contact_damage():
    """冻结的怪不产生接触伤害。"""
    ph = make(CHAIN)
    mob = Monster(FakeAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                 "rx0": 0, "rx1": 450}, 0, ph)
    mob.apply_freeze(5.0)
    mobs = []
    for _ in range(20):
        mob.update(0.05, player_x=210, player_y=0, mobs=mobs)
    assert mobs == []


def test_flying_mob_speed_follows_wz_fly_speed():
    """仅有 fly 动作的怪，移速取 WZ flySpeed（有符号偏移，同 speed 套路）。"""

    class FlyAssets(FakeAssets):
        def mob_info(self, mob_id):
            info = FakeAssets.mob_info(self, mob_id)
            info["stats"]["flySpeed"] = 100
            return info

        def mob_frames(self, mob_id, action, flip=False):
            return [(self._surf, 100)] if action == "fly" else []

    ph = make(CHAIN)
    mob = Monster(FlyAssets(), {"id": "0100101", "x": 210, "y": 0, "cy": 0,
                                "rx0": 0, "rx1": 450}, 0, ph)
    assert mob.act_walk == "fly" and mob.flying
    expected = settings.MOB_SPEED_BASE + 100 * settings.MOB_SPEED_FACTOR
    assert mob.move_speed == pytest.approx(expected)


def test_flying_mob_blocked_by_wall():
    """飞行怪撞到竖直墙应被挡下折返，而不是穿墙飞过去。"""

    class FlyAssets(FakeAssets):
        def mob_frames(self, mob_id, action, flip=False):
            return [(self._surf, 100)] if action == "fly" else []

    segs = [fh(1, 0, 0, 0, 400, 0),          # 地面
            fh(2, 0, 150, 0, 150, 400)]      # 竖直墙（贯穿怪所在高度）
    ph = make(segs)
    mob = Monster(FlyAssets(), {"id": "0100101", "x": 100, "y": 200, "cy": 200,
                                "rx0": 100, "rx1": 400}, 0, ph)
    hi = mob.x
    for _ in range(300):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        hi = max(hi, mob.x)
    limit = 150 - settings.PLAYER_BODY_HALF_W
    assert hi <= limit + 1.0


def test_flying_mob_flies_sine_wave_along_sloped_ground():
    """飞行怪不吸附脚下地形：贴着斜坡飞时高度绕出生高度做大幅度正弦斜飞。"""

    class FlyAssets(FakeAssets):
        def mob_frames(self, mob_id, action, flip=False):
            return [(self._surf, 100)] if action == "fly" else []

    slope = [fh(1, 0, 0, 0, 200, 100, next=2),
             fh(2, 0, 200, 100, 400, 200, prev=1)]
    ph = make(slope)
    # 出生点落在斜坡上（x=100 处坡面 y=50），若不悬停会被地形带到 y=150+；
    # 端点固定为 400，保证 wandered 方向确定（否则随机折返会让断言不稳定）
    mob = Monster(FlyAssets(), {"id": "0100101", "x": 100, "y": 50, "cy": 50,
                                "rx0": 400, "rx1": 400}, 0, ph)
    assert mob.flying and mob.fh is not None
    hi = mob.x
    lo_cy, hi_cy = mob.cy, mob.cy
    for _ in range(200):
        mob.update(0.05, player_x=100000, player_y=0, mobs=[])
        hi = max(hi, mob.x)
        lo_cy, hi_cy = min(lo_cy, mob.cy), max(hi_cy, mob.cy)
        assert abs(mob.cy - 50) <= settings.MOB_FLY_WAVE_AMPLITUDE + 0.5
    assert hi > 350                          # 在空中确实飞过一段距离
    assert hi_cy - lo_cy > settings.MOB_FLY_WAVE_AMPLITUDE   # 有明显上下起伏
