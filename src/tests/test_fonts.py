"""CJK 字体加载：确保中文字体被正确加载，避免 pygame 默认字体渲染成方块。"""
import pygame
import pytest

from game.fonts import has_cjk_font, load_cjk_font

pygame.font.init()

pytestmark = pytest.mark.skipif(not has_cjk_font(),
                                reason="无系统 CJK 字体")


def _glyph_px(font, ch: str) -> bytes:
    img = font.render(ch, True, (255, 255, 255))
    return pygame.image.tostring(img, "RGBA")


def test_font_matches_a_system_cjk_font():
    """load_cjk_font 应命中系统中文字体（非 pygame 默认 Font(None)）。"""
    font = load_cjk_font(24)
    assert font.get_height() > 0


def test_chinese_glyphs_render_distinct_shapes():
    """不同汉字应渲染成不同形状——若不加载 CJK 字体会全是同一方块。"""
    font = load_cjk_font(24)
    assert _glyph_px(font, "中") != _glyph_px(font, "口")
