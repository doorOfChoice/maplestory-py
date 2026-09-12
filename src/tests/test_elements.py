"""属性克制：WZ elemAttr 解析与伤害倍率（纯函数 seam）。"""

from game.core.elements import (IMMUNE, NEUTRAL, STRONG, WEAK,
                                element_multiplier, parse_elem_attr)


def test_parse_single_and_multiple():
    assert parse_elem_attr("F3") == {"f": 3}
    assert parse_elem_attr("I2F3") == {"i": 2, "f": 3}
    assert parse_elem_attr("L2I3") == {"l": 2, "i": 3}


def test_parse_ignores_empty_and_junk():
    assert parse_elem_attr(None) == {}
    assert parse_elem_attr("") == {}


def test_weak_strong_immune_neutral():
    mob = parse_elem_attr("F3I2H1")
    assert element_multiplier(mob, "f") == WEAK
    assert element_multiplier(mob, "i") == STRONG
    assert element_multiplier(mob, "h") == IMMUNE
    assert element_multiplier(mob, "l") == NEUTRAL


def test_case_insensitive_and_no_element():
    assert element_multiplier(parse_elem_attr("F3"), "F") == WEAK
    assert element_multiplier(parse_elem_attr("F3"), "") == NEUTRAL
