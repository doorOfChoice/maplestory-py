#!/usr/bin/env python3
"""冒险岛 v113 · pygame 单机游戏入口。

用法（在项目根目录）：
    uv run python -m game.main
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.game import Game  # noqa: E402


def main() -> None:
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
