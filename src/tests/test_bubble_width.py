"""气泡宽度贴合文本内容：短句不撑满屏，长文封顶且不超屏。"""
from __future__ import annotations

from game.render.ui import fit_bubble_width


def test_short_text_uses_min_width():
    assert fit_bubble_width(120, 960) == 200


def test_width_hugs_content_plus_padding():
    assert fit_bubble_width(300, 960) == 336


def test_long_text_capped_at_max_width():
    assert fit_bubble_width(4000, 960) == 480


def test_never_wider_than_screen():
    assert fit_bubble_width(4000, 400) == 376
