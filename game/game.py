"""游戏主场景：装配地图 / 生成 life 实体 / 主循环（60fps 固定步长）。

流程：加载资源 → 生成玩家 / 怪物 / NPC → 主循环（输入 → 更新 → 绘制）
出生 / 死亡重生：出生在入口 portal；HP 归零显示死亡界面，按 R 回到出生点并重置怪物。
"""

from __future__ import annotations

import os
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
from .effects import Effect
from .ui import UI
from .panels import Panels
from .quests import load_quest_defs, render_markup
from .save_manager import SaveManager

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

        # 存档：读本地 save.json；存在则继续，否则新游戏
        self.save_manager = SaveManager(settings.SAVE_FILE)
        self.save_data = self.save_manager.load()
        self._save_timer = 0.0
        start_map = (self.save_data["player"]["map_id"]
                     if self.save_data else settings.MAP_ID)

        # 资源
        self.assets = Assets(start_map, settings.REGION)
        self.physics = Physics(self.assets.footholds, self.assets.ropes,
                               bounds=self.assets.bounds)
        self.camera = Camera(self.assets.map_width, self.assets.map_height,
                             self.assets.bounds["left"], self.assets.bounds["top"])
        self.audio = Audio(self.assets, self.assets.map_bgm_path())
        self.combat = Combat(self.assets)
        self.ui = UI(self.assets)
        self.panels = Panels(self.ui, self.assets)
        self.panels._quest_goal_lines = self._quest_extra_goal_lines

        # 任务数据：解析全部 Quest.wz，仅开放精选任务
        self.quest_defs = load_quest_defs(self.assets)
        self.quest_defs = {qid: d for qid, d in self.quest_defs.items()
                           if qid in settings.ENABLED_QUESTS}

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

        self.monsters: List[Monster] = []
        self.npcs: List[NPC] = []
        self.hits: List[dict] = []
        self._life_mobs = [d for d in self.assets.life if d["type"] == "mob"]
        self._life_npcs = [d for d in self.assets.life if d["type"] == "npc"]
        self._spawn_life()

        self.keys = _Keys()
        self.dead = False
        self._talk_npc: Optional[NPC] = None
        self._quest_flow = None          # 任务对话框状态机（见 _begin_quest_flow）
        self._portal_cooldown = 0.0      # 传送冷却，防止一帧多次切图
        self._portal_pulse = 0.0         # 传送门脉冲动画相位
        self.spawn_grace = settings.SPAWN_GRACE

        # 地图切换异步加载状态机
        self._loading = False
        self._pending_map: Optional[Tuple[str, Optional[str]]] = None
        self._loading_timer = 0.0

        self.audio.play_bgm()
        if self.save_data:
            self.ui.show_dialog("读取存档", [
                f"欢迎回来，Lv.{self.player.level} 冒险者！",
                "已从本地存档载入你的进度。",
                "（对话不影响行动，Enter/Esc 或点击关闭）"])
        else:
            self.ui.show_dialog("欢迎", ["冒险岛 v113 · 弓箭手村东部小山",
                                         "A/D(或←→) 移动  空格 跳跃  S+空格 下跳",
                                         "W(或↑) 爬绳/梯  J 攻击  1/2 技能  F 喝药",
                                         "I 道具栏  K 技能栏  Q 任务日志  Enter 对话  R 复活",
                                         "走到发光传送门前按 ↑ 可切换地图；NPC 头顶灯泡表示有任务。"
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
        self.npcs = [NPC(self.assets, d, i)
                     for i, d in enumerate(self._life_npcs)]

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
                elif event.key == pygame.K_f:
                    if self.player.use_potion():
                        self.audio.play("PickUpItem", 0.4)
                elif event.key in (pygame.K_1, pygame.K_2):
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
        """按快捷键施放技能（1/2）。成功则播放技能施放特效。"""
        sid = settings.HOTKEY_SKILLS.get(hotkey)
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
        """与 NPC 对话：优先任务交互（可交付 > 可接取 > 进行中），否则普通寒暄。"""
        for npc in self.npcs:
            if npc.rect().colliderect(
                    pygame.Rect(int(self.player.x - 20), int(self.player.y - 40), 40, 80)):
                self._talk_npc = npc
                if self._begin_quest_flow(npc):
                    return
                self.ui.show_dialog(npc.name, ["你好，冒险者！", "小心东边山丘上的怪物。",
                                               "攻击按 J，击败怪物可获得经验与掉落物。"])
                return

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
        """任务对话框按钮回调：yes / no / ok。"""
        flow = self._quest_flow
        if flow is None:
            self.ui.hide_quest()
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
        self._place_player_at_spawn()
        self._spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()

    # ── 传送门 / 地图切换 ──────────────────────────────────────────
    def _portal_at_feet(self) -> Optional[dict]:
        """回传玩家脚底重叠的白名单 type-2 传送门（供绘制提示 / 触发判断）。"""
        feet = self.player.y + settings.FEET_OFFSET
        pr = pygame.Rect(int(self.player.x - 12), int(feet - 12), 24, 24)
        for p in self.assets.portals:
            if p.get("type") != 2:
                continue
            tm = str(p.get("targetMap") or "")
            if tm not in settings.TRAVEL_MAPS:
                continue
            prt = pygame.Rect(int(p["x"]) - 14, int(p["y"]) - 14, 28, 28)
            if pr.colliderect(prt):
                return p
        return None

    def _check_portal(self) -> bool:
        """玩家站在 type-2 传送门上按住 ↑ 键才切图（与原版一致）。返回是否切图。"""
        if self._portal_cooldown > 0:
            self._portal_cooldown -= 1 / 60
            return False
        if not self.keys.up:
            return False
        p = self._portal_at_feet()
        if p is not None:
            self._enter_map(str(p["targetMap"]), p.get("targetName"))
            return True
        return False

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
        self._place_player_at_spawn()
        self._spawn_life()
        self.combat.drops.clear()
        self.combat.numbers.clear()
        self.combat.effects.clear()
        self.hits.clear()
        self._portal_cooldown = 0.8

        self.audio.play_bgm()
        self.panels.flash(self.assets.map_name())
        self._loading = False
        self._pending_map = None

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
            if self._check_portal():
                return

        # 掉出地图底部：回出生点并扣血（避免永远下坠）
        if self.player.y > self.assets.map_height + 80:
            self.player.damage(settings.FALL_OUT_DAMAGE)
            self.combat.numbers.append(DamageNumber(
                self.player.x, self.player.y - 40,
                settings.FALL_OUT_DAMAGE, (120, 180, 255)))
            self._place_player_at_spawn()

        # 攻击判定
        if self.player.attacking:
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
        # 移除已消失的怪物
        self.monsters = [m for m in self.monsters
                         if not (m.dead and m.remove_after <= 0)]
        self.combat.apply_mob_hits(self.player, self.hits)

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
        # 命中火花 / 升级特效（实体之上）
        self.combat.draw_effects(self.canvas, self.camera)
        # HUD / 面板 / 对话框 / 死亡
        self.ui.draw_hud(self.canvas, self.player, self.combat)
        self.panels.draw_quickslots(self.canvas, self.player)
        self.panels.draw(self.canvas, self.player, self.combat.meso)
        self.ui.draw_dialog(self.canvas)
        self.ui.draw_quest(self.canvas)
        self.ui.draw_death(self.canvas)

        # 2x 放大到窗口
        scaled = pygame.transform.scale(
            self.canvas, (settings.WINDOW_W, settings.WINDOW_H))
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()

    def _draw_loading(self) -> None:
        self.canvas.fill((0, 0, 0))
        font = pygame.font.Font(None, 48)
        dots = "." * (int(self._loading_timer * 3) % 4)
        text = font.render(f"载入中{dots}", True, (255, 255, 255))
        rect = text.get_rect(center=(settings.VIEW_W // 2, settings.VIEW_H // 2))
        self.canvas.blit(text, rect)
        hint_font = pygame.font.Font(None, 24)
        hint = hint_font.render("Loading map...", True, (160, 160, 160))
        hint_rect = hint.get_rect(center=(settings.VIEW_W // 2, settings.VIEW_H // 2 + 50))
        self.canvas.blit(hint, hint_rect)
        scaled = pygame.transform.scale(
            self.canvas, (settings.WINDOW_W, settings.WINDOW_H))
        self.screen.blit(scaled, (0, 0))
        pygame.display.flip()

    def _portal_frame_index(self, frames, t: float) -> int:
        """依累积秒数定位动画帧：每帧显示其 delay 毫秒时长（循环播放）。"""
        return Animation.frame_at(frames, t * 1000.0)

    def _draw_portals(self, surface) -> None:
        """画传送门：白名单内的 type-2 门用 WZ 原版 8 帧动画。"""
        frames = self.assets.portal_frames()
        if not frames:
            return
        idx = self._portal_frame_index(frames, self._portal_pulse)
        for p in self.assets.portals:
            if p.get("type") != 2:
                continue
            tm = str(p.get("targetMap") or "")
            if tm not in settings.TRAVEL_MAPS:
                continue
            sx, sy = self.camera.to_screen(p["x"], p["y"])
            surf, origin, _ = frames[idx]
            rect = surf.get_rect()
            rect.centerx = int(sx)
            rect.bottom = int(sy) + 2
            surface.blit(surf, rect.topleft)
            # 玩家站在传送门上时画金色高亮光环
            if self._portal_at_feet() is p:
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
            self._handle_input()
            self._update(dt)
            self._draw()
        self._shutdown()

    def _shutdown(self) -> None:
        try:
            self.save_manager.flush(SaveManager.collect_data(
                self.player, self.combat, self.assets.map_id))
        except Exception:
            pass
        self.audio.close()
        self.assets.close()
        pygame.quit()
