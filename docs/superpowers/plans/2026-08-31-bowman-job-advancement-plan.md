# 执行计划：职业 / 转职系统（弓箭手 1 转 + 远程弹道）

- 关联 spec：`docs/superpowers/specs/2026-08-31-bowman-job-advancement-design.md`
- 方法论：TDD（红→绿，一次一片），遵循 `AGENTS.md`（公开 seam、合成数据、不 mock、不 fixture、单测不依赖 `wz/`）
- 运行：`uv run pytest`；启动 `uv run python -m game.main`

## 验收标准（Definition of Done）
1. 新手开局：`job=0`、无任何技能、快捷键栏空、只有 J 普攻（近战）。
2. 练到 Lv10 靠近赫麗娜 → 弹转职对话 → 确认后 `job=3000`、附赠被动满级、自动装备短弓、快捷键填入弓箭手主动技能。
3. 按数字键施放断魂箭/二连箭 → 播放 `shoot1` 拉弓动画 → 生成直线箭矢（`ball` 贴图）→ 飞行中命中怪结算伤害+`hit`特效，命中数受 `mobCount` 限制，二连箭出 2 支，超射程/寿命消失。
4. 未学/前置未满足/等级不足/SP 不足时 `learn` 失败。
5. 旧 v1 存档可载入（迁移为 job=0）；新存档保存 job 与快捷键。
6. `uv run pytest` 全绿；无 WZ 环境下合成单测仍全绿。

## 全局约定（先落地，供各任务引用）
`game/settings.py` 新增：
```
BOWMAN_JOB = 3000
BOWMAN_STARTER_BOW = "1452000"
BOWMAN_TRAINER_NPC = "1012100"
TRAINER_SPAWN_MAP = "100000000"
TRAINER_SPAWN = (x, y)          # 实现时选一个可站立 foothold 坐标
ARROW_SPEED = 900.0             # px/s，实机可调
ARROW_LIFETIME = 0.6            # s
```
删除：`SKILL_HOTKEYS`、`SKILL_UNLOCK_LEVEL`、`HOTKEY_SKILLS`（`SKILL_COOLDOWN` 保留为默认回退）。

---

## T1 — `resolve_skill_img` 纯函数 + `jobs.py` 骨架
**文件**：`game/jobs.py`(新)、`tests/test_jobs.py`(新)
**Red**：`test_resolve_skill_img_by_length()`
- `resolve_skill_img("3001004") == "300.img"`
- `resolve_skill_img("10001004") == "1000.img"`
**Green**：`jobs.py` 定义 `resolve_skill_img(skill_id)`：`len==8 → id[:4]+".img"`，否则 `id[:3]+".img"`。
**验证**：`uv run pytest tests/test_jobs.py`

## T2 — `assets.py` 去写死 + 箭矢/武器取图
**文件**：`game/assets.py`、`tests/test_jobs.py`（追加纯函数测试）
**Red**：`test_is_ranged_weapon()`：`is_ranged_weapon("1452000")` True、`"1462000"` True、`"1302000"` False。
**Green**：
- 新增 `is_ranged_weapon(item_id)`（int 前缀 145/146）。
- `skill_icon`(800)、`skill_effect_frames`(812)、`skill_hit_frames`(816) 把 `"100.img"` 换成 `resolve_skill_img(skill_id)`（`from .jobs import resolve_skill_img`）。
- 新增 `skill_ball_frames(skill_id)`：读 `Skill.wz/<img>/skill/<id>/ball/*` → `[(surface, origin, delay)]`（复用 `_decode_canvas_prop`/`_canvas_delay`）。
- `attack_pose(equips)`：若手持武器 `is_ranged_weapon` → 返回 `shoot1`(弓)/`shoot2`(弩)（用 `get_weapon_poses` 校验存在），否则维持 `ATTACK_POSES`。
**验证**：`uv run pytest tests/test_jobs.py`；`uv run python -m game.main` 不报错（战士技能消失属预期）。

## T3 — 职业注册表 + `can_advance` 纯函数
**文件**：`game/jobs.py`、`tests/test_jobs.py`
**Red**：
- `test_can_advance_requires_level()`：job0/lv9→False，job0/lv10→True。
- `test_can_advance_wrong_prejob()`：job=3000→False。
**Green**：
- `@dataclass JobDef(code,name,tree_imgs,passive_ids,advance_lv,trainer_npc,starter_weapon)`。
- `JOBS = {0: JobDef(0,"新手",[],[],0,None,None), 3000: JobDef(3000,"弓箭手",["300.img"],[3000000,3000001,3000002],10,1012100,"1452000")}`（职业名注明 WZ 出处注释）。
- `can_advance(player, jobdef) -> bool`：`player.job==0 and player.level>=jobdef.advance_lv`。
- `skill_ids_for_job(assets, code)`：遍历 `tree_imgs` 的 `skill/*`（integration，无单测，T9 冒烟）。
**验证**：`uv run pytest tests/test_jobs.py`

## T4 — `SkillBook` 职业驱动 + 四重门控 + `on_advance`
**文件**：`game/skills.py`、`tests/test_skill_gating.py`(新)
**Red**（注入合成 `SkillDef`，不碰 WZ）：
- `test_learn_blocked_by_sp()`：sp=0 → learn False。
- `test_learn_blocked_by_prereq()`：3001005 需 3001004≥1，未学 → False；学后 → True。
- `test_learn_blocked_by_charlevel()`：人物等级 < `CharLevel` → False。
- `test_learnable_excludes_invisible()`：`invisible` 被动不在 `learnable()`。
- `test_on_advance_grants_passives_and_hotkeys()`：`on_advance(bowman_def)` 后被动满级、主动技能进 `hotkeys`。
**Green**：
- `SkillBook(assets, job, defs=None)`：`defs` 为空时由 `skill_ids_for_job`+`load_skill_defs` 载入（WZ）；测试直接传 `defs`。
- 移除 `__init__` 里「1 级赠送首技能」。
- `learn(sid, player_level)`：SP>0 + 职业匹配 + `req` 满足 + `CharLevel` 满足 + 未满级。
- `load_skill_defs` 增解析 `req`/`CharLevel`/`invisible`；按 `resolve_skill_img` 分组读图（不再写死 `100.img`）。
- `on_advance(jobdef)`：`grant_passives`（`invisible`→满级）+ 重排 `hotkeys`。
- `hotkeys: dict[int,str]`；`to_dict/from_dict` 带上 `hotkeys`。
**验证**：`uv run pytest tests/test_skill_gating.py`

## T5 — `Player.job` / `advance_to` + 存档 v2 迁移
**文件**：`game/player.py`、`game/save_manager.py`、`tests/test_advance_state.py`(新)、`tests/test_save_manager.py`(改)
**Red**：
- `test_save_v2_roundtrip()`：`collect_data` 含 `player.job` 与 `skills.hotkeys`；`load` 后一致。
- `test_migrate_v1_defaults()`：喂 v1 dict（无 job）→ 迁移 `job=0`、不崩。
**Green**：
- `Player`：`job` 真实化；`SkillBook(assets, self.job)`；新增 `advance_to(code, assets)`：`self.job=code` → `self.skills=SkillBook(assets, code)` → `skills.on_advance(JOBS[code])` → 武器空则 `make_item(starter_weapon)` 装备 → `refresh_equips()`。
- `is_ranged()`：`job==BOWMAN_JOB and 手持 is_ranged_weapon`。
- `save_manager`：`version=2`，写 `job`+`hotkeys`；`load` 检测 v1 → 迁移。
**验证**：`uv run pytest tests/test_advance_state.py tests/test_save_manager.py`

## T6 — 导师注入 + 转职对话流程
**文件**：`game/game.py`、`game/settings.py`
**Red**：决策已在 T3 `can_advance` 覆盖；本任务为接线，用 T9 集成冒烟 + 手动验证。
**Green**：
- `_spawn_life`：当 `assets.map_id==TRAINER_SPAWN_MAP` 追加一个 `NPC(assets, {"id":BOWMAN_TRAINER_NPC,"x":..,"cy":..}, idx)`。
- `_try_talk`：命中导师且 `can_advance(player, JOBS[3000])` → `ui.show_quest("转职 · 弓箭手", [...], ["yes","no"])`，`_quest_flow={"stage":"advance"}`；`_quest_button("yes")` → `player.advance_to(3000, assets)` + `panels.flash("转职成功：弓箭手")`；等级不足 → 显示进度提示。
- 更新欢迎文案（新手→Lv10→找赫麗娜）。
**验证**：`uv run python -m game.main` 手动走转职；`uv run pytest`（无回归）。

## T7 — `Arrow` 弹道 + 远程起手接线
**文件**：`game/combat.py`、`game/game.py`、`game/player.py`、`tests/test_projectile.py`(新)
**Red**（合成 target：暴露 `rect()`/`take_hit()`/`x`/`cy`/`dead`）：
- `test_arrow_hits_once_and_flies_straight()`：一支箭穿过单个 target → `take_hit` 调用一次、y 不变（无重力）。
- `test_arrow_respects_mob_count()`：`mob_count=1` 时命中第二只不再结算。
- `test_spawn_arrows_bullet_count()`：`bulletCount=2` → `len(combat.arrows)==2`。
- `test_arrow_despawns_after_lifetime()`：`life` 耗尽 → 从列表移除。
**Green**：
- `Arrow` 类（`update(dt, monsters, combat)` 直线前进、相交结算、飘字、`hit` 特效、命中数/寿命/出界消失）。
- `Combat.arrows`、`spawn_arrows(player, skill_data)`（按 `bulletCount` 错峰、速度 `facing*ARROW_SPEED`、`frames=assets.skill_ball_frames(sid)`）、`update_arrows(dt, monsters)`、`draw` 画箭。
- `Game._update`：远程起手一次性生成箭（用 `player.attack_hit_applied` 同类的 `attack_projectile_spawned` 标志，避免重复生成）；每帧 `combat.update_arrows(dt, monsters)`。
- `Player.start_attack`：远程技能不再走近战命中，改由 Game 触发 `spawn_arrows`。
**验证**：`uv run pytest tests/test_projectile.py`；手动射箭。

## T8 — 动态快捷键 UI（技能窗 / 快捷栏 / 职业名）
**文件**：`game/panels.py`、`game/ui.py`
**Green**：
- 技能窗 `_draw_skills`：列表源改 `book.learnable()`（不再读 `settings.SKILL_HOTKEYS`）。
- 快捷栏 `draw_quickslots`：读 `player.skills.hotkeys`。
- 装备窗标题区显示职业名（`JOBS[player.job].name`）。
- `ui.draw_hud` 操作提示文案微调。
**验证**：手动开技能窗/快捷栏确认；`uv run pytest`。

## T9 — WZ 冒烟测试（有 WZ 才跑）
**文件**：`tests/test_wz_skill_smoke.py`(新)
**Green**：`@pytest.mark.skipif(not (WZ_DIR/"Skill.wz").exists())`：
- `skill_ids_for_job(assets, 3000)` 含 `"3001004"`。
- `load_skill_defs(assets, ["3001004"])` 的 `name == "断魂箭"`。
- `assets.skill_ball_frames("3001004")` 非空。
**验证**：`uv run pytest tests/test_wz_skill_smoke.py`（无 WZ 环境自动 skip）。

## T10 — 全量回归
- `uv run pytest`（全绿）
- `uv run python -m game.main`：新手零技能 → 练级 → 转职 → 射箭命中，存档重开接续。

---

## 依赖顺序
`T1 → T2 → T3 → T4 → T5 → {T6, T7} → T8 → T9 → T10`
（T6/T7 可在 T5 后并行；T7 的箭矢贴图依赖 T2 的 `skill_ball_frames`。）

## 风险与回退
- 导师坐标不当 → 卡位/看不见：T6 手动验证时微调 `TRAINER_SPAWN`。
- 箭矢手感：T7 后实机调 `ARROW_SPEED/ARROW_LIFETIME`。
- `SkillBook` 构造签名变更波及 `player.py` 两处调用：T4/T5 同步改。
- 远程「一次攻击一批箭」若漏加一次性标志会连发：T7 用 `attack_projectile_spawned` 防重。
