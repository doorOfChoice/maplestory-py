# 枫之谷 v113 · 单机重制

用 Python + Pygame 复刻 MapleStory v113（台服）：直接读取官方 WZ 资产，重现地图、怪物、NPC、任务、技能与背包。

> 只`读取` `wz/` 下的官方资产，任何时候都`不写入`、不修改。

## 还原

- **原生素材**：自制 `wzpy` 函数库解密、解析、解码官方封存，地图 / 怪物 / 角色 / NPC 全部取自原版图片，无重绘、无魔改。
- **数据驱动世界**：地图连通由 WZ portal 的 `tm/tn` 决定，从弓箭手村可漫游到 200+ 张相连地图；普通门、隐藏门、同图瞬移门全类型还原；切图后台预热缓存不卡顿。
- **类 MS 物理**：foothold 平台、绳梯攀爬、蹬墙跳、下跳穿板、落地吸附，还原原版手感。
- **战斗**：近战与弓弩弹道、技能施放、buff / 暴击、怪物 AI、伤害飘字与击退。
- **完整玩法**：任务与 NPC 对话（非模态）、原版素材的背包 / 技能 / 任务 / 状态面板、商店与仓库、强化卷轴、每 60 秒自动存档。

## 画面

| 欢迎画面 | 弓箭手村东部小山 |
|:--:|:--:|
| ![欢迎画面](screenshots/welcome.png) | ![游戏画面](screenshots/gameplay.png) |

| | |
|:--:|:--:|
| ![背包](screenshots/inventory.png) | ![技能栏](screenshots/skills.png) |
| ![任务日志](screenshots/quests.png) | ![全貌](screenshots/overview.png) |

截图可用 `uv run python src/scripts/capture_screenshots.py` 重新生成。

## 运行

需要 Python ≥ 3.12、`uv`，以及 v113（台服）WZ 文件（仓库不提供）：

1. 从 [MapleStoryUnity/wzData](https://github.com/MapleStoryUnity/wzData) 下载 TMS **113** 压缩包
2. 把全部 `.wz` 文件放进项目根目录 `wz/`（`wz/` 目录入库、里头的 WZ 已 gitignore）

```bash
uv sync                      # 安装依赖
uv run python -m game.main   # 启动游戏
```

## 操作

| 按键 | 动作 |
|:--|:--|
| `←` `→` | 移动（`A` 攻击） |
| `Space` | 跳跃；绳梯上跳离 |
| `↑` `↓` | 爬绳梯 / 下绳梯；站传送门上 `↑` 切图；`↓`+`Space` 下跳 |
| `1`～`9` `Z` `F` | 技能 / 拾取 / 喝药 |
| `I` `K` `Q` `B` `M` | 背包 / 技能 / 任务 / 状态 / 小地图 |
| `Enter` | 与 NPC 对话（`Enter`/`Esc` 关闭） |
| `R` | 死亡后回出生点复活 |

## 结构

```
src/wzpy/   函数库：WZ 解析 / 解密 / 渲染器（可独立复用）
src/game/   应用层：循环 / 物理 / 实体 / 战斗 / 技能 / 背包 / 任务 / UI / 存档
src/tests/  pytest 整合测试（合成数据，无需 WZ 文件）
```

开发遵循 TDD（见 `.agents/skills/tdd/`），测试不依赖环境中的 WZ 文件。

## 声明

个人学习用途的 MapleStory v113 重制示范，不附带任何 WZ 资产。MapleStory 及素材版权归 Nexon / Wizet 所有。
