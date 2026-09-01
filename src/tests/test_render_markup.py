"""任务文本标签渲染：去掉颜色/选项标记、替换名称、处理裸数字与折行。"""
from __future__ import annotations

from game.systems.quests import render_markup, wrap_lines


def _npc(nid):
    return {7000001: "皮亚鲁斯"}.get(nid, None)


def _item(nid):
    return {4000004: "菇菇宝贝伞"}.get(nid, None)


def test_letter_prefix_marker_replaces_name():
    """#p#/#t# 等字母前缀标记被替换为名称。"""
    out = render_markup("去 #t4000004# 找 #p7000001#", item_name=_item, npc_name=_npc)
    assert out == "去 菇菇宝贝伞 找 皮亚鲁斯"


def test_color_and_choice_markers_are_stripped():
    """颜色标记与 #L# 选项标记被整体移除。"""
    out = render_markup("#b#蓝色#k#\n#L0#选项A#l")
    assert "#b" not in out and "#k" not in out and "#L" not in out
    assert "蓝色" in out and "选项A" in out


def test_bare_numeric_marker_falls_back_to_number():
    """无字母前缀的 #数字# 用物品名解析，解析不到则保留数字。"""
    out = render_markup("物品 #4000004# 未知 #9999999#", item_name=_item)
    assert "菇菇宝贝伞" in out
    assert "#9999999#" not in out
    assert "9999999" in out


def test_wrap_lines_splits_on_newline_and_width():
    """wrap_lines 兼顾 \\n 分段与按宽度折行。"""

    def _wrap(seg, _w, _f):
        if len(seg) <= 5:
            return [seg]
        return [seg[:5], seg[5:]]

    out = wrap_lines("短行\n这一行很长很长很  长", 90, None, _wrap)
    assert out == ["短行", "这一行很长", "很长很  长"]
