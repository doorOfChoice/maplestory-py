"""特效朝向：技能特效需按人物朝向水平镜像，跟随型特效随朝向实时翻转。

Effect.draw 以 origin 对齐锚点，翻转时 origin.x 同步镜像；face_follow 让
通道技持续特效在玩家转身时立刻改朝。
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.render.effects import Effect

pygame.init()


class _Camera:
    """一像素一世界单位的相机桩。"""

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        return (int(x), int(y))


def _two_pixel_frame() -> tuple:
    """2×1 贴图：左红右蓝，便于检出镜像。"""
    surf = pygame.Surface((2, 1), pygame.SRCALPHA)
    surf.set_at((0, 0), (255, 0, 0, 255))
    surf.set_at((1, 0), (0, 0, 255, 255))
    return (surf, (0, 0), 100)


def _draw(canvas: pygame.Surface, **kwargs) -> None:
    # x=1 + 默认居中：2px 贴图正好落在 canvas 的 0/1 两格
    Effect([_two_pixel_frame()], 1, 0, **kwargs).draw(canvas, _Camera())


def test_effect_draws_unflipped_by_default():
    """默认不翻转：贴图保持原样。"""
    canvas = pygame.Surface((2, 1))
    _draw(canvas)
    assert canvas.get_at((0, 0))[:3] == (255, 0, 0)
    assert canvas.get_at((1, 0))[:3] == (0, 0, 255)


def test_effect_flip_mirrors_sprite():
    """flip=True 时水平镜像，红蓝像素左右互换。"""
    canvas = pygame.Surface((2, 1))
    _draw(canvas, flip=True)
    assert canvas.get_at((0, 0))[:3] == (0, 0, 255)
    assert canvas.get_at((1, 0))[:3] == (255, 0, 0)


def test_effect_face_follow_tracks_facing():
    """face_follow：跟随目标的朝向决定是否镜像，转身即翻转。"""
    target = SimpleNamespace(x=0.0, y=0.0, facing_right=False)
    effect = Effect([_two_pixel_frame()], 0, 0, follow=target,
                    face_follow=True)
    effect.update(0.016)
    assert effect.flip is True
    target.facing_right = True
    effect.update(0.016)
    assert effect.flip is False
