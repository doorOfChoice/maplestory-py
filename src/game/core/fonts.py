"""CJK 中文字体加载：避免 pygame 默认字体（Font(None)）把汉字渲染成方块。

pygame 的 `pygame.font.Font(None, size)` 只带 ASCII 字形，遇到 CJK 会统一
绘制成 .notdef 矩形（乱码口口口）。字体来源优先级：
1. resources/fonts/ 下的捆绑字体文件（多字重时优先 Regular）；
2. 按平台常见中文字体名匹配的系统字体；
3. 全部落空时回退 Font(None)（保持可用，不抛异常）。

捆绑字体最高优先（含像素字体，见 _is_pixel_font）：像素/位图字体经 _SharpFont
包装后强制关抗锯齿，否则自由字体会在点阵边缘补灰色像素、失去原版锐利感。
另提供 render_text：对反复出现的文本做 LRU 缓存（HUD/伤害数字每帧渲染，
字体渲染很贵，缓存 Surface 可消除帧时间尖峰）。
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Optional, Tuple

import pygame

from game import settings

# 候选顺序：macOS 优先（项目运行环境），再广覆盖 Windows / Linux 常见中文字体
_FONT_CANDIDATES = (
    "hiraginosansgb", "pingfang", "stheitilight", "songti",
    "arialunicode", "microsoftyahei", "simhei", "simsun",
    "notosanscjk", "notosanscjksc",
)

# 按字号缓存字体对象，避免每帧反复 match_font 搜索系统字体。
_FONT_CACHE: dict = {}

# 文本渲染 LRU 缓存：键 (id(font), text, color, antialias)。
# 字体对象经 _FONT_CACHE 常驻，id 稳定；超限时淘汰最久未用。
_TEXT_CACHE: "OrderedDict[Tuple, pygame.Surface]" = OrderedDict()
_TEXT_CACHE_MAX = 512


def has_cjk_font() -> bool:
    """是否有可渲染中文的字体来源（捆绑字体或系统候选，供测试跳过用）。"""
    return find_bundled_font() is not None or any(
        pygame.font.match_font(name) for name in _FONT_CANDIDATES)


_FONT_SUFFIXES = (".otf", ".ttf", ".ttc")
# 字重关键词按"长词优先"匹配，避免 semibold 被 bold、extralight 被 light 抢先命中
_WEIGHT_KEYWORDS = ("extralight", "semibold", "medium", "bold", "light",
                    "regular", "heavy")
# 宋体横画极细，小字号下几乎全是抗锯齿灰边（发虚）；UI 小字优先挑重字重
_SMALL_UI_WEIGHTS = ("semibold", "medium", "bold")
# 达到此字号的标题才适合用 Regular 宋体（笔画已够粗，衬线细节成为优点）
_TITLE_SERIF_MIN_SIZE = 20


def _weight_of(path: Path) -> str:
    stem = path.stem.lower()
    for kw in _WEIGHT_KEYWORDS:
        if kw in stem:
            return kw
    return ""


def find_bundled_font(font_dir: Optional[Path] = None,
                      weights: Tuple[str, ...] = ()) -> Optional[Path]:
    """在捆绑字体目录（递归）中挑一个字体文件。

    不指定 weights 时优先 Regular、否则任取一个；指定 weights（小写关键词，
    按优先级）时只做精确字重匹配，全部落空返回 None 而不回退细体。
    """
    root = font_dir if font_dir is not None else settings.FONT_DIR
    if not root.is_dir():
        return None
    files = sorted(p for p in root.rglob("*") if p.suffix.lower() in _FONT_SUFFIXES)
    if not files:
        return None
    if weights:
        for w in weights:
            for p in files:
                if _weight_of(p) == w:
                    return p
        return None
    for p in files:
        if _weight_of(p) == "regular":
            return p
    return files[0]


# 像素/位图字体识别：命中这些词的文件名视为点阵字体，关抗锯齿渲染
_PIXEL_FONT_HINTS = ("pixel", "bitmap", "dot", "8px", "10px", "12px", "16px")


def _is_pixel_font(path: str) -> bool:
    """文件名含 pixel / bitmap / 像素尺寸等词 → 视为点阵字体。"""
    stem = Path(path).stem.lower()
    return any(hint in stem for hint in _PIXEL_FONT_HINTS)


class _SharpFont(pygame.font.Font):
    """像素/位图字体包装：强制关抗锯齿，保持点阵边缘锐利。

    pygame 的 render(antialias) 默认开抗锯齿，会在字形边缘补灰色像素，
    点阵字体经此处理会发虚；这里忽略调用方传入的 antialias 一律按 False 渲染。
    """

    def render(self, text, antialias: bool = True,
               color=(255, 255, 255), background=None) -> pygame.Surface:
        return super().render(text, False, color, background)


def _open_font(path: str, size: int) -> pygame.font.Font:
    """按路径加载字体：点阵字体套 _SharpFont，否则用原生 Font。"""
    cls = _SharpFont if _is_pixel_font(path) else pygame.font.Font
    return cls(path, size)


def _candidate_paths(size: int, prefer: Tuple[str, ...] = ()) -> list:
    """按字号给出字体文件候选（依优先级）：显式指定 > 捆绑字体 > 系统字体。

    捆绑字体（现为像素字体）对任何字号都最高优先；多字重时小字号先挑重字重。
    """
    paths = [path for name in prefer if (path := pygame.font.match_font(name))]
    regular = find_bundled_font()
    if size < _TITLE_SERIF_MIN_SIZE:
        heavy = find_bundled_font(weights=_SMALL_UI_WEIGHTS)
        if heavy is not None:
            paths.append(str(heavy))
    if regular is not None:
        paths.append(str(regular))
    paths += [path for name in _FONT_CANDIDATES
              if (path := pygame.font.match_font(name))]
    return paths


def load_cjk_font(size: int, prefer: Tuple[str, ...] = ()) -> pygame.font.Font:
    """返回一个可渲染中文的 pygame 字体：显式指定 > 捆绑字体 > 系统字体 > Font(None)。

    捆绑字体优先；像素字体（resources/fonts 下的点阵字）套 _SharpFont 强制关
    抗锯齿。prefer 传入字体名元组时最先尝试（如 ("stheitimedium",) 强制黑体）。
    """
    hit = _FONT_CACHE.get((size, prefer))
    if hit is not None:
        return hit
    for path in _candidate_paths(size, prefer):
        try:
            font = _open_font(path, size)
            _FONT_CACHE[(size, prefer)] = font
            return font
        except Exception:
            continue
    font = pygame.font.Font(None, size)
    _FONT_CACHE[(size, prefer)] = font
    return font


def render_text(font: pygame.font.Font, text: str, color,
                antialias: bool = True) -> pygame.Surface:
    """缓存渲染文本（LRU），供每帧重复渲染的 HUD / 伤害数字使用。

    文本不变时命中缓存直接返回 Surface，避免每帧调用 font.render。
    """
    key = (id(font), text, color, antialias)
    hit = _TEXT_CACHE.get(key)
    if hit is not None:
        _TEXT_CACHE.move_to_end(key)
        return hit
    surf = font.render(text, antialias, color)
    _TEXT_CACHE[key] = surf
    if len(_TEXT_CACHE) > _TEXT_CACHE_MAX:
        _TEXT_CACHE.popitem(last=False)
    return surf
