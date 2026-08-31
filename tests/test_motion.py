"""运动辅助：速度渐近（approach）与跳跃缓冲 / 土狼时间（JumpFeather）。"""

from game.motion import approach, JumpFeather


def test_approach_ramps_up_by_max_delta():
    """approach 朝目标移动最多 max_delta：向大方向每步递增，绝不瞬跳。"""
    assert approach(0.0, 150.0, 26.0) == 26.0
    assert approach(130.0, 150.0, 26.0) == 150.0
    assert approach(150.0, 150.0, 26.0) == 150.0


def test_approach_ramps_down_by_max_delta():
    """approach 朝小方向同样受 max_delta 约束：减速柔化，不骤停。"""
    assert approach(150.0, 0.0, 26.0) == 124.0
    assert approach(10.0, 0.0, 26.0) == 0.0


def test_approach_never_overshoots():
    """approach 越过目标时吸附到目标值，不振荡。"""
    assert approach(140.0, 150.0, 26.0) == 150.0
    assert approach(10.0, 0.0, 26.0) == 0.0


def test_jump_press_buffers():
    """按下跳跃立即进入缓冲窗口，可起跳。"""
    f = JumpFeather()
    f.press()
    assert f.buffered
    assert f.can_jump(True)


def test_buffer_expires_in_air():
    """在空中不点落地则不浪费：缓冲随时间衰减耗尽，不能再起跳。"""
    f = JumpFeather()
    f.press()
    f.tick(0.20, on_ground=False)
    assert not f.buffered
    assert not f.can_jump(False)


def test_coyote_allows_jump_just_after_leaving_ground():
    """离开地面后的土狼窗口内仍可起跳。"""
    f = JumpFeather()
    f.tick(0.016, on_ground=True)   # 站在地面 → 刷新土狼窗口
    f.tick(0.03, on_ground=False)   # 刚离开地面，土狼还在
    f.press()
    assert f.can_jump(False)
    f.consume()
    f.tick(1.0, on_ground=False)    # 窗口耗尽
    assert not f.can_jump(False)


def test_buffer_holds_until_landing():
    """落地前一瞬按跳：缓冲保留，落地那帧接上起跳。"""
    f = JumpFeather()
    f.press()
    f.tick(0.05, on_ground=False)   # 空中，无土狼 → 还不能跳
    assert not f.can_jump(False)
    f.tick(0.03, on_ground=True)    # 落地，缓冲仍在 → 可跳
    assert f.can_jump(True)
    f.consume()
    assert not f.can_jump(True)


def test_consume_clears_both_windows():
    """成功起跳后清空缓冲与土狼，避免一按再跳。"""
    f = JumpFeather()
    f.press()
    f.tick(0.016, on_ground=True)
    f.consume()
    assert not f.buffered
    assert not f.can_jump(True)
