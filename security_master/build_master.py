"""T-201：合并证券主表 v0（在市 + 退市 + ST 区间标记）。

输入：
  研究/pool_v1/baseline/_cache/val_2025-09-30.json   在市快照（5,426 只）
  研究/security_master/verify_result.csv             232 只退市名单验证
  研究/security_master/st_ranges.csv                 632 个 ST 区间
输出：
  master.csv / master_summary.json / listdates.json（行情首条缓存，可断点续跑）

first_bar_date 口径：行情首条交易日（腾讯 qfq / 新浪兜底）。**不是上市日**——
腾讯只有 640/900 条、新浪 1023 条，老股首条只是「能回溯到的最早一天」。
只对「ST 事件股 + 退市股」抓，其余留空。
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "master.csv"
CACHE = ROOT / "listdates.json"
POOL = Path("~/研究/pool_v1/baseline/_cache/val_2025-09-30.json")
UA = {"User-Agent": "Mozilla/5.0"}

BOARDS = (
    (("600", "601", "603", "605"), "sh_main"),
    (("000", "001", "002", "003"), "sz_main"),
    (("300", "301"), "cyb"),
    (("688", "689"), "kcb"),
    (("200", "900"), "b_share"),
    (("8", "4", "9"), "bj"),
)


def board_of(code: str) -> str:
    for pre, name in BOARDS:
        if code.startswith(pre):
            return name
    return "other"


def mkt(code: str) -> str:
    return "sh" if code.startswith(("6", "9")) else "sz"


def first_bar(code: str) -> tuple[str | None, int]:
    url = ("https://ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={mkt(code)}{code},day,2016-01-01,2026-11-08,900,qfq")
    j = requests.get(url, headers=UA, timeout=15).json()
    d = (j.get("data") or {}).get(f"{mkt(code)}{code}") or {}
    rows = d.get("qfqday") or d.get("day") or []
    if not rows:
        return None, 0
    return rows[0][0], len(rows)


def main() -> int:
    live = json.loads(POOL.read_text(encoding="utf-8"))
    ver = {r["code"]: r for r in csv.DictReader((ROOT / "verify_result.csv").open(encoding="utf-8-sig"))}
    st_codes = {r["code"] for r in csv.DictReader((ROOT / "st_ranges.csv").open(encoding="utf-8-sig"))}

    doney: dict[str, dict] = {}
    if CACHE.exists():
        doney = json.loads(CACHE.read_text(encoding="utf-8"))

    rows = []
    for code, v in live.items():
        rows.append({"code": code, "name": v.get("name") or "", "status": "live",
                     "delist_date": "", "board": board_of(code),
                     "has_st_event": 1 if code in st_codes else 0, "verify_class": ""})
    for code, r in ver.items():
        if r["class"] == "C 疑似在市":
            continue
        rows.append({"code": code, "name": r["name"], "status": "delisted",
                     "delist_date": r["ann"], "board": board_of(code),
                     "has_st_event": 1 if code in st_codes else 0, "verify_class": r["class"]})

    # 只对事件股 + 退市股抓首条
    need = sorted({r["code"] for r in rows if r["has_st_event"] or r["status"] == "delisted"})
    todo = [c for c in need if c not in doney]
    print(f"rows={len(rows)} need_listdate={len(need)} todo={len(todo)}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(first_bar, c): c for c in todo}
        for i, f in enumerate(as_completed(futs), 1):
            code = futs[f]
            try:
                d, n = f.result()
                doney[code] = {"first": d, "n": n}
            except Exception as e:  # noqa: BLE001
                doney[code] = {"first": None, "n": 0, "err": str(e)[:60]}
            if i % 25 == 0 or i == len(todo):
                CACHE.write_text(json.dumps(doney, ensure_ascii=False), encoding="utf-8")
                print(f"{i}/{len(todo)} {int(time.time()-t0)}s", flush=True)
    CACHE.write_text(json.dumps(doney, ensure_ascii=False), encoding="utf-8")

    for r in rows:
        info = doney.get(r["code"]) or {}
        r["first_bar_date"] = info.get("first") or ""
        r["bars_cached"] = info.get("n") or ""

    rows.sort(key=lambda x: x["code"])
    fields = ["code", "name", "status", "board", "first_bar_date", "delist_date",
              "has_st_event", "verify_class", "bars_cached"]
    with MASTER.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    summary = {
        "total": len(rows),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_board": dict(Counter(r["board"] for r in rows)),
        "st_event_codes": sum(1 for r in rows if r["has_st_event"]),
        "with_first_bar": sum(1 for r in rows if r["first_bar_date"]),
        "delisted_a_share": sum(1 for r in rows if r["status"] == "delisted" and r["board"] not in ("b_share",)),
    }
    (ROOT / "master_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())