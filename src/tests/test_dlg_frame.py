"""UtilDlgEx 窗体与状态栏取高的单源行为：会话面板 / UI 回退窗共用同一实现。"""

from __future__ import annotations

import pygame

pygame.init()

from game.render import conv  # noqa: E402


class _Assets:
    """按路径供给定色图块的假资产。"""

    def __init__(self, images: dict) -> None:
        self._images = images

    def ui_surface(self, img: str, path: str):
        surf = self._images.get(path)
        return (surf,) if surf is not None else None


def _frame_assets(w=529, top_h=28, tile_h=30, bot_h=58, bar=None):
    images = {"UtilDlgEx/it": pygame.Surface((w, top_h)),
              "UtilDlgEx/ic": pygame.Surface((w, tile_h)),
              "UtilDlgEx/is": pygame.Surface((w, bot_h))}
    for key in ("UtilDlgEx/it", "UtilDlgEx/ic", "UtilDlgEx/is"):
        images[key].fill((255, 0, 255, 255))
    if bar is not None:
        images["base/backgrnd"] = pygame.Surface((600, bar))
    return _Assets(images)


def test_status_bar_height_prefers_asset():
    """素材在场时状态栏高取实际图高。"""
    assert conv.status_bar_height(_frame_assets(bar=40)) == 40


def test_status_bar_height_fallback_is_single_constant():
    """素材缺失回退到单源常量，值即历史上的魔数 71。"""
    assert conv.status_bar_height(_Assets({})) == conv.STATUS_BAR_FALLBACK_H
    assert conv.STATUS_BAR_FALLBACK_H == 71


def test_draw_dlg_frame_blits_top_tile_and_bottom():
    """窗体 = 顶 it + 平铺 ic（裁到正文高）+ 底 is 贴正文底部。"""
    surface = pygame.Surface((600, 400), pygame.SRCALPHA)
    conv.draw_dlg_frame(surface, _frame_assets(), 10, 20, 529, 100)
    magenta = (255, 0, 255, 255)
    assert surface.get_at((15, 25)) == magenta              # 顶栏内
    assert surface.get_at((15, 20 + 28 + 50)) == magenta    # 平铺中段
    assert surface.get_at((15, 20 + 28 + 100 + 10)) == magenta  # 底栏（正文高之后）
    assert surface.get_at((15, 399)).a == 0                 # 框外不染色


def test_ui_and_conv_share_frame_helpers():
    """UI 的取图/取高方法与会话面板均转发到同一单源（同假资产得出同值）。"""
    assets = _frame_assets(bar=44)
    ui_like = conv.ConvPanel(assets)
    assert ui_like._status_bar_h() == conv.status_bar_height(assets) == 44
