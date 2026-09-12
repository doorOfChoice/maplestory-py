#!/usr/bin/env python3
"""从「冒险岛079小册子」抓取怪物掉落表，导出为 CSV。

数据源：https://mxd079.dvg.cn 的掉落速查接口：
    GET /api/drop-search.php?q=<mob_id>&detail=full
返回 JSON，``results[].drops[]`` 每行含 item.itemid / item.name 与
chance（百万分比，如 360000 = 36%）。

mob_id 列表来自 ``data/mob_ids.csv``（由本地 Mob.wz 解析得到）。输出
``data/mob_drops_079_full.csv``，列：mob_id, mob_name, item_id, item_name,
chance, chance_text, min, max, questid。079 库中不存在的怪物记一行
chance_text=NOT_IN_079。

脚本可断点续跑：已出现在输出 CSV 中的 mob_id 会被跳过，只抓取剩余部分；
请求失败的 mob_id 不落盘，下次重跑会重试。

用法（项目根目录）：
    uv run python src/scripts/import_drops_079.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
MOB_IDS_CSV = DATA_DIR / "mob_ids.csv"
OUT_CSV = DATA_DIR / "mob_drops_079_full.csv"

API_URL = "https://mxd079.dvg.cn/api/drop-search.php"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; maplestory-drops-import/1.0)",
}
FIELDS = ["mob_id", "mob_name", "item_id", "item_name", "chance",
          "chance_text", "min", "max", "questid"]
NOT_IN_079 = "NOT_IN_079"
REQUEST_INTERVAL = 0.15
MAX_RETRIES = 3


def load_mob_ids() -> list[int]:
    """从 data/mob_ids.csv 读出全部怪物 id。"""
    with MOB_IDS_CSV.open(newline="", encoding="utf-8") as f:
        return [int(row["mob_id"]) for row in csv.DictReader(f)]


def load_done() -> set[int]:
    """已抓取的 mob_id（含 NOT_IN_079 行）；用于断点续跑。"""
    if not OUT_CSV.exists():
        return set()
    with OUT_CSV.open(newline="", encoding="utf-8") as f:
        return {int(row["mob_id"]) for row in csv.DictReader(f)}


def fetch(mob_id: int) -> list[list]:
    """抓取单只怪物掉落，返回待写入的行；无记录返回 NOT_IN_079 行。"""
    url = API_URL + "?" + urllib.parse.urlencode(
        {"q": mob_id, "detail": "full", "pageSize": 24})
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.load(resp)
    if not payload.get("ok"):
        raise RuntimeError(payload.get("message") or "接口返回 ok=false")
    hit = next((m for m in payload.get("results", [])
               if int(m["mob"]["mobid"]) == mob_id), None)
    if hit is None:
        return [[mob_id, "", "", "", "", NOT_IN_079, "", "", ""]]
    name = hit["mob"].get("name", "")
    drops = hit.get("drops", [])
    if not drops:
        return [[mob_id, name, "", "", "", "", "", "", ""]]
    return [[mob_id, name, d["item"]["itemid"], d["item"].get("name", ""),
             d.get("chance", ""), d.get("chanceText", ""),
             d.get("min", ""), d.get("max", ""), d.get("questid", 0)]
            for d in drops]


def open_writer():
    """打开输出 CSV，首次写入表头。"""
    exists = OUT_CSV.exists()
    fp = OUT_CSV.open("a", newline="", encoding="utf-8")
    writer = csv.writer(fp)
    if not exists:
        writer.writerow(FIELDS)
    return fp, writer


def main() -> int:
    mob_ids = load_mob_ids()
    done = load_done()
    todo = [m for m in mob_ids if m not in done]
    print(f"共 {len(mob_ids)} 只，已完成 {len(done)} 只，待抓取 {len(todo)} 只")
    if not todo:
        print(f"无新增 → {OUT_CSV}")
        return 0

    fp, writer = open_writer()
    ok = no_match = failed = 0
    try:
        for i, mob_id in enumerate(todo, start=1):
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    rows = fetch(mob_id)
                    break
                except Exception as exc:  # noqa: BLE001 — 打印后重试
                    if attempt == MAX_RETRIES:
                        failed += 1
                        print(f"[{i}/{len(todo)}] {mob_id} 失败：{exc}")
                        rows = None
                    else:
                        time.sleep(REQUEST_INTERVAL * attempt)
            if rows is None:
                continue
            writer.writerows(rows)
            fp.flush()
            if rows[0][5] == NOT_IN_079:
                no_match += 1
            else:
                ok += 1
            if i % 50 == 0:
                print(f"[{i}/{len(todo)}] 成功 {ok} / 无记录 {no_match} / 失败 {failed}")
            time.sleep(REQUEST_INTERVAL)
    finally:
        fp.close()

    print(f"完成：成功 {ok}、无记录 {no_match}、失败 {failed} → {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
