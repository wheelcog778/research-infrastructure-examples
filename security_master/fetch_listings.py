"""T-201：抓「上市公告书」得到上市日（只抓名单，不跑收益）。

口径：巨潮全文检索 上市公告书，沪深主板；排除增发/配股/可转债/补充/更正/英文。
输出：listings_raw.jsonl + listing_list.csv（code, name, list_date）
说明：公告日通常为上市日前 1 天或当天，误差 ±2 天，字段名 list_date 标注为「公告日近似」。
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "listings_raw.jsonl"
URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"}
PLATES = ("szmb", "shmb")
SE = "2016-01-01~2026-11-08"
KEY = "上市公告书"
MAIN_PREFIX = ("600", "601", "603", "605", "000", "001", "002", "003")
EXCLUDE = ("增发", "配股", "可转换", "可转债", "债券", "补充", "更正", "英文",
           "摘要", "提示", "持续督导", "保荐", "持续监督", "年度")


def clean(t: str) -> str:
    return re.sub(r"<[^>]+>", "", t or "").strip()


def fetch(plate: str) -> list[dict]:
    out, page = [], 1
    while True:
        data = {
            "pageNum": page, "pageSize": 30, "column": "szse", "tabName": "fulltext",
            "plate": plate, "stock": "", "searchkey": KEY, "secdate": "", "tdate": "",
            "category": "", "trade": "", "seDate": SE, "sortName": "", "sortType": "",
            "isHLtitle": "true",
        }
        for attempt in range(3):
            try:
                j = requests.post(URL, data=data, headers=HEAD, timeout=30).json()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(3)
        anns = j.get("announcements") or []
        for a in anns:
            out.append({"code": a.get("secCode") or "", "name": a.get("secName") or "",
                        "title": clean(a.get("announcementTitle") or ""),
                        "time": a.get("announcementTime"), "id": a.get("announcementId") or "",
                        "plate": plate})
        if len(anns) < 30 or not anns:
            break
        page += 1
        if page > 500:
            print(f"WARN page cap {plate}", file=sys.stderr)
            break
        time.sleep(0.25)
    return out


def main() -> int:
    rows = []
    for plate in PLATES:
        got = fetch(plate)
        print(f"{plate}: {len(got)}", flush=True)
        rows.extend(got)
    with RAW.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    kept = []
    for r in rows:
        t, code = r["title"], r["code"]
        if not code or len(code) != 6 or not code.startswith(MAIN_PREFIX) or not r["time"]:
            continue
        if "上市公告书" not in t:
            continue
        if any(x in t for x in EXCLUDE):
            continue
        r["date"] = time.strftime("%Y-%m-%d", time.localtime(r["time"] / 1000))
        kept.append(r)

    first: dict[str, dict] = {}
    for r in sorted(kept, key=lambda x: x["date"]):
        first.setdefault(r["code"], r)

    out = ROOT / "listing_list.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "list_announce_date", "title", "announcement_id"])
        for code, r in sorted(first.items()):
            w.writerow([code, r["name"], r["date"], r["title"], r["id"]])

    by_year: dict[str, int] = {}
    for r in first.values():
        by_year[r["date"][:4]] = by_year.get(r["date"][:4], 0) + 1
    print(json.dumps({"raw": len(rows), "after_filter": len(kept), "unique_codes": len(first),
                      "by_year": dict(sorted(by_year.items()))}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())