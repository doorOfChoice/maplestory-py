# AGENTS.md

本文件為開發者與 AI agent 共用的開發規範與程式碼導覽。改動程式碼前請先讀一遍，特別注意「樣式約定」與「測試規範」。

## 專案概覽

MapleStory v113 的 pygame 單機重製。遊戲直接讀取 `113/` 下的官方 WZ 資產（唯讀），由自製的 `wzpy` 函式庫解析、解密並渲染成 pygame 畫面。

- **Python ≥ 3.12**，套件管理用 `uv`
- **兩層架構**：
  - `wzpy/` —— 函式庫層：WZ 封存格式解析（解密、屬性樹、圖片解碼）、Map/Mob/Character 渲染器、JSON 匯出。可獨立重複使用。
  - `game/` —— 應用層：遊戲迴圈、物理、實體（玩家/怪物/NPC）、戰鬥、技能、背包、任務、UI。
- `113/`（WZ 原檔）已 gitignore，不提交。

## 常用指令

```bash
uv sync            # 安裝依賴（含 dev 群組）
uv run python -m game.main   # 啟動遊戲
uv run pytest      # 跑測試（testpaths = tests）
```

pyproject.toml 已設定 pytest 的 `pythonpath = ["."]` 與 `testpaths = ["tests"]`。

## 架構要點

### 資料流

```
WZ (.wz) → wzpy: WzFile.open → 解密 → 目錄樹 → 惰性屬性解析
        → Renderer (Map/Mob/Character) → PIL Image
        → game/assets.py: pil_to_surface 快取 → pygame Surface
        → 場景繪製（canvas → camera → display，固定 60 FPS）
```

### 遊戲迴圈（game/game.py）

每幀：`clock.tick(FPS)`（dt 上限 35ms 防物理隧穿）→ `_handle_input` → `_update(dt)`（玩家/怪物/戰鬥/相機）→ `_draw`（場景、UI、面板、對話、死亡畫面）。

### 關鍵設計決定

- **座標系統**：沿用 WZ 世界座標（y 向下為正），角色以 navel 為錨點，腳底 = navel + `FEET_OFFSET`（20px）
- **物理**（game/physics.py）：自製的 MS 式 foothold 行走系統，非回合制碰撞 —— 落地只發生在「腳底本幀跨越 foothold 線」時；爬牆只沿目前 foothold 的 prev/next 鏈；含梯子/繩、蹬牆跳
- **WZ 資產唯讀**：本專案只讀 `113/`，永不寫入
- **惰性解析**：WZ 影像首次存取才解析，並積極快取
- **非模態對話**：NPC/任務對話不暫停世界
- **常數集中**：所有物理/戰鬥/背包常數集中在 `game/settings.py`（含檔頭說明）

## 樣式約定

- **語言**：模組 docstring、類別說明、行內註解一律使用**繁體中文**；文件采佈局註解分隔（`# ── 區塊 ──`、`# ═══`）
- **`from __future__ import annotations`**：每個檔頂部必加
- **匯入順序**：標準函式庫 → 第三方 → 本專案，以空行分隔；`game/` 內用相對匯入（`from . import settings`），跨套件用絕對匯入（`from wzpy.wz_file import WzFile`）；禁用 `import *`
- **命名**：
  - 類別 `PascalCase`、函式/方法 `snake_case`、模組常數 `UPPER_SNAKE_CASE`、私有成員前綴單底線 `_`、檔名 `snake_case.py`
- **型別標註**：所有函式簽名皆應有型別標註與回傳型別；用 Python 3.10+ union 語法（`Optional[x]` 等）；可變預設值用 `dataclasses.field(default_factory=...)`；物理熱點類別用 `__slots__`
- **docstring**：模組層描述用途、座標約定、設計哲學（見 `game/settings.py`、`game/physics.py` 範例）
- **行長**：約 100~120 字元為上限，勿硬縮
- **縮排**：4 空格
- **不寫無說明註解**之外的程式碼註解過度鋪陳；除非必要，不加註解

## 測試規範

- 框架 **pytest**，整數整合式測試：透過**公開介面**驗證行為，不用 mock、不用 fixture、不探索私有成員（見 `.agents/skills/tdd/`）
- 檔名 `test_<feature>.py`、函式 `test_<行為描述>()`（純函式，不用類別）
- 測資用模組層輔助函式建構（如 `fh()`、`make()`）；一個測試一個邏輯斷言；測試彼此獨立、無共享狀態
- 純單元測試不需 WZ 檔（用合成 foothold 資料構造 `Physics`）
- 慣例注釋：測試 docstring 描述**被驗證的行為**（與程式碼註解同樣用繁體中文）
- 新功能或修 bug 時遵循 TDD：紅燈先寫、一次一片（vertical slice）、測公開 seam，先與使用者確認要測的 seam

## 資料與資產 (113/)

`113/` 下為 MapleStory v113 官方 WZ 封存（Map / Mob / Character / Npc / String / Sound ...），僅供本專案執行時讀取，**不得提交 Git**。改動需新增 WZ 依賴的測試時，不可假設 CI 環境有 `113/`，請以合成資料取代。