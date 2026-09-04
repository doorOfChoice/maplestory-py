# 声明式链接展开 + takeover 让位 设计文档（talk() schema 增量）

- 日期：2026-09-04
- 状态：已实现
- 前置：`2026-09-04-lua-conversation-schema-design.md`（步骤图解释器，本增量在其上扩展）

## 1. 问题

步骤图解释器落地后，`npc/1012119.lua` 的任务链演示仍有三处不适：

1. **双份真相**：entries() 的 name/lvmin/Say 槽与 talk() 手写的 quests 表/闭包几乎重复；
2. **样板不消失**：接/交链接的 show/click 闭包、completable 工厂、busy/not_yet 兜底步
   每个 NPC 都要重写一遍；
3. **职能写死**：真实场景里商店 NPC「没任务直接开店、有任务才聊」，出租车「没任务
   直接展示传送」，但 talk() 一旦存在就无条件霸占对话。

## 2. 决策记录（与使用者逐轮确认）

| 决策点 | 选定 |
|---|---|
| 任务链去重 | 台词回归 Say 槽（accept_yes/complete_yes/complete_stop 双份用途：默认子会话 + talk 展开终态步） |
| 链接通用格式 | 单一 `links` 数组按 `type` 判别（与 entries() 判别式同构），否决独立 `chain`/`travel` 段 |
| 前置唯一来源 | QuestDef.prereq（字符串 qid 可用），数组顺序只决定显示次序 |
| 接管条件 | `takeover = "always"(缺省) / "on_business" / function`；「有生意」由宿主按展开结果判定，脚本零谓词 |
| 生意定义 | quest（可接 offer / 可交付）与 travel（有非当前图目的地）算；shop 与手写链接不算（角色/情调） |
| 让位去向 | 弃用脚本会话、回落既有默认路由（默认会话/直开商店/寒暄），任务进行中由默认会话「（进行中）」链接承接 |

## 3. 实现落点

- `src/game/systems/conversation.py`
  - `ConvServices{quest_defs, teleports, has_shop}`：控制器注入的展开数据源；
  - `Link.business`：生意标记；`ConversationDef.takeover`；
  - `_fold_step` 按 `type` 分流 → `_expand_quest/_expand_travel/_expand_shop`；
    展开同时注册 `<qid>_accepted/_rewarded/_notyet` 与默认 `busy` 步（脚本同名步优先）；
  - `Conversation.has_business()` / `yields_to_route()` 公开查询；
  - 缺省 `start` 约定：`greet` 优先，否则名字序第一个（Lua 表遍历序不定）。
- `src/game/npc_dialogue.py`：`_open_script_conv` 注入 services 并在 `yields_to_route()`
  时返回 False → 走既有默认路由链。
- `src/game/systems/lua_quests.py`：新增 `_prereq()`——数字 qid 保 int、其余保字符串；
  `QuestDef.prereq` 类型放宽（can_start 本就以 str(q) 比对）。
- `resources/content/npc/1012119.lua`：重写为纯数据（entries 带 prereq/Say 槽）+
  声明式 talk()（4×quest + shop + chat，takeover=on_business）。
- `resources/content/AGENTS.md`：会话定义/link 字段表、声明式链接一节、路由与 Say 槽说明。

## 4. 行为变化（有意为之）

1. 任务进行中且不可交付时，托德让位 → 默认路由展示「（进行中）+商店」列表（原演示为
   空任务链接的定制会话页）。
2. 「交付但不满足条件」文案从全体共用改为各任务自己的 complete_stop。
3. quest 链接点击直接接取/交付，无询问确认页（确认流仍属默认子会话）。

## 5. 测试

- 新增 `src/tests/test_typed_links.py`：合成 QuestDef（字符串 qid 前置）+ 内嵌 Lua，
  覆盖展开显隐/发奖跳步/travel 剔图与子集/shop 非生意/on_business 让位/prereq 翻译。
- `test_lua_talk_demo.py`：open_talk 注入 services；「已接取未凑齐」用例改测让位。
- 全量：485 passed；`test_projectile.py` 2 个失败为 HEAD 既有（与本次无关，stash 验证）。
