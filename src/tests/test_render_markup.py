"""任务文本标签渲染：去掉颜色/选项标记、替换名称、处理裸数字与折行。

colors 模式（会话面板用）：保留 #r/#g/#b/#d/#k 颜色码并给实体名自动包色；
split_colors / wrap_segments 负责把带码文本折成 (片段, 颜色) 供渲染。
"""
from __future__ import annotations

from game.core.markup import IconSeg, MARKUP_COLORS, TextSeg, split_colors
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


def test_emphasis_codes_stripped_in_plain_mode():
    """#e 强调 / #n 恢复码在纯文本模式下整体移除。"""
    out = render_markup("#e重要事项#n，请确认。")
    assert out == "重要事项，请确认。"


def test_split_colors_handles_emphasis_and_normal():
    """split_colors：#e 着强调色（橙），#n 恢复基色。"""
    segs = split_colors("前置#e强调#n结尾")
    assert segs == [("前置", None), ("强调", MARKUP_COLORS["e"]),
                    ("结尾", None)]


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
    assert lines == [[TextSeg("abcde", red)], [TextSeg("fghij", red)]]


def test_wrap_segments_merges_adjacent_same_color():
    lines = wrap_segments("#r甲#k乙", 35, _FakeFont())
    assert lines == [[TextSeg("甲", MARKUP_COLORS["r"]), TextSeg("乙")]]


def test_wrap_segments_emits_icon_segment():
    """传入 icon_width 时，#c<id># 产出独立的图标片段，位置与原文一致。"""
    lines = wrap_segments("交给#c1002000#希娜", 200, _FakeFont(),
                          icon_width=lambda item_id: 24)
    assert lines == [[TextSeg("交给"), IconSeg(1002000), TextSeg("希娜")]]


def test_wrap_segments_icon_keeps_surrounding_colors():
    """图标段本身不带颜色；色码作用域跨过图标继续生效，#k 后回基色。"""
    lines = wrap_segments("#r红字#c100#仍红#b蓝字#k黑字", 200, _FakeFont(),
                          icon_width=lambda item_id: 24)
    red, blue = MARKUP_COLORS["r"], MARKUP_COLORS["b"]
    assert lines == [[TextSeg("红字", red), IconSeg(100), TextSeg("仍红", red),
                      TextSeg("蓝字", blue), TextSeg("黑字")]]


def test_wrap_segments_counts_icon_width_in_wrapping():
    """折行按图标实际宽度计量：装不下的图标独占一行，文字顺延。"""
    # _FakeFont 每字符 7px；图标 20px；行宽 20 → a(7)+icon(20) 放不下
    lines = wrap_segments("a#c1#b", 20, _FakeFont(), icon_width=lambda i: 20)
    assert lines == [[TextSeg("a")], [IconSeg(1)], [TextSeg("b")]]


def test_wrap_segments_splits_on_newline():
    """文本内 \\n 强制分行（与按宽折行共存，空行保留）。"""
    lines = wrap_segments("甲\n\n乙丙", 200, _FakeFont())
    assert lines == [[TextSeg("甲")], [], [TextSeg("乙丙")]]


# ── resolve_item_icons：图标码可用性预解析（会话面板/任务窗共用）──────
def test_resolve_item_icons_falls_back_to_name():
    """能出图的 #c 码原样保留；素材缺失的码回退为物品名（名也缺则留 #id）。"""
    from game.render.conv import resolve_item_icons
    out = resolve_item_icons("交#c100#与#c200#",
                             item_icon=lambda iid: object() if iid == "100" else None,
                             item_name=lambda iid: {200: "木偶心"}.get(int(iid)))
    assert out == "交#c100#与木偶心"


# ── 富文本基色：会话面板与任务窗共享单源 ─────────────────────────────
def test_rich_text_base_color_single_source():
    """任务窗详情正文与会话面板正文的无色文本共用同一基色。"""
    from game.render import conv
    from game.render.windows import questlog
    assert conv.DLG_TEXT_BASE == (60, 52, 44)
    assert questlog.DLG_TEXT_BASE == conv.DLG_TEXT_BASE


# ── split_item_icons：#c<id># 内联物品码切段 ──
def test_split_item_icons_basic():
    """文本按 #c<id># 切成 文字/图标 段序列，码本体不再以原文出现。"""
    from game.systems.quests import split_item_icons
    assert split_item_icons("交给#c1002000#希娜") == [
        ("t", "交给"), ("i", 1002000), ("t", "希娜")]


def test_split_item_icons_plain_text_is_single_segment():
    from game.systems.quests import split_item_icons
    assert split_item_icons("纯文本") == [("t", "纯文本")]
    assert split_item_icons("") == []
