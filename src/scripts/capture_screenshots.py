#!/usr/bin/env python3
"""README 遊戲截圖產生器。

無頭（SDL dummy）啟動遊戲，直接驅動主循環逐幀更新，於各場景截取 canvas：
welcome / gameplay / inventory / skills / quests / overview → screenshots/。

不會讀寫真實存檔（SAVE_FILE 重導向到 temp 目錄），也不播放聲音。

用法（專案根目錄）：
    uv run python src/scripts/capture_screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame

from game import settings
from game.systems.inventory import make_item

DT = 1.0 / 60.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "screenshots"


def build_game():
    from game.game import Game
    # 存檔重導向到不存在的 temp 路徑 → 強制新遊戲（歡迎對話）且保護本機存檔
    settings.SAVE_FILE = Path(tempfile.mkdtemp(prefix="ms_shot_")) / "save.json"
    return Game()


def frames(game, n: int, **keys) -> None:
    """固定步長推進 n 幀，可同時覆蓋方向/攻擊等按鍵狀態。"""
    for k, v in keys.items():
        setattr(game.keys, k, v)
    for _ in range(n):
        game._update(DT)
        game._draw()


def shot(game, name: str) -> None:
    path = OUT_DIR / f"{name}.png"
    pygame.image.save(game.canvas, str(path))
    print(f"  ✓ {path.relative_to(OUT_DIR.parent)}")


def wander_for_opening(game, max_frames: int = 900) -> None:
    """向右走動並持續揮劍，直到出現傷害數字再補幾幀定格。"""
    for i in range(max_frames):
        game.keys.right = True
        game.keys.attack = (i % 30) < 20
        if not game.player.attacking and game.keys.attack:
            game.player.start_attack()
        game._update(DT)
        game._draw()
        if game.combat.numbers and i > 60:
            break
    game.keys.right = False
    game.keys.attack = False


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    game = build_game()

    # ── 1. 歡迎畫面：開場對話 + HUD ────────────────────────────────
    frames(game, 20)
    shot(game, "welcome")

    # ── 2. 戰鬥實機：走位揮砍，抓有傷害數字的一幀 ─────────────────
    game.ui.hide_dialog()
    game._cast_skill(1)              # 先施放一次技能，讓特效入鏡
    wander_for_opening(game)
    frames(game, 3)
    shot(game, "gameplay")

    # ── 3. 道具欄：補一些金幣/材料後開啟 ──────────────────────────
    game.combat.meso = 1520
    frames(game, 5)
    game.panels.toggle_inventory()
    frames(game, 5)
    shot(game, "inventory")
    game.panels.toggle_inventory()

    # ── 4. 技能欄：升級學會兩個技能後開啟 ─────────────────────────
    game.player.level = 10
    game.player.skills.gain_sp(8)
    game.player.skills.learn_or_upgrade("1001005", game.player.level)
    for _ in range(2):
        game.player.skills.learn_or_upgrade("1001004", game.player.level)
    frames(game, 3)
    game.panels.toggle_skill()
    frames(game, 5)
    shot(game, "skills")
    game.panels.toggle_skill()

    # ── 5. 任務日誌：接取啟用任務並填入部分進度後開啟 ─────────────
    quests = game.player.quests
    for qid in list(game.quest_defs):
        quests.accept(qid, game.player)
    for qid in quests.accepted_order:
        d = quests.defs.get(qid)
        if d is None:
            continue
        rec = quests.kills.setdefault(qid, {})
        for mid, need in d.kills:
            rec[mid] = max(need - 3, 0)
        for iid, need in d.end_items:
            have = max(need - 4, 1)
            key = f"{int(iid):08d}"
            item = game.player.inventory.etcs.get(key)
            if item is None and have > 0:
                game.player.inventory.add(
                    make_item(key, game.assets, have))
    if not quests.accepted_order:
        print("  ! 無可接取任務（等級/職業限制），任務日誌將為空")
    frames(game, 3)
    game.panels.toggle_quest_log()
    frames(game, 5)
    shot(game, "quests")

    # ── 6. 全貌：關閉面板後的完整遊戲畫面 ─────────────────────────
    game.panels.toggle_quest_log()
    game.ui.hide_dialog()
    game.ui.hide_quest()
    game.player.invuln_timer = 0.0
    game.player.hurt_timer = 0.0
    frames(game, 40)
    shot(game, "overview")

    game.assets.close()
    pygame.quit()
    print(f"完成：{OUT_DIR}")


if __name__ == "__main__":
    main()
