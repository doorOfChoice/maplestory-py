"""游戏主场景：装配地图 / 生成 life 实体 / 主循环（60fps 固定步长）。

流程：加载资源 → 生成玩家 / 怪物 / NPC → 主循环（输入 → 更新 → 绘制）
出生 / 死亡重生：出生在入口 portal；HP 归零显示死亡界面，按 R 回到出生点并重置怪物。
"""

from __future__ import annotations

import os
import threading
import traceback
from typing import List, Optional, Tuple

import pygame

from . import settings
from .animation import Animation
from .assets import Assets
from .physics import Physics
from .camera import Camera
from .audio import Audio
from .player import Player
from .monster import Monster
from .npc import NPC
from .combat import Combat
from .combat import DamageNumber
from . import dialogues
from . import travel
from .effects import Effect
from .jobs import JOBS, can_advance
from .ui import UI
from .minimap import MiniMap
from .panels import Panels
from .quests import load_quest_defs, render_markup
from .save_manager import SaveManager
from .splash import Splash
from .fonts import load_cjk_font, render_text

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
        """后台线程执行原先 __init__ 的重活：资源 / 任务 / 实体 / 面板。

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
            self.physics = Physics(self.assets.footholds, self.assets.ropes,
                                   bounds=self.assets.bounds)
            self.camera = Camera(self.assets.map_width, self.assets.map_height,
                                 self.assets.bounds["left"],
                                 self.assets.bounds["top"])
            self.audio = Audio(self.assets, self.assets.map_bgm_path())
            self.combat = Combat(self.assets)
            self.ui = UI(self.assets)
            self.minimap = MiniMap(
                self.assets.footholds, self.assets.ropes, self.assets.portals,
                self.assets.bounds, self.assets.map_width, self.assets.map_height,
                mag=(self.assets.map_desc.get("minimap") or {}).get("mag"),
                canvas=self.assets.minimap_surface(),
                map_surface=self.assets.map_surface)

            self._boot_progress = 0.40
            self.panels = Panels(self.ui, self.assets)
            self.panels._quest_goal_lines = self._quest_extra_goal_lines

            # 任务数据：等待后台解析完成（只解析 ENABLED_QUESTS 精选任务）
            quest_thread.join()
            self.quest_defs = quest_box.get("defs") or {}

            # 出生点：入口 portal（sp，type 0）；读档时用存档位置
            spawn = self._find_spawn()
            self.spawn_x = spawn[0]
            self.spawn_y = spawn[1]
            if self.save_data:
                pd = self.save_data["player"]
                self.spawn_x = float(pd["x"])
                self.spawn_y = float(pd["y"]) + settings.FEET_OFFSET

            self.player = Player(self.assets, self.spawn_x, self.spawn_y,
                                 quest_defs=self.quest_defs,
                                 save_data=self.save_data)
            if not self.save_data:
                self.player.facing_right = True
            # 落地吸附到出生点的 foothold
            self._place_player_at_spawn()

            self._boot_progress = 0.70
            self.monsters: List[Monster] = []
            self.npcs: List[NPC] = []
            self.hits: List[dict] = []
            self._life_mobs = [d for d in self.assets.life if d["type"] == "mob"]
            self._life_npcs = [d for d in self.assets.life if d["type"] == "npc"]
            self._spawn_life()

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
        self._talk_npc: Optional[NPC] = None
        self._quest_flow = None
        self._portal_cooldown = 0.0
        self._portal_pulse = 0.0
        self._banner: Optional[Tuple[str, str]] = None
        self._banner_timer = 0.0
        self.spawn_grace = settings.SPAWN_GRACE
        self.fade = 1.0        # 开屏进入游戏时黑场淡入

        self.audio.play_bgm()
        self._show_banner()
        self._preload_neighbors()
        if self.save_data:
            self.ui.show_dialog("读取存档", [
                f"欢迎回来，Lv.{self.player.level} 冒险者！",
                "已从本地存档载入你的进度。",
                "（对话不影响行动，Enter/Esc 或点击关闭）"])
        else:
            self.ui.show_dialog("欢迎", ["冒险岛 v113 · 弓箭手村东部小山",
                                         "A/D(或←→) 移动  空格 跳跃  S+空格 下跳",
                                         "W(或↑) 爬绳/梯  J 攻击  数字键 技能  F 喝药",
                                         "I 道具栏  K 技能栏  B 状态  Q 任务日志  Enter 对话  R 复活",
                                         "背包满了？双击道具使用/穿戴，把它拖出背包窗口即可扔在地上"
                                         "（已穿装备也能从纸娃娃拖出扔掉）。",
                                         "新手练到 Lv10 后，找出生点旁的赫麗娜转职弓箭手；"
                                         "走到发光传送门前按 ↑ 可切换地图。"
                                         "（对话不影响行动，Enter/Esc 或点击关闭）"])

    # ── 生成 ───────────────────────────────────────────────────────
    def _find_spawn(self):
        for p in self.assets.portals:
            if p["name"] == "sp" and p["type"] == 0:
                return float(p["x"]), float(p["y"])
        return 0.0, 0.0

    def _spawn_life(self) -> None:
        self.monsters = [Monster(self.assets, d, i, self.physics)
                         for i, d in enumerate(self._life_mobs)]
        self._respawn_queue = []      # [(剩余秒, life_data)]：切图/重生时清空
        self.npcs = [NPC(self.assets, d, i)
                     for i, d in enumerate(self._life_npcs)]
        # 导师注入：原版赫麗娜在 100000201（不可达），在出生图额外生成一个实例
        if self.assets.map_id == settings.TRAINER_SPAWN_MAP:
            self.npcs.append(NPC(self.assets, {
                "id": settings.BOWMAN_TRAINER_NPC,
                "x": settings.TRAINER_SPAWN[0],
                "cy": settings.TRAINER_SPAWN[1]}, len(self.npcs)))

    def _tick_respawns(self, dt: float) -> None:
        """重生队列计时：mobTime>0 按其毫秒数，否则用 MOB_RESPAWN_DELAY 兜底。"""
        if not self._respawn_queue:
            return
        still: List[Tuple[float, dict]] = []
        for remaining, data in self._respawn_queue:
            remaining -= dt
            if remaining <= 0:
                self.monsters.append(
                    Monster(self.assets, data, len(self.monsters), self.physics))
            else:
                still.append((remaining, data))
        self._respawn_queue = still

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
                    # 任务对话框按钮优先
                    btn = self.ui.quest_hit((cx, cy))
                    if btn is not None:
                        self._quest_button(btn)
                    elif self.ui.quest_dialog_hit((cx, cy)):
                        pass   # 点对话框空白处不关闭（选项型）
                    elif self.ui.dialog_hit((cx, cy)):
                        # 点击气泡本体 → 关闭对话（面板照常可点）
                        self.ui.hide_dialog()
                        self._talk_npc = None
                    else:
                        self.panels.handle_mouse_down((cx, cy), self.player)
            elif event.type == pygame.MOUSEMOTION:
                if self.panels.is_dragging():
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    self.panels.handle_mouse_motion((cx, cy))
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if not self.dead:
                    cx = event.pos[0] * settings.VIEW_W // settings.WINDOW_W
                    cy = event.pos[1] * settings.VIEW_H // settings.WINDOW_H
                    dropped = self.panels.handle_mouse_up((cx, cy), self.player)
                    if dropped is not None:
                        self.combat.drop_player_item(self.player, dropped)
                        self.audio.play("PickUpItem", 0.3)
                else:
                    self.panels.handle_mouse_up()
            elif event.type == pygame.KEYDOWN:
                if self.dead:
                    if event.key == pygame.K_r:
                        self.respawn()
                    continue
                # 任务对话框：Enter/Esc 视为 OK（有 yes/no 时视为拒绝/关闭）
                if self.ui.quest_visible:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                     pygame.K_SPACE, pygame.K_ESCAPE):
                        if self._quest_flow is not None \
                                and self._quest_flow["stage"] in ("offer", "complete"):
                            self._quest_button("no")
                        else:
                            self.ui.hide_quest()
                            self._quest_flow = None
                        continue
                # 对话框非模态：Enter/空格/Esc 关闭本次按键；其余按键照常
                if self.ui.dialog_visible:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                     pygame.K_SPACE, pygame.K_ESCAPE):
                        self.ui.hide_dialog()
                        self._talk_npc = None
                        continue
                if event.key == pygame.K_i:
                    self.panels.toggle_inventory()
                elif event.key == pygame.K_k:
                    self.panels.toggle_skill()
                elif event.key == pygame.K_q:
                    self.panels.toggle_quest_log()
                elif event.key == pygame.K_m:
                    self.minimap.toggle()
                elif event.key == pygame.K_f:
                    if self.player.use_potion():
                        self.audio.play("PickUpItem", 0.4)
                elif pygame.K_1 <= event.key <= pygame.K_9:
                    self._cast_skill(event.key - pygame.K_1 + 1)
                elif event.key == pygame.K_w:
                    # W 只用于上绳/梯（长按逻辑在 Player.update 中处理），不触发跳跃
                    pass
                elif event.key in (pygame.K_SPACE, pygame.K_UP):
                    if (event.key == pygame.K_UP and not self.keys.down
                            and self._portal_at_feet() is not None):
                        pass  # 站在传送门上按 ↑ → 交给 _check_portal 切图，不跳跃
                    elif self.keys.down:
                        self.player.drop_through(self.physics)
                    elif self.player.climbing:
                        # 只有空格从绳上跳下；↑ 在绳上继续爬
                        if event.key == pygame.K_SPACE:
                            self.audio.play("Jump", 0.5)
                            self.player.jump()
                    elif (self.physics.rope_at(self.player.x, self.player.y) is None
                          or event.key == pygame.K_SPACE):
                        # 绳边按 ↑ 是爬绳意图，不起跳
                        if self.player.on_ground:
                            self.audio.play("Jump", 0.5)
                        self.player.jump()
                elif event.key == pygame.K_j:
                    self.player.start_attack()
                elif event.key in (pygame.K_DOWN, pygame.K_s) and self.keys.jump:
                    self.player.drop_through(self.physics)
                elif event.key == pygame.K_b:
                    self.panels.toggle_stat()
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._try_talk()

        # 加载期间不采集按键、不兜底攻击
        if self._loading:
            return
        pressed = pygame.key.get_pressed()
        # WASD 与方向键并存
        self.keys.left = bool(pressed[pygame.K_LEFT] or pressed[pygame.K_a])
        self.keys.right = bool(pressed[pygame.K_RIGHT] or pressed[pygame.K_d])
        self.keys.up = bool(pressed[pygame.K_UP] or pressed[pygame.K_w])
        self.keys.down = bool(pressed[pygame.K_DOWN] or pressed[pygame.K_s])
        self.keys.attack = bool(pressed[pygame.K_j])
        self.keys.jump = bool(pressed[pygame.K_SPACE])

        # 兜底：弹窗瞬间按住的 J 等按键事件会被模态分支吞掉，
        # 用持续按键状态补触发攻击（按下即生效，无需等松开重按）
        if (self.keys.attack and not self.ui.dialog_visible
                and not self.dead and not self.player.attacking):
            self.player.start_attack()

    def _cast_skill(self, hotkey: int) -> None:
        """按数字快捷键施放技能（读职业动态快捷键表）。成功则播放施放特效。"""
        sid = self.player.skills.hotkeys.get(hotkey)
        if sid is None:
            return
        data = self.player.skills.cast(sid, self.player.level)
        if data is None:
            return
        if self.player.start_attack(data):
            eff = self.assets.skill_effect_frames(sid)
            if eff:
                self.combat.effects.append(Effect(
                    eff, self.player.x, self.player.y))

    def _try_talk(self) -> None:
        """与 NPC 对话：导师转职 > 任务交互 > 普通寒暄。"""
        for npc in self.npcs:
            if npc.rect().colliderect(
                    pygame.Rect(int(self.player.x - 20), int(self.player.y - 40), 40, 80)):
                self._talk_npc = npc
                if npc.npc_id == settings.BOWMAN_TRAINER_NPC \
                        and self._begin_advance_flow(npc):
                    return
                if self._begin_quest_flow(npc):
                    return
                self.ui.show_dialog(npc.name,
                                    dialogues.get_dialog(npc.npc_id, npc.name),
                                    anchor=npc)
                return

    # ── 转职对话流程 ───────────────────────────────────────────────
    def _begin_advance_flow(self, npc) -> bool:
        """导师对话：可转职弹确认框；已转职/等级不足给对应提示。"""
        jobdef = JOBS[settings.BOWMAN_JOB]
        if self.player.job == jobdef.code:
            self.ui.show_dialog(npc.name, ["你已经是一名出色的弓箭手了。"], anchor=npc)
            return True
        if can_advance(self.player, jobdef):
            self._quest_flow = {"npc": npc, "quest": None, "stage": "advance"}
            self.ui.show_quest(f"转职 · {jobdef.name}", [
                "你想成为弓箭手吗？",
                f"达到 Lv{jobdef.advance_lv} 的新手可以转职为{jobdef.name}，",
                "转职后我会送你一把短弓并教你弓箭手的技能。"], ["yes", "no"])
            return True
        self.ui.show_dialog(npc.name, [
            "你还太弱小了，达到等级再来找我吧。",
            f"（当前 Lv{self.player.level} / 需要 Lv{jobdef.advance_lv}）"], anchor=npc)
        return True

    # ── 任务对话状态机 ─────────────────────────────────────────────
    def _begin_quest_flow(self, npc) -> bool:
        """检查与 NPC 的任务交互。返回是否进入了任务对话框。"""
        quests = self.player.quests
        npc_id = npc.npc_id

        # 1. 可交付（进行中且条件满足）
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == npc_id \
                    and quests.is_accepted(qid) and quests.can_complete(qid, self.player):
                self._quest_flow = {"npc": npc, "quest": qid, "stage": "complete"}
                self._show_quest_complete(qid)
                return True

        # 2. 可接取（给予 NPC 是这位，且条件满足、未接未完成）
        for qid, d in self.quest_defs.items():
            if d.start_npc is not None and str(d.start_npc) == npc_id \
                    and not quests.started(qid) and quests.can_start(qid, self.player):
                self._quest_flow = {"npc": npc, "quest": qid, "stage": "offer"}
                self._show_quest_offer(qid)
                return True

        # 3. 进行中但条件未满足（交付 NPC 是这位）
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == npc_id \
                    and quests.is_accepted(qid):
                self._quest_flow = {"npc": npc, "quest": qid, "stage": "status"}
                self._show_quest_status(qid)
                return True

        return False

    def _qmark(self, text: str) -> str:
        """把官方 Say 文本里的标记替换为可读文本。"""
        a = self.assets
        return render_markup(text, a,
                             map_name=a.map_name_of, npc_name=a.npc_name,
                             item_name=a.item_name, mob_name=a.mob_name_of)

    def _show_quest_offer(self, qid: str) -> None:
        d = self.quest_defs[qid]
        lines = [self._qmark(l) for l in d.accept_lines] or [f"要接受任务「{d.name}」吗？"]
        self.ui.show_quest(f"任务 · {d.name}", lines, ["yes", "no"])

    def _show_quest_complete(self, qid: str) -> None:
        d = self.quest_defs[qid]
        lines = [self._qmark(l) for l in d.complete_lines] or [
            f"已完成任务「{d.name}」的所有条件！要领取奖励吗？"]
        self.ui.show_quest(f"任务完成 · {d.name}", lines, ["yes", "no"])

    def _show_quest_status(self, qid: str) -> None:
        d = self.quest_defs[qid]
        lines = [self._qmark(l) for l in d.complete_stop] or \
                [f"「{d.name}」还未完成，继续努力吧！"]
        self.ui.show_quest(d.name, lines, ["ok"])

    def _quest_button(self, key: str) -> None:
        """任务/转职对话框按钮回调：yes / no / ok。"""
        flow = self._quest_flow
        if flow is None:
            self.ui.hide_quest()
            return
        if flow["stage"] == "advance":
            self.ui.hide_quest()
            self._quest_flow = None
            if key == "yes":
                self.player.advance_to(settings.BOWMAN_JOB, self.assets)
                self.audio.play("LevelUp", 0.6)
                self.panels.flash("转职成功：弓箭手")
            return
        qid = flow["quest"]
        quests = self.player.quests
        if flow["stage"] == "offer":
            if key == "yes":
                if quests.accept(qid, self.player):
                    d = self.quest_defs[qid]
                    self.audio.play("QuestClear", 0.5)
                    self.panels.flash(f"任务接受：{d.name}")
                    flow["stage"] = "accepted"
                    lines = [self._qmark(l) for l in d.accept_yes] or \
                            [f"已接受任务「{d.name}」。按 Q 查看任务日志。"]
                    self.ui.show_quest(d.name, lines, ["ok"])
                else:
                    self.ui.hide_quest()
            else:
                d = self.quest_defs[qid]
                flow["stage"] = "declined"
                lines = [self._qmark(l) for l in d.accept_no] or ["好吧，改变心意的话再来找我。"]
                self.ui.show_quest(d.name, lines, ["ok"])
        elif flow["stage"] == "complete":
            if key == "yes":
                if quests.complete(qid, self.player, self.combat,
                                   self.assets, self.audio):
                    d = self.quest_defs[qid]
                    self.panels.flash(f"任务完成：{d.name}")
                    flow["stage"] = "completed"
                    lines = [self._qmark(l) for l in d.complete_yes] or \
                            [f"已获得任务「{d.name}」的奖励！"]
                    self.ui.show_quest(d.name, lines, ["ok"])
                else:
                    self.ui.hide_quest()
            else:
                self.ui.hide_quest()
        else:   # status / accepted / declined / completed 只展示 → 关闭
            self.ui.hide_quest()
            self._quest_flow = None

    def _quest_extra_goal_lines(self, qid: str) -> List[str]:
        """任务日志：生成当前进行中任务的目标行（击杀 / 收集 / 描述）。"""
        d = self.quest_defs.get(qid)
        if d is None:
            return []
        q = self.player.quests
        lines: List[str] = []
        for mid, count in d.kills:
            cur = q.kill_progress(qid, mid)
            lines.append(f"击杀 {self.assets.mob_name_of(mid)}  {cur}/{count}")
        for iid, count in d.end_items:
            cur = q.item_progress(self.player, qid, iid)
            lines.append(f"收集 {self.assets.item_name(str(iid)) or f'#{iid}'}  {cur}/{count}")
        if not lines and d.desc1:
            lines.append(d.desc1)
        if d.reward_exp:
            lines.append(f"奖励：经验 {d.reward_exp}")
        if d.reward_money:
            lines.append(f"奖励：金币 {d.reward_money}")
        for iid, count in d.reward_items:
            if count > 0:
                lines.append(f"奖励：{self.assets.item_name(str(iid)) or f'#{iid}'} ×{count}")
        return lines

    # ── 重生 ───────────────────────────────────────────────────────
    def _place_player_at_spawn(self) -> None:
        p = self.player
        p.x = self.spawn_x
        p.y = self.spawn_y - settings.FEET_OFFSET
        p.vx = p.vy = 0.0
        p.on_ground = False
        p.climbing = False
        p.attacking = False
        p.attack_timer = 0.0
        p.drop_layers.clear()
        p.drop_timer = 0.0
        fh = self.physics.grounded_surface(p.x, p.feet_y)
        if fh is not None:
            p.y = fh.y_at(p.x) - settings.FEET_OFFSET
            p.on_ground = True
            p.cur_fh = fh
            p.ground_layer = fh.layer

    def respawn(self) -> None:
        self.dead = False
        self.spawn_grace = settings.SPAWN_GRACE
        self.ui.hide_death()
        self.ui.hide_dialog()
        self._talk_npc = None
        self.player.hp = self.player.max_hp
        self.player.attacking = False
        self.player.hurt_timer = 0.0
        self.player.invuln_timer = 0.0
        self.player.feather.consume()
        self.fade = 1.0        # 重生黑场淡入
        self._place_player_at_spawn()
        self._spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()
        self.combat.arrows.clear()

    # ── 传送门 / 地图切换 ──────────────────────────────────────────
    def _usable_portals(self) -> List[dict]:
        """当前地图可通行的传送门（WZ 数据驱动，含 trigger / target_id / same_map）。"""
        return travel.usable_portals(self.assets.portals,
                                     self.assets.map_renderer.has_map,
                                     self.assets.map_id)

    def _portal_at_feet(self) -> Optional[dict]:
        """回传玩家脚底重叠、且此刻可触发的传送门（按↑门需 up 键，碰撞门即时）。"""
        feet = self.player.y + settings.FEET_OFFSET
        pr = pygame.Rect(int(self.player.x - 12), int(feet - 12), 24, 24)
        for p in self._usable_portals():
            prt = pygame.Rect(int(p["x"]) - 14, int(p["y"]) - 14, 28, 28)
            if pr.colliderect(prt):
                return p
        return None

    def _check_portal(self, dt: float) -> bool:
        """站在可通行传送门上触发切图：按↑门需 up 键，碰撞门碰到即走。返回是否切图。"""
        if self._portal_cooldown > 0:
            self._portal_cooldown -= dt
            return False
        p = self._portal_at_feet()
        if p is None:
            return False
        if p["trigger"] == "up" and not self.keys.up:
            return False
        if p.get("same_map"):
            self._enter_same_map(p)
            return True
        self._enter_map(p["target_id"], p.get("targetName"))
        return True

    def _enter_same_map(self, p: dict) -> None:
        """同图瞬移门：不重载地图，直接落地到目标门位置（原版 psh 行为）。"""
        self._portal_cooldown = 0.8
        sx, sy = self._portal_position(p.get("targetName"))
        self.spawn_x, self.spawn_y = sx, sy
        self._place_player_at_spawn()
        self.fade = 1.0                # 黑场淡入，掩盖瞬移

    def _enter_map(self, map_id: str, portal_name: Optional[str]) -> None:
        """切换到目标地图：后台渲染地图，主线程显示加载画面。"""
        if self._loading:
            return
        self.ui.hide_dialog()
        self.ui.hide_quest()
        self._talk_npc = None
        self._quest_flow = None
        self.audio.stop_bgm()

        self.assets.start_load_map(map_id)
        self._loading = True
        self._pending_map = (map_id, portal_name)
        self._loading_timer = 0.0

    def _finish_loading(self) -> None:
        """后台线程完成后，在主线程恢复游戏状态。"""
        bgm_path = self.assets.finish_load_map()
        map_id, portal_name = self._pending_map
        self.physics = Physics(self.assets.footholds, self.assets.ropes,
                               bounds=self.assets.bounds)
        self.camera = Camera(self.assets.map_width, self.assets.map_height,
                             self.assets.bounds["left"], self.assets.bounds["top"])
        self.audio.bgm_path = bgm_path
        self._life_mobs = [d for d in self.assets.life if d["type"] == "mob"]
        self._life_npcs = [d for d in self.assets.life if d["type"] == "npc"]

        sx, sy = self._portal_position(portal_name)
        self.spawn_x, self.spawn_y = sx, sy
        self.minimap.set_map(
            self.assets.footholds, self.assets.ropes, self.assets.portals,
            self.assets.bounds, self.assets.map_width, self.assets.map_height,
            mag=(self.assets.map_desc.get("minimap") or {}).get("mag"),
            canvas=self.assets.minimap_surface(),
            map_surface=self.assets.map_surface)
        self._place_player_at_spawn()
        self._spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()
        self.combat.arrows.clear()
        self.hits.clear()
        self._portal_cooldown = 0.8

        self.audio.play_bgm()
        self._show_banner()
        self._preload_neighbors()
        self._loading = False
        self._pending_map = None
        self.fade = 1.0        # 黑场淡入新地图

    def _show_banner(self) -> None:
        """切图横幅：主标题地图名 + 副标题街道名，随 fade 淡入淡出。"""
        name, street = self.assets.map_banner()
        self._banner = (name, street)
        self._banner_timer = settings.BANNER_TIME

    def _preload_neighbors(self) -> None:
        """把当前图所有可通行传送门的目标图后台预热进 LRU 缓存，下次切图秒开。"""
        targets = {p["target_id"] for p in self._usable_portals()}
        targets.discard(self.assets.map_id)
        if targets:
            self.assets.preload_neighbors(targets)

    def _portal_position(self, portal_name: Optional[str]):
        """目标地图出生点：优先指定 portal，其次 sp 入口。"""
        for p in self.assets.portals:
            if portal_name and p.get("name") == portal_name:
                return float(p["x"]), float(p["y"])
        for p in self.assets.portals:
            if p.get("type") == 0:      # sp
                return float(p["x"]), float(p["y"])
        return float(self.assets.bounds["left"]), float(self.assets.bounds["top"])

    # ── 存档 ─────────────────────────────────────────────────────────
    def _save_game(self) -> None:
        """收集当前游戏状态，非同步写入本地存档（不阻塞主循环）。"""
        try:
            self.save_manager.request_save(SaveManager.collect_data(
                self.player, self.combat, self.assets.map_id))
        except Exception:
            pass

    # ── 更新 ───────────────────────────────────────────────────────
    def _update(self, dt: float) -> None:
        self._portal_pulse += dt
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
        if self.ui.dialog_visible and self._talk_npc is not None:
            r = self._talk_npc.rect()
            if abs(self.player.x - r.centerx) > 140:
                self.ui.hide_dialog()
                self._talk_npc = None
        # 任务对话框同样在走远后收起
        if self.ui.quest_visible and self._quest_flow is not None:
            r = self._quest_flow["npc"].rect()
            if abs(self.player.x - r.centerx) > 140:
                self.ui.hide_quest()
                self._quest_flow = None

        # 出生保护计时
        if self.spawn_grace > 0:
            self.spawn_grace -= dt

        # 玩家
        self.player.update(dt, self.keys, self.physics, self.audio)

        # 传送门检测
        if not self.ui.quest_visible and not self.ui.dialog_visible:
            if self._check_portal(dt):
                return

        # 掉出地图底部：回出生点并扣血（避免永远下坠）
        if self.player.y > self.assets.map_height + 80:
            self.player.damage(settings.FALL_OUT_DAMAGE)
            self.combat.numbers.append(DamageNumber(
                self.player.x, self.player.y - 40,
                settings.FALL_OUT_DAMAGE, "blue"))
            self._place_player_at_spawn()

        # 攻击判定：远程（普攻与技能）起手一次性生成箭（近战仍在首帧结算）
        if self.player.attacking:
            if self.player.is_ranged():
                if not self.player.attack_projectile_spawned:
                    self.player.attack_projectile_spawned = True
                    self.combat.spawn_arrows(self.player, self.player.pending_skill)
            else:
                self.combat.player_attack(self.player, self.monsters)

        # 经验结算（击杀累积后逐条发放，可升级；升级播官方特效不弹窗）
        while self.combat.pending_exp:
            amount = self.combat.pending_exp.pop(0)
            if self.player.gain_exp(amount):
                self.audio.play("LevelUp", 0.6)
                # 特效按角色锚点居中，整体抬高些更接近原版观感
                self.combat.effects.append(Effect(
                    self.assets.levelup_frames(), self.player.x, self.player.y - 45))

        # 怪物
        self.hits.clear()
        no_aggro = self.spawn_grace > 0
        for mob in self.monsters:
            mob.update(dt, self.player.x, self.player.y, self.hits, self.audio,
                       no_aggro=no_aggro)
        # 移除已消失的怪物；死亡者排入重生队列（mobTime>0 用其值，否则默认延迟）
        alive: List[Monster] = []
        for m in self.monsters:
            if m.dead and m.remove_after <= 0:
                delay = (m.mob_time / 1000.0 if m.mob_time > 0
                         else settings.MOB_RESPAWN_DELAY)
                self._respawn_queue.append((delay, m.life_data))
            else:
                alive.append(m)
        self.monsters = alive
        self._tick_respawns(dt)
        self.combat.apply_mob_hits(self.player, self.hits)

        # 飞行中的箭（在怪物移动之后结算，命中数受 mobCount 限制）
        self.combat.update_arrows(dt, self.monsters, self.player)

        # NPC
        for npc in self.npcs:
            npc.update(dt)

        # 拾取
        if self.combat.pickup(self.player):
            self.audio.play("PickUpItem", 0.5)

        # 死亡检测
        if self.player.hp <= 0:
            self.dead = True
            self.ui.show_death()
            self.audio.play("GameIn", 0.4)

        self.combat.update(dt, self.player)
        self.camera.center_on(self.player.x, self.player.y)

    # ── 绘制 ───────────────────────────────────────────────────────
    def _draw(self) -> None:
        if self._loading:
            self._draw_loading()
            return
        # 地图
        self.canvas.blit(
            self.assets.map_surface, (0, 0),
            pygame.Rect(self.camera.img_x, self.camera.img_y,
                        settings.VIEW_W, settings.VIEW_H))
        # 传送门（地图之上，实体之下）
        self._draw_portals(self.canvas)
        # 掉落物（地图之上，实体之下）
        self.combat.draw(self.canvas, self.camera)
        # NPC / 怪物（NPC 头顶画任务灯泡）
        for npc in self.npcs:
            npc.draw(self.canvas, self.camera, self._npc_marker(npc))
        for mob in self.monsters:
            mob.draw(self.canvas, self.camera)
        # 玩家
        if not self.dead:
            self.player.draw(self.canvas, self.camera)
        # 飞行中的箭（实体之上）
        self.combat.draw_arrows(self.canvas, self.camera)
        # 命中火花 / 升级特效（实体之上）
        self.combat.draw_effects(self.canvas, self.camera)
        # HUD / 面板 / 对话框 / 死亡
        self.ui.draw_hud(self.canvas, self.player, self.combat)
        self.minimap.draw(self.canvas, self.player.x, self.player.y,
                          self.player.facing_right, self.monsters, self.npcs)
        # 地图名名牌：小地图可见时下移避让，否则右上角 8px
        name_y = (settings.MINIMAP_MARGIN + settings.MINIMAP_H + 8
                  if self.minimap.visible else 8)
        self.ui.draw_map_name(self.canvas, self.assets.map_name(), name_y)
        self.panels.draw_quickslots(self.canvas, self.player)
        self.panels.draw(self.canvas, self.player, self.combat.meso)
        self.ui.draw_dialog(self.canvas, self.camera)
        self.ui.draw_quest(self.canvas)
        self.ui.draw_death(self.canvas)

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
        title.set_alpha(alpha)
        tr = title.get_rect(center=(cx, cy))
        surface.blit(title, tr)
        if street:
            sub = render_text(small, street, (210, 210, 220))
            sub.set_alpha(alpha)
            surface.blit(sub, sub.get_rect(center=(cx, cy + 44)))

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

    def _portal_frame_index(self, frames, t: float) -> int:
        """依累积秒数定位动画帧：每帧显示其 delay 毫秒时长（循环播放）。"""
        return Animation.frame_at(frames, t * 1000.0)

    def _draw_portals(self, surface) -> None:
        """画传送门：普通↑门用 pv 动画，同图瞬移门用 psh 缩小动画；隐藏门不画。"""
        frames = self.assets.portal_frames()
        shrink = self.assets.portal_shrink_frames()
        if not frames:
            return
        idx = self._portal_frame_index(frames, self._portal_pulse)
        sidx = self._portal_frame_index(shrink, self._portal_pulse)
        standing = self._portal_at_feet()
        for p in self._usable_portals():
            if p.get("trigger") != "up" or p.get("hidden"):
                continue
            sx, sy = self.camera.to_screen(p["x"], p["y"])
            surf, origin, _ = (shrink[sidx] if p.get("same_map") else frames[idx])
            rect = surf.get_rect()
            rect.centerx = int(sx)
            rect.bottom = int(sy) + 2
            surface.blit(surf, rect.topleft)
            # 玩家站在传送门上时画金色高亮光环
            if standing is not None and standing["name"] == p["name"]:
                pygame.draw.ellipse(surface, (255, 255, 140, 220),
                                    (rect.centerx - 18, rect.bottom - 10, 36, 14), 3)

    def _npc_marker(self, npc) -> int:
        """NPC 任务灯泡：2=可交付 / 0=可接取 / 1=进行中 / -1=无任务。"""
        quests = self.player.quests
        npc_id = npc.npc_id
        # 可交付优先
        for qid, d in self.quest_defs.items():
            if d.end_npc is not None and str(d.end_npc) == npc_id \
                    and quests.is_accepted(qid) and quests.can_complete(qid, self.player):
                return 2
        # 可接取
        for qid, d in self.quest_defs.items():
            if d.start_npc is not None and str(d.start_npc) == npc_id \
                    and not quests.started(qid) and quests.can_start(qid, self.player):
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
            if hasattr(self, "audio"):
                self.audio.close()
            if hasattr(self, "assets"):
                self.assets.close()
            pygame.quit()
            return
        try:
            self.save_manager.flush(SaveManager.collect_data(
                self.player, self.combat, self.assets.map_id))
        except Exception:
            pass
        self.audio.close()
        self.assets.close()
        pygame.quit()
