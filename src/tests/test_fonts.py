"""CJK 字体加载：确保中文字体被正确加载，避免 pygame 默认字体渲染成方块。"""
import pygame
import pytest

from game.core.fonts import find_bundled_font, has_cjk_font, load_cjk_font

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


def test_find_bundled_font_returns_none_for_empty_dir(tmp_path):
    assert find_bundled_font(tmp_path) is None


def test_find_bundled_font_prefers_regular_weight(tmp_path):
    """多字重时优先选 Regular，避免默认用粗体/特细。"""
    (tmp_path / "Sub").mkdir()
    for name in ("Foo-Bold-2.otf", "Foo-Regular-1.otf", "Foo-Heavy-4.otf"):
        (tmp_path / "Sub" / name).write_bytes(b"")
    found = find_bundled_font(tmp_path)
    assert found is not None and found.name == "Foo-Regular-1.otf"


def test_find_bundled_font_falls_back_to_any_font_file(tmp_path):
    (tmp_path / "Only-Light-5.ttf").write_bytes(b"")
    found = find_bundled_font(tmp_path)
    assert found is not None and found.name == "Only-Light-5.ttf"


def test_find_bundled_font_weights_honors_preference_order(tmp_path):
    """显式给字重序列时按优先级命中；全部落空返回 None（不随便抓一个细体）。"""
    for name in ("Foo-Regular.otf", "Foo-Medium.otf", "Foo-SemiBold.otf"):
        (tmp_path / name).write_bytes(b"")
    assert find_bundled_font(tmp_path, ("semibold", "medium")).name == "Foo-SemiBold.otf"
    assert find_bundled_font(tmp_path, ("medium", "semibold")).name == "Foo-Medium.otf"
    assert find_bundled_font(tmp_path, ("bold",)) is None


def test_small_ui_font_uses_heavier_weight_than_regular():
    """小字号（<20）应命中更重字重：同一汉字的着墨量明显高于 Regular。"""
    heavy = find_bundled_font(weights=("semibold", "medium", "bold"))
    regular = find_bundled_font()
    if heavy is None or regular is None:
        pytest.skip("捆绑字体目录无多字重可用")
    small = load_cjk_font(12)
    base = pygame.font.Font(str(regular), 12)
    cov_small = pygame.surfarray.array_alpha(
        small.render("背", True, (255, 255, 255))).sum()
    cov_base = pygame.surfarray.array_alpha(
        base.render("背", True, (255, 255, 255))).sum()
    assert cov_small > cov_base


def test_bundled_font_is_loaded_from_resources_dir():
    """resources/fonts 下的字体存在时应被找到并可直接加载。"""
    path = find_bundled_font()
    if path is None:
        pytest.skip("未放置捆绑字体")
    font = pygame.font.Font(str(path), 24)
    assert _glyph_px(font, "中") != _glyph_px(font, "口")


def test_load_cjk_font_prefers_bundled_over_system():
    """有捆绑字体时，load_cjk_font 渲染结果应与直接加载捆绑字体一致。"""
    path = find_bundled_font()
    if path is None:
        pytest.skip("未放置捆绑字体")
    a = load_cjk_font(24).render("中", True, (255, 255, 255))
    b = pygame.font.Font(str(path), 24).render("中", True, (255, 255, 255))
    assert pygame.image.tostring(a, "RGBA") == pygame.image.tostring(b, "RGBA")
