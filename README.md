# MapleStory v113 · pygame 单机重制

以 Python + pygame 重制 MapleStory v113（全球版，EMS 资产）的单机版：直接读取官方 WZ 封存，重现地图场景、怪物、NPC、任务、技能与背包系统。

> 本项目只`读取` WZ 资产，任何时候都`不写入` `113/` 文件夹。

## 游戏截图

| | |
|:--:|:--:|
| ![欢迎画面](screenshots/welcome.png) | ![游戏画面](screenshots/gameplay.png) |
| 开场欢迎对话 | 弓箭手村东部小山实机画面 |
| ![背包](screenshots/inventory.png) | ![技能栏](screenshots/skills.png) |
| 道具栏（原版 UI 素材） | 技能栏 |
| ![任务日志](screenshots/quests.png) | ![全貌](screenshots/overview.png) |
| 任务日志（含目标 NPC） | 关闭面板后的完整画面 |

截图可执行 `uv run python capture_screenshots.py` 重新生成至 `screenshots/`。

## 功能特色

- **WZ 资产解析**（自制 `wzpy` 函数库）：解密、属性树、图片解码，提供 Map / Mob / Character / NPC 渲染器与 JSON 导出
- **异步地图加载**：切图时于背景线程预热素材缓存，主线程不卡顿
- **类 MS 三层物理**：foothold 平台、梯/绳、蹬墙跳、下跳穿板、落地吸附
- **即时战斗**：近战攻击、技能施放（1/2 快捷）、怪物 AI（搜索/追踪/多层）、伤害数字与击退动作
- **任务系统**：Quest.wz 解析、非模态对话、NPC 任务灯泡、任务日志（杀怪／收集目标）
- **存档系统**：每 60 秒自动存档 + 关闭时写入 `saves/save.json`，重开自动接续进度
- **原版 UI**：道具栏 / 技能栏 / 任务日志 / 聊天框皆以 WZ UI 素材重绘，非模态对话框不暂停世界

## 需求

- Python ≥ 3.12
- 包管理：`uv`
- MapleStory v113（EMS）WZ 文件放在项目根目录的 `113/`（已 gitignore，需自行提供）

## 安装与执行

```bash
uv sync            # 安装依赖（含 dev 组）
uv run python -m game.main   # 启动游戏
uv run pytest      # 跑测试
```

## 操作说明

| 按键 | 动作 |
|:--|:--|
| `A` / `D`（或 `←` / `→`） | 移动 |
| `Space` | 跳跃；绳/梯上按 `Space` 跳离 |
| `W` / `↑` | 爬绳／爬梯 |
| `S` + `Space` | 空中下跳穿板 |
| `J` | 攻击 |
| `1` / `2` | 施放技能 |
| `F` | 使用药水 |
| `I` / `K` / `Q` | 道具栏 / 技能栏 / 任务日志 |
| `Enter` | 与 NPC 对话（`Enter` / `Esc` 关闭非模态对话框） |
| `↑` | 站上发光传送门切换地图 |
| `R` | 死亡后回出生点复活 |

## 项目结构

```
wzpy/      函数库层：WZ 解析、解密、渲染器（可独立重复使用）
game/      应用层：游戏循环、物理、实体、战斗、技能、背包、任务、UI、存档
113/       WZ 原档（只读，未纳入版本控制）
screenshots/   README 用游戏截图
tests/      pytest 整合测试（合成数据，不需 WZ 文件）
```

## 开发指引

- 模块 docstring、类别说明与代码注释一律使用**简体中文**
- 常量集中于 `game/settings.py`；实体物理热点类别使用 `__slots__`
- 新功能或修 bug 依循 TDD（见 `.agents/skills/tdd/`）：透过公开接口写整合测试，不用 mock
- 测试不得依赖 `113/` 存在的环境，请以合成数据建构

## 授权与声明

- 本项目为个人学习用途的 MapleStory v113 重制示范，不附带任何 WZ 资产
- MapleStory 及其素材版权归 Nexon / Wizet 所有
