"""角色 navel 锚点必须与「实际渲染的姿态」一致。

compose_animation 会先用 detect_pose 把不支持的姿态回退（弓的 alert2 → stand1）；
character_navel_px 若仍按原始 alert2 计算，帧画 stand1、锚点算 alert2，玩家精灵
就会在召唤施法动作期间整体下移（本测试复现并锁定该契约）。
"""

from __future__ import annotations

from types import SimpleNamespace

from game.render.assets import Assets

STANCE_TOP = -46      # stand1 姿态下世界原点相对 bbox 顶部的偏移
ALERT_TOP = -19       # alert2（链接节点被丢弃，只剩头/发/脸）的偏移


def make_renderer() -> SimpleNamespace:
    """最小字符渲染器桩：不支持 alert2，回退 stand1；两姿态给不同 bbox。"""

    class _R:
        def __init__(self) -> None:
            self.posed = []

        def detect_pose(self, equips, pose):
            return "stand1" if pose == "alert2" else pose

        def _cap_hair_filter(self, equips):
            return False, frozenset(), frozenset()

        def pose_frame_delays(self, pose, body_id):
            return [100]

        def _build_placements(self, equips, pose, *args, **kwargs):
            self.posed.append(pose)
            top = STANCE_TOP if pose == "stand1" else ALERT_TOP
            part = SimpleNamespace(
                top_left=(0, top), width_override=None, height_override=None,
                pixel_canvas=SimpleNamespace(width=30, height=60))
            return [part], {}

    return _R()


def test_navel_uses_pose_fallback_matching_rendered_frames():
    """请求 alert2（武器不支持）时，navel 必须按回退后的 stand1 计算。"""
    renderer = make_renderer()
    stub = SimpleNamespace(char_renderer=renderer)
    assert Assets.character_navel_px(stub, ["01452002"], "alert2", False) \
        == (0, -STANCE_TOP)
    assert renderer.posed == ["stand1"]
