"""开屏动画渲染：纯 pygame 绘制，不依赖 WZ / 显示，可在无头环境验证。"""
import pygame

from game.splash import Splash

pygame.font.init()


def _surface():
    return pygame.Surface((960, 540))


def test_draw_updates_pixels():
    """draw 会往画布写出内容（非全透明）。"""
    s = Splash(960, 540)
    s.update(0.1)
    canvas = _surface()
    s.draw(canvas, progress=0.0, status="正在进入冒险岛")
    data = pygame.image.tostring(canvas, "RGBA")
    assert any(b != 0 for b in data[3::4])   # alpha 通道有非 0


def test_progress_bar_grows_with_progress():
    """进度条填充宽度随 progress 单调增加。"""
    s = Splash(960, 540)
    s.update(0.1)

    def fill_width(p):
        canvas = _surface()
        s.draw(canvas, progress=p, status="")
        # 统计进度条填充色（_BAR_TRACK）像素数，近似条宽
        data = pygame.image.tostring(canvas, "RGB")
        w, h = canvas.get_size()
        row = 4 * h // 5
        base = row * w * 3
        track = (200, 214, 235)   # _BAR_TRACK
        count = 0
        for x in range(0, w, 4):
            r, g, b = data[base + x*3:base + x*3 + 3]
            if (r, g, b) == track:
                count += 1
        return count

    low = fill_width(0.1)
    high = fill_width(0.9)
    assert high > low
