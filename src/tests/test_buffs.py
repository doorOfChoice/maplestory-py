"""Buff 与状态异常：持续时间增益/减益的行为验证（纯数据，无 pygame）。"""
from __future__ import annotations

from game.buffs import BuffList, StatusList


def test_buff_apply_and_mod_sum():
    """上 buff 后对应词条生效，多个 buff 同词条求和。"""
    buffs = BuffList()
    buffs.apply("3101004", "鹰眼", 30.0, {"dex": 10, "crit": 15})
    buffs.apply("3101005", "集中术", 30.0, {"dex": 5})
    assert buffs.mod_sum("dex") == 15
    assert buffs.mod_sum("crit") == 15
    assert buffs.mod_sum("str") == 0


def test_buff_refresh_replaces_duration():
    """重复上同名 buff：刷新持续时间而非叠加数值。"""
    buffs = BuffList()
    buffs.apply("3101004", "鹰眼", 30.0, {"dex": 10})
    buffs.apply("3101004", "鹰眼", 30.0, {"dex": 10})
    assert buffs.mod_sum("dex") == 10
    buffs.tick(25.0)
    assert buffs.mod_sum("dex") == 10
    buffs.tick(10.0)
    assert buffs.mod_sum("dex") == 0


def test_buff_expire_by_tick():
    """时间耗尽自动移除。"""
    buffs = BuffList()
    buffs.apply("x", "测试", 5.0, {"atk": 20})
    buffs.tick(4.0)
    assert buffs.mod_sum("atk") == 20
    buffs.tick(2.0)
    assert buffs.mod_sum("atk") == 0
    assert buffs.active() == []


def test_poison_ticks_damage_by_potency():
    """中毒：每 POISON_TICK 秒按强度扣一次血。"""
    st = StatusList()
    st.apply("poison", 5.0, potency=8)
    total = 0
    for _ in range(20):          # 20 × 0.25s = 5s
        total += st.tick(0.25)
    assert total == 40           # 每秒 8 点 × 5 秒
    assert not st.has("poison")


def test_stun_locks_and_slow_mult():
    """眩晕锁行动；减速返回速度倍率。"""
    st = StatusList()
    assert not st.locked()
    assert st.speed_mult() == 1.0
    st.apply("stun", 2.0)
    st.apply("slow", 2.0)
    assert st.locked()
    assert st.speed_mult() < 1.0
    st.tick(3.0)
    assert not st.locked()
    assert st.speed_mult() == 1.0


def test_status_refresh_takes_max():
    """同种异常重复上：取更长的剩余与更高的强度。"""
    st = StatusList()
    st.apply("poison", 3.0, potency=5)
    st.apply("poison", 1.0, potency=9)
    total = 0
    for _ in range(12):          # 12 × 0.25s = 3s（剩余取 max=3，强度取 max=9）
        total += st.tick(0.25)
    assert total == 27
    assert not st.has("poison")


def test_clear_removes_everything():
    """死亡清场：buff 与异常全部移除。"""
    buffs = BuffList()
    buffs.apply("x", "测试", 30.0, {"dex": 10})
    st = StatusList()
    st.apply("stun", 2.0)
    buffs.clear()
    st.clear()
    assert buffs.mod_sum("dex") == 0
    assert not st.locked()
