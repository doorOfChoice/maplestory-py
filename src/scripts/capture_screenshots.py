#!/usr/bin/env python3
"""README 截图生成器。

无头（SDL dummy）启动游戏，直接驱动主循环逐帧更新，于各场景截取 canvas：
welcome / gameplay / dialogue / inventory / skills / quests / overview → screenshots/。

不会读写真实存档（SAVE_FILE 重定向到 temp 目录），也不播放声音。

用法（项目根目录）：
    uv run python src/scripts/capture_screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pygame

from game import settings
from game.systems.inventory import make_item
from game.render.windows.inventory import toggle_inventory_pair

DT = 1.0 / 60.0
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "screenshots"


def build_game():
    from game.game import Game
    # 存档重定向到不存在的 temp 路径 → 强制新游戏（欢迎对话）且保护本地存档
    settings.SAVE_FILE = Path(tempfile.mkdtemp(prefix="ms_shot_")) / "save.json"
    game = Game()
    # 世界在后台线程构建：等就绪后手动补一次 bootstrap（替代 run() 主循环）
    while not game._world_ready:
        time.sleep(0.05)
    if not hasattr(game, "ctx"):
        raise RuntimeError("世界构建失败，无法截图")
    game._finish_bootstrap()
    return game


def frames(game, n: int, **keys) -> None:
    """固定步长推进 n 帧，可同时覆盖方向/攻击等按键状态。"""
    for k, v in keys.items():
        setattr(game.keys, k, v)
    for _ in range(n):
        game._update(DT)
        game._draw()


def shot(game, name: str) -> None:
    path = OUT_DIR / f"{name}.png"
    pygame.image.save(game.canvas, str(path))
    print(f"  ✓ {path.relative_to(OUT_DIR.parent)}")


def fight_near_mob(game, max_frames: int = 600) -> None:
    """把玩家挪到最近怪物身旁持续挥砍，直到出现伤害数字定格。"""
    world = game.ctx.world
    player = world.player
    mobs = [m for m in world.monsters if not m.dead]
    if mobs:
        mob = min(mobs, key=lambda m: abs(m.x - player.x))
        player.x = mob.x - 50.0
        player.y = mob.cy - settings.FEET_OFFSET
        player.vy = 0.0
    combat = world.combat
    for i in range(max_frames):
        game.keys.attack = (i % 30) < 20
        if not player.attacking and game.keys.attack:
            player.start_attack()
        game._update(DT)
        game._draw()
        if combat.numbers and i > 30:
            break
    game.keys.attack = False


def talk_to_npc(game) -> bool:
    """把玩家挪到 NPC 身旁再点开对话：优先有 talk() 脚本的（内容更丰富）。

    对话层会按玩家距离自动收起（TALK_RANGE），所以必须先传送到位再 talk。
    """
    player = game.ctx.world.player
    npcs = game.ctx.world.npcs
    script_dir = settings.RESOURCE_DIR / "content" / "npc"
    scripted = [n for n in npcs if (script_dir / f"{n.npc_id}.lua").exists()]
    for npc in (scripted or npcs):
        rect = npc.rect()
        player.x = float(rect.centerx + 50)
        player.y = float(rect.bottom - settings.FEET_OFFSET)
        player.vy = 0.0
        frames(game, 5)
        if game._dialogue.try_talk_at(rect.centerx, rect.centery):
            return True
    return False


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    game = build_game()
    world = game.ctx.world

    # ── 1. 欢迎画面：开场对话 + HUD ────────────────────────────────
    frames(game, 60)                 # 等黑场淡入走完
    shot(game, "welcome")

    # ── 2. 战斗实机：贴住怪物挥砍，抓有伤害数字的一帧 ──────────────
    game.ctx.ui.hide_dialog()
    frames(game, 200)                # 等开场地图横幅散去再开打
    fight_near_mob(game)
    frames(game, 3)
    shot(game, "gameplay")

    # ── 3. NPC 对话：点开一个有脚本的会话（分段着色 + 蓝字列表）────
    # 回出生点并静置：甩开怪物击退/掉线重进图触发的地图横幅与黑场
    game.respawn()
    frames(game, 240)
    game.ctx.ui.hide_dialog()
    if talk_to_npc(game):
        frames(game, 5)
        shot(game, "dialogue")
        game._dialogue.close_all()
    else:
        print("  ! 当前地图无 NPC，跳过对话截图")

    # ── 4. 道具栏：补一些金币/材料后开启（含纸娃娃）────────────────
    world.combat.meso = 1520
    frames(game, 5)
    toggle_inventory_pair(game.ctx.windows)
    frames(game, 5)
    shot(game, "inventory")
    toggle_inventory_pair(game.ctx.windows)

    # ── 5. 任务日志：接取启用任务并填入部分进度后开启 ──────────────
    quests = world.player.quests
    for qid in list(game.quest_defs):
        quests.accept(qid, world.player)
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
            item = world.player.inventory.etcs.get(key)
            if item is None and have > 0:
                world.player.inventory.add(make_item(key, game.assets, have))
    if not quests.accepted_order:
        print("  ! 无可接取任务（等级/职业限制），任务日志将为空")
    frames(game, 3)
    game.ctx.windows.get("questlog").toggle()
    frames(game, 5)
    shot(game, "quests")
    game.ctx.windows.get("questlog").toggle()

    # ── 6. 技能栏：转职弓箭手并学会两个技能后开启 ──────────────────
    world.player.level = 10
    world.player.advance_to(3000, game.assets)
    world.player.skills.gain_sp_for_level(world.player.level, 8)
    learned = 0
    for sid in world.player.skills.learnable():
        if world.player.skills.learn(sid, world.player.level):
            learned += 1
            if learned == 2:
                break
    frames(game, 3)
    game.ctx.windows.get("skill").toggle()
    frames(game, 5)
    shot(game, "skills")
    game.ctx.windows.get("skill").toggle()

    # ── 7. 全貌：关闭所有窗口后的完整游戏画面（HUD + 小地图）───────
    game.ctx.ui.hide_dialog()
    game.ctx.ui.conv.hide()
    world.player.invuln_timer = 0.0
    world.player.hurt_timer = 0.0
    frames(game, 40)
    shot(game, "overview")

    game.assets.close()
    pygame.quit()
    print(f"完成：{OUT_DIR}")


if __name__ == "__main__":
    main()
