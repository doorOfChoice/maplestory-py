"""游戏主场景：装配依赖 → 生成 World（单图场景）→ 主循环（60fps 固定步长）。

流程：加载资源 → World 构建玩家 / 怪物 / NPC → 主循环（输入 → 更新 → 绘制）
出生 / 死亡重生：出生在入口 portal；HP 归零显示死亡界面，按 R 回出生点。
Game 负责输入、UI 覆盖层（对话/横幅/淡入/死亡界面）、存档与地图加载状态机；
World（src/game/world.py）负责单图场景的状态、实体与每帧更新/绘制。
"""

from __future__ import annotations

import os
import threading
import traceback
from typing import List, Optional, Tuple

import pygame

from game import settings
from game.render.assets import Assets
from game.render.effects import Effect
from game.systems.quests import load_quest_defs, render_markup
from game.systems.lua_quests import build_advance_quest_defs, load_lua_quest_defs
from game.npc_dialogue import NpcDialogueController
from game.save_manager import SaveManager
from game.render.splash import Splash
from game.context import GameContext
from game.core.fonts import load_cjk_font, render_text

# 输入对象（把 pygame 按键抽象成 Player.update 需要的形状）
class _Keys:
    left = False
    right = False
    up = False
    down = False
    jump = False       # 按住跳
    attack = False
    drop = False       # 下跳


class Game:
    def __init__(self):
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        # macOS：默认情况下“聚焦窗口的第一次点击”会被系统吞掉（表现为
        # 要点两下才响应）。打开 SDL 该 hint 后，点击聚焦与点击响应合一。
        os.environ.setdefault("SDL_MOUSE_FOCUS_CLICKTHROUGH", "1")
        pygame.init()
        self.screen = pygame.display.set_mode(
            (settings.WINDOW_W, settings.WINDOW_H))
        pygame.display.set_caption(
            f"Maplestory 113 · {settings.MAP_ID} · pygame")
        self.canvas = pygame.Surface((settings.VIEW_W, settings.VIEW_H))
        self.clock = pygame.time.Clock()
        self.running = True

        # 存档概览（轻量、先读），世界构建在后台线程完成
        self.save_manager = SaveManager(settings.SAVE_FILE)
        self.save_data = self.save_manager.load()
        self._save_timer = 0.0
        start_map = (self.save_data["player"]["map_id"]
                     if self.save_data else settings.MAP_ID)

        # 开屏：初始化只铺轻量状态，重活全部交给 _build_world 后台线程。
        # 期间主循环只画 Splash，等 world_ready 后一次性接管。
        self.splash = Splash()
        self._boot_progress = 0.0
        self._boot_status = "正在进入冒险岛"
        self._world_ready = False

        # 地图切换异步加载状态机（world 未就绪前不触发）
        self._loading = False
        self._pending_map: Optional[Tuple[str, Optional[str]]] = None
        self._loading_timer = 0.0
        # 黑场淡入进度（0=无；进入游戏/切图/重生后置 1，随 dt 递减）
        self.fade = 0.0

        threading.Thread(target=self._build_world, args=(start_map,),
                         daemon=True).start()

    # ── 后台构建整个世界 ────────────────────────────────────────────
    def _build_world(self, start_map: str) -> None:
        """后台线程执行原先 __init__ 的重活：资源 / 任务 / World / 面板。

        逐步推进 _boot_progress 以驱动开屏进度条；任何异常都让世界就绪
        并抛给主线程（避免游戏卡死在开屏）。
        """
        try:
            self._boot_progress = 0.05
            self.assets = Assets(start_map, settings.REGION)
            self._boot_progress = 0.20
            # 任务解析与地图/实体构建并行：Quest.wz 与其他 WZ 各自独立
            # reader_lock，线程安全；Player 构造前 join 取回结果。
            quest_box: dict = {}

            def _load_quests() -> None:
                try:
                    quest_box["defs"] = load_quest_defs(
                        self.assets, settings.ENABLED_QUESTS)
                except Exception:
                    traceback.print_exc()
                    quest_box["defs"] = {}

            quest_thread = threading.Thread(target=_load_quests, daemon=True)
            quest_thread.start()

            # 任务数据：等待后台解析完成（只解析 ENABLED_QUESTS 精选任务）
            quest_thread.join()
            self.quest_defs = quest_box.get("defs") or {}
            # 合并 Lua 自定义任务（content/npc/*.lua）与转职任务（script=advance）
            lua_defs = load_lua_quest_defs()
            adv_defs = build_advance_quest_defs()
            if lua_defs or adv_defs:
                self.quest_defs = {**self.quest_defs, **lua_defs, **adv_defs}

            # 组合根：装配音效 / UI / 面板 / 单图场景（World），并完成互相接线
            self.ctx = GameContext.create(self.assets, self.quest_defs,
                                          self.save_data)
            self.ctx.panels._quest_goal_lines = self._quest_extra_goal_lines

            self._boot_progress = 1.0
            self._boot_status = ""
        except Exception:
            traceback.print_exc()
        finally:
            self._world_ready = True

    def _finish_bootstrap(self) -> None:
        """世界构建完成后，在主线程恢复轻量状态并播 BGM / 欢迎对话框。"""
        self.keys = _Keys()
        self.dead = False
        self._dialogue = NpcDialogueController(self.ctx, self.quest_defs)
        self._banner: Optional[Tuple[str, str]] = None
        self._banner_timer = 0.0
        self.spawn_grace = settings.SPAWN_GRACE
        self.fade = 1.0        # 开屏进入游戏时黑场淡入

        self.ctx.audio.play_bgm()
        self._show_banner()
        self.ctx.world.preload_neighbors()
        if self.save_data:
            self.ctx.ui.show_dialog("读取存档", [
                f"欢迎回来，Lv.{self.ctx.world.player.level} 冒险者！",
                "已从本地存档载入你的进度。",
                "（对话不影响行动，Enter/Esc 或点击关闭）"])
        else:
            self.ctx.ui.show_dialog("欢迎", ["冒险岛 v113 · 弓箭手村东部小山",
                                          "←→ 移动  空格 跳跃  ↓+空格 下跳  ↑ 爬绳/梯",
                                          "A 攻击  Z 拾取  数字键 技能  F 喝药",
                                          "I 道具栏  K 技能栏  B 状态  Q 任务日志  M 小地图",
                                          "Enter 对话  R 复活",
                                         "背包满了？双击道具使用/穿戴，把它拖出背包窗口即可扔在地上"
                                         "（已穿装备也能从纸娃娃拖出扔掉）。",
                                          "新手练到 Lv10 后，找出生点旁的赫丽娜转职弓箭手；"
                                         "走到发光传送门前按 ↑ 可切换地图。"
                                          "（对话不影响行动，Enter/Esc 或点击关闭）"])

    # ── 输入 ───────────────────────────────────────────────────────
    def _handle_input(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif self._loading:
                continue       # 加载期间只处理关闭事件
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.dead:
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    # 对话层（列表/按钮/气泡）优先消费；否则交给商店/仓库/背包
                    if self._dialogue.consume_click((cx, cy)):
                        continue
                    if self.ctx.shop_panel.visible:
                        self.ctx.shop_panel.handle_click((cx, cy), self.ctx.world.player, self.ctx.world.combat)
                    elif self.ctx.storage_panel.visible:
                        self.ctx.storage_panel.handle_click((cx, cy), self.ctx.world.player)
                    else:
                        self.ctx.panels.handle_mouse_down((cx, cy), self.ctx.world.player)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
                if not self.dead:
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    amount = -1 if event.button == 4 else 1
                    if self.ctx.shop_panel.visible:
                        self.ctx.shop_panel.handle_wheel((cx, cy), amount, self.ctx.world.player)
                    elif self.ctx.storage_panel.visible:
                        self.ctx.storage_panel.handle_wheel((cx, cy), amount, self.ctx.world.player)
                    elif self.ctx.panels.handle_wheel((cx, cy), amount, self.ctx.world.player):
                        pass   # 背包 / 技能窗滚轮，已消费
            elif event.type == pygame.MOUSEMOTION:
                if self.ctx.panels.is_dragging():
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    self.ctx.panels.handle_mouse_motion((cx, cy))
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if not self.dead:
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    dropped = self.ctx.panels.handle_mouse_up((cx, cy), self.ctx.world.player)
                    if dropped is not None:
                        self.ctx.world.combat.drop_player_item(self.ctx.world.player, dropped)
                        self.ctx.audio.play("PickUpItem", 0.3)
                else:
                    self.ctx.panels.handle_mouse_up()
            elif event.type == pygame.KEYDOWN:
                if self.dead:
                    if event.key == pygame.K_r:
                        self.respawn()
                    continue
                # 任务/寒暄对话框：回车/空格/Esc 交给对话层消费；其余按键照常
                if self._dialogue.consume_keydown(event.key):
                    continue
                # 商店 / 仓库面板：Esc 关闭
                if event.key == pygame.K_ESCAPE:
                    if self.ctx.shop_panel.visible or self.ctx.storage_panel.visible:
                        self.ctx.shop_panel.close()
                        self.ctx.storage_panel.close()
                        continue
                if event.key == pygame.K_i:
                    self.ctx.panels.toggle_inventory()
                elif event.key == pygame.K_k:
                    self.ctx.panels.toggle_skill()
                elif event.key == pygame.K_q:
                    self.ctx.panels.toggle_quest_log()
                elif event.key == pygame.K_m:
                    self.ctx.world.minimap.toggle()
                elif event.key == pygame.K_f:
                    if self.ctx.world.player.use_potion():
                        self.ctx.audio.play("PickUpItem", 0.4)
                elif pygame.K_1 <= event.key <= pygame.K_9:
                    self._cast_skill(event.key - pygame.K_1 + 1)
                elif event.key == pygame.K_UP:
                    if not self.keys.down and self.ctx.world.portal_at_feet() is not None:
                        pass  # 站在传送门上按 ↑ → 交给 _check_portal 切图
                    elif self.keys.down:
                        self.ctx.world.player.drop_through(self.ctx.world.physics)
                    # ↑ 不再触发跳跃，仅用于传送门和爬绳（爬绳由 update 中 keys.up 驱动）
                elif event.key == pygame.K_SPACE:
                    if self.keys.down:
                        self.ctx.world.player.drop_through(self.ctx.world.physics)
                    elif self.ctx.world.player.climbing:
                        self.ctx.audio.play("Jump", 0.5)
                        self.ctx.world.player.jump()
                    else:
                        if self.ctx.world.player.on_ground:
                            self.ctx.audio.play("Jump", 0.5)
                        self.ctx.world.player.jump()
                elif event.key == pygame.K_z:
                    self._try_pickup()
                elif event.key == pygame.K_a:
                    self.ctx.world.player.start_attack()
                elif event.key == pygame.K_DOWN and self.keys.jump:
                    self.ctx.world.player.drop_through(self.ctx.world.physics)
                elif event.key == pygame.K_b:
                    self.ctx.panels.toggle_stat()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._dialogue.try_talk()

        # 加载期间不采集按键、不兜底攻击
        if self._loading:
            return
        pressed = pygame.key.get_pressed()
        # 移动只用方向键；A 为攻击
        self.keys.left = bool(pressed[pygame.K_LEFT])
        self.keys.right = bool(pressed[pygame.K_RIGHT])
        self.keys.up = bool(pressed[pygame.K_UP])
        self.keys.down = bool(pressed[pygame.K_DOWN])
        self.keys.attack = bool(pressed[pygame.K_a])
        self.keys.jump = bool(pressed[pygame.K_SPACE])

        # 兜底：弹窗瞬间按住的 A 等按键事件会被模态分支吞掉，
        # 用持续按键状态补触发攻击（按下即生效，无需等松开重按）
        if (self.keys.attack and not self.ctx.ui.dialog_visible
                and not self.dead and not self.ctx.world.player.attacking):
            self.ctx.world.player.start_attack()

    def _try_pickup(self) -> bool:
        """Z 键手动拾取人物周边掉落物；有收获则播放音效。"""
        if self.ctx.world.combat.pickup(self.ctx.world.player):
            self.ctx.audio.play("PickUpItem", 0.5)
            return True
        return False

    def _cast_skill(self, hotkey: int) -> None:
        """按数字快捷键施放技能（读职业动态快捷键表）。成功则播放施放特效。"""
        sid = self.ctx.world.player.skills.hotkeys.get(hotkey)
        if sid is None:
            return
        data = self.ctx.world.player.skills.cast(sid, self.ctx.world.player.level)
        if data is None:
            return
        if self.ctx.world.player.start_attack(data):
            eff = self.assets.skill_effect_frames(sid)
            if eff:
                self.ctx.world.combat.effects.append(Effect(
                    eff, self.ctx.world.player.x, self.ctx.world.player.y))

    def _qmark(self, text: str) -> str:
        """把官方 Say 文本里的标记替换为可读文本。"""
        a = self.assets
        return render_markup(text, a,
                             map_name=a.map_name_of, npc_name=a.npc_name,
                             item_name=a.item_name, mob_name=a.mob_name_of)

    def _quest_extra_goal_lines(self, qid: str) -> List[str]:
        """任务日志：生成当前进行中任务的目标行（击杀 / 收集 / 描述）。"""
        d = self.quest_defs.get(qid)
        if d is None:
            return []
        q = self.ctx.world.player.quests
        lines: List[str] = []
        for mid, count in d.kills:
            cur = q.kill_progress(qid, mid)
            lines.append(f"击杀 {self.assets.mob_name_of(mid)}  {cur}/{count}")
        for iid, count in d.end_items:
            cur = q.item_progress(self.ctx.world.player, qid, iid)
            lines.append(f"收集 {self.assets.item_name(str(iid)) or f'#{iid}'}  {cur}/{count}")
        if not lines and d.desc1:
            lines.append(self._qmark(d.desc1))
        if d.reward_exp:
            lines.append(f"奖励：经验 {d.reward_exp}")
        if d.reward_money:
            lines.append(f"奖励：金币 {d.reward_money}")
        for iid, count in d.reward_items:
            if count > 0:
                lines.append(f"奖励：{self.assets.item_name(str(iid)) or f'#{iid}'} ×{count}")
        return lines

    # ── 重生 ───────────────────────────────────────────────────────
    def respawn(self) -> None:
        self.dead = False
        self.spawn_grace = settings.SPAWN_GRACE
        self.ctx.ui.hide_death()
        self._dialogue.close_all()
        p = self.ctx.world.player
        p.hp = p.max_hp
        p.attacking = False
        p.hurt_timer = 0.0
        p.invuln_timer = 0.0
        p.feather.consume()
        p.buffs.clear()
        p.statuses.clear()
        self.fade = 1.0        # 重生黑场淡入
        self.ctx.world.respawn_scene()

    # ── 传送门 / 地图切换 ──────────────────────────────────────────
    def _enter_map(self, map_id: str, portal_name: Optional[str]) -> None:
        """切换到目标地图：后台渲染地图，主线程显示加载画面。"""
        if self._loading:
            return
        self._dialogue.close_all()
        self.ctx.shop_panel.close()
        self.ctx.storage_panel.close()
        self.ctx.audio.stop_bgm()

        self.assets.start_load_map(map_id)
        self._loading = True
        self._pending_map = (map_id, portal_name)
        self._loading_timer = 0.0

    def _finish_loading(self) -> None:
        """后台线程完成后，在主线程恢复游戏状态。"""
        bgm_path = self.assets.finish_load_map()
        _map_id, portal_name = self._pending_map
        self.ctx.audio.bgm_path = bgm_path
        self.ctx.world.finish_loading(portal_name)
        self.ctx.audio.play_bgm()
        self._show_banner()
        self._loading = False
        self._pending_map = None
        self.fade = 1.0        # 黑场淡入新地图

    def _show_banner(self) -> None:
        """切图横幅：主标题地图名 + 副标题街道名，随 fade 淡入淡出。"""
        name, street = self.assets.map_banner()
        self._banner = (name, street)
        self._banner_timer = settings.BANNER_TIME

    # ── 存档 ─────────────────────────────────────────────────────────
    def _save_game(self) -> None:
        """收集当前游戏状态，非同步写入本地存档（不阻塞主循环）。"""
        try:
            self.save_manager.request_save(SaveManager.collect_data(
                self.ctx.world.player, self.ctx.world.combat, self.assets.map_id))
        except Exception:
            pass

    # ── 更新 ───────────────────────────────────────────────────────
    def _update(self, dt: float) -> None:
        if self._banner_timer > 0:
            self._banner_timer -= dt
        # 黑场淡入计时（切图 / 重生后用真实 dt 递减）
        if self.fade > 0.0:
            self.fade = max(0.0, self.fade - dt / settings.FADE_TIME)
        # 定时自动存档
        self._save_timer += dt
        if self._save_timer >= settings.SAVE_INTERVAL:
            self._save_timer = 0.0
            self._save_game()
        # 地图切换加载中：等待后台线程，恢复后继续游戏逻辑
        if self._loading:
            self._loading_timer += dt
            if self.assets.is_load_done:
                self._finish_loading()
            return
        if self.dead:
            return

        # 对话框不再暂停世界；走远 / 切图自动收起
        self._dialogue.update()

        # 出生保护计时
        if self.spawn_grace > 0:
            self.spawn_grace -= dt

        # 世界帧（玩家/怪物/箭/NPC/战斗/相机），弹窗时屏蔽传送门检测
        portal_blocked = self._dialogue.portal_blocked()
        portal = self.ctx.world.update(dt, self.keys, self.spawn_grace,
                                   audio=self.ctx.audio, portal_blocked=portal_blocked)
        if portal is not None:
            if portal.get("same_map"):
                self.ctx.world.enter_same_map(portal)
                self.fade = 1.0
            else:
                self._enter_map(portal["target_id"], portal.get("targetName"))
            return

        # 死亡检测
        if self.ctx.world.player.hp <= 0:
            self.dead = True
            self.ctx.ui.show_death()
            self.ctx.audio.play("GameIn", 0.4)

    # ── 绘制 ───────────────────────────────────────────────────────
    def _draw(self) -> None:
        if self._loading:
            self._draw_loading()
            return
        # 世界实体（地图/传送门/掉落/NPC/怪物/玩家/箭/特效）
        self.ctx.world.draw(self.canvas, self._npc_marker, player_visible=not self.dead)
        # HUD / 面板 / 对话框 / 死亡
        self.ctx.ui.draw_hud(self.canvas, self.ctx.world.player, self.ctx.world.combat)
        self.ctx.world.minimap.draw(self.canvas, self.ctx.world.player.x, self.ctx.world.player.y,
                          self.ctx.world.player.facing_right, self.ctx.world.monsters, self.ctx.world.npcs)
        # 地图名名牌：小地图可见时下移避让，否则右上角 8px
        name_y = (settings.MINIMAP_MARGIN + settings.MINIMAP_H + 8
                  if self.ctx.world.minimap.visible else 8)
        self.ctx.ui.draw_map_name(self.canvas, self.assets.map_name(), name_y)
        self.ctx.panels.draw_quickslots(self.canvas, self.ctx.world.player)
        self.ctx.panels.draw(self.canvas, self.ctx.world.player, self.ctx.world.combat.meso)
        if self.ctx.shop_panel.visible:
            self.ctx.shop_panel.draw(self.canvas, self.ctx.world.player, self.ctx.world.combat)
        elif self.ctx.storage_panel.visible:
            self.ctx.storage_panel.draw(self.canvas, self.ctx.world.player)
        self.ctx.ui.draw_dialog(self.canvas, self.ctx.world.camera)
        self.ctx.ui.draw_quest(self.canvas)
        self.ctx.ui.draw_death(self.canvas)

        # 黑场淡入（切图 / 重生后从黑渐变到场景，避免瞬间弹出）
        if self.fade > 0.0:
            alpha = int(255 * self.fade)
            veil = pygame.Surface((settings.VIEW_W, settings.VIEW_H),
                                  pygame.SRCALPHA)
            veil.fill((0, 0, 0, alpha))
            self.canvas.blit(veil, (0, 0))

        # 切图横幅（画在黑场之上，淡入淡出）
        self._draw_banner(self.canvas)

        self._present()

    def _draw_banner(self, surface) -> None:
        """切图横幅：地图名（大）+ 街道名（小），首尾各 0.5s 淡入淡出。"""
        if self._banner_timer <= 0 or self._banner is None:
            return
        name, street = self._banner
        total = settings.BANNER_TIME
        elapsed = total - self._banner_timer
        edge = 0.5
        if elapsed < edge:
            a = elapsed / edge
        elif self._banner_timer < edge:
            a = self._banner_timer / edge
        else:
            a = 1.0
        alpha = max(0, min(255, int(255 * a)))
        cx = settings.VIEW_W // 2
        cy = settings.VIEW_H // 3
        big = load_cjk_font(52)
        small = load_cjk_font(26)
        title = render_text(big, name, (255, 246, 214))
        self._blit_faded(surface, title, (cx, cy), alpha)
        if street:
            sub = render_text(small, street, (210, 210, 220))
            self._blit_faded(surface, sub, (cx, cy + 44), alpha)

    @staticmethod
    def _blit_faded(surface, text_surf, center: Tuple[int, int], alpha: int) -> None:
        """按 alpha 淡入淡出地绘制带逐像素透明的文字 Surface。

        不能用 Surface.set_alpha(int)：对 SRCALPHA 表面其行为未定义，真实显示
        驱动下会用统一 alpha 覆盖逐像素 alpha，使本应透明的背景整块变实色（闪
        色块）。这里在副本上用 BLEND_RGBA_MULT 只缩放 alpha 通道（背景 alpha=0
        乘后仍为 0），既正确淡变又不污染 render_text 的缓存表面。
        """
        if alpha >= 255:
            surface.blit(text_surf, text_surf.get_rect(center=center))
            return
        if alpha <= 0:
            return
        layer = text_surf.copy()
        mod = pygame.Surface(layer.get_size(), pygame.SRCALPHA)
        mod.fill((255, 255, 255, alpha))
        layer.blit(mod, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(layer, layer.get_rect(center=center))

    def _present(self) -> None:
        """把 canvas 呈现到窗口。scale=1 时直接 blit（省去每帧全画面复制）。"""
        canvas = self.canvas
        if settings.WINDOW_SCALE != 1:
            canvas = pygame.transform.scale(
                canvas, (settings.WINDOW_W, settings.WINDOW_H))
        self.screen.blit(canvas, (0, 0))
        pygame.display.flip()

    def _draw_loading(self) -> None:
        self.canvas.fill((0, 0, 0))
        font = load_cjk_font(48)
        dots = "." * (int(self._loading_timer * 3) % 4)
        text = render_text(font, f"载入中{dots}", (255, 255, 255))
        rect = text.get_rect(center=(settings.VIEW_W // 2, settings.VIEW_H // 2))
        self.canvas.blit(text, rect)
        hint_font = load_cjk_font(24)
        hint = render_text(hint_font, "Loading map...", (160, 160, 160))
        hint_rect = hint.get_rect(center=(settings.VIEW_W // 2, settings.VIEW_H // 2 + 50))
        self.canvas.blit(hint, hint_rect)
        self._present()

    def _npc_marker(self, npc) -> int:
        """NPC 任务灯泡：2=可交付 / 0=可接取 / 1=进行中 / -1=无任务。"""
        quests = self.ctx.world.player.quests
        npc_id = npc.npc_id
        # 可交付优先
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == npc_id \
                    and quests.is_accepted(qid) and quests.can_complete(qid, self.ctx.world.player):
                return 2
        # 可接取
        for qid, d in self.quest_defs.items():
            if d.start_npc is not None and str(d.start_npc) == npc_id \
                    and not quests.started(qid) and quests.can_start(qid, self.ctx.world.player):
                return 0
        # 进行中（交付 NPC 是这位）
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == npc_id \
                    and quests.is_accepted(qid):
                return 1
        return -1

    # ── 主循环 ─────────────────────────────────────────────────────
    def run(self) -> None:
        while self.running:
            # 尖峰帧（切窗回来/卡顿）限步长：单帧重力下陷必须留在
            # grounded_surface 容差内（G*dt^2 < 2.5px），否则会误穿地
            dt = min(self.clock.tick(settings.FPS) / 1000.0, 0.035)
            if not self._world_ready:
                self._bootstrap_frame(dt)
                continue
            if not getattr(self, "_boot_done", False):
                self._finish_bootstrap()
                self._boot_done = True
            self._handle_input()
            self._update(dt)
            self._draw()
        self._shutdown()

    def _bootstrap_frame(self, dt: float) -> None:
        """开屏阶段：只画动画、响应关闭，等待世界构建完成。"""
        self.splash.update(dt)
        # 仅处理关闭事件，避免开屏期间按键被吞或误触发
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
        self._draw_splash()

    def _draw_splash(self) -> None:
        self.splash.draw(self.canvas, progress=self._boot_progress,
                         status=self._boot_status)
        self._present()

    def _shutdown(self) -> None:
        if not self._world_ready or not getattr(self, "_boot_done", False):
            # 世界未构建完成（开屏中途退出）：只清理已初始化的资源
            if hasattr(self, "ctx"):
                self.ctx.audio.close()
            if hasattr(self, "assets"):
                self.assets.close()
            pygame.quit()
            return
        try:
            self.save_manager.flush(SaveManager.collect_data(
                self.ctx.world.player, self.ctx.world.combat, self.assets.map_id))
        except Exception:
            traceback.print_exc()
        self.ctx.audio.close()
        self.assets.close()
        pygame.quit()
