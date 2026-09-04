"""任务文本标签渲染：去掉颜色/选项标记、替换名称、处理裸数字与折行。

colors 模式（会话面板用）：保留 #r/#g/#b/#d/#k 颜色码并给实体名自动包色；
split_colors / wrap_segments 负责把带码文本折成 (片段, 颜色) 供渲染。
"""
from __future__ import annotations

from game.core.markup import MARKUP_COLORS, split_colors
from game.render.conv import wrap_segments
from game.systems.quests import render_markup, wrap_lines


class _FakeFont:
    """按字符数计宽的字替身：每字符 7px、高 12px。"""

    def size(self, s: str):
        return (len(s) * 7, 12)


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


# ── colors 模式：保留颜色码 + 实体名自动包色 ──
def test_colors_mode_preserves_manual_color_codes():
    """colors=True 时手写 #r/#k 原样保留，供渲染层分段取色。"""
    out = render_markup("凑齐 #r30 个#k 就交货。", colors=True)
    assert out == "凑齐 #r30 个#k 就交货。"


def test_colors_mode_auto_wraps_entity_names():
    """colors=True 时物品名包 #b、怪物名包 #r、地图名包 #g、NPC 名包 #d。"""
    out = render_markup("#t4000004# 在 #m100000000#",
                        item_name=_item, map_name=lambda _i: "射手村",
                        colors=True)
    assert out == "#b菇菇宝贝伞#k 在 #g射手村#k"


def test_plain_mode_still_strips_everything():
    """默认模式不变：颜色码剥离、名称裸替换（任务日志等纯文本场景）。"""
    out = render_markup("#r#t4000004##k", item_name=_item)
    assert out == "菇菇宝贝伞"


# ── split_colors：带码文本 → (片段, 颜色) ──
def test_split_colors_pairs_tokens_with_segments():
    segs = split_colors("前置#r红色#k回到基色")
    assert segs == [("前置", None), ("红色", MARKUP_COLORS["r"]),
                    ("回到基色", None)]


def test_split_colors_without_tokens_is_single_base_segment():
    assert split_colors("纯文本") == [("纯文本", None)]


# ── wrap_segments：按像素宽折行且颜色随行内片段走 ──
def test_wrap_segments_wraps_and_carries_color():
    lines = wrap_segments("#rabcdefghij", 35, _FakeFont())
    red = MARKUP_COLORS["r"]
    assert lines == [[("abcde", red)], [("fghij", red)]]


def test_wrap_segments_merges_adjacent_same_color():
    lines = wrap_segments("#r甲#k乙", 35, _FakeFont())
    assert lines == [[("甲", MARKUP_COLORS["r"]), ("乙", None)]]
