"""T-201 前置：抓「终止上市」公告，得到真实退市股名单（只抓名单，不跑收益）。

输出：research/security_master/delisted_raw.jsonl + delisted_list.csv
口径：巨潮全文检索 searchkey=终止上市，沪深主板；剔除「可能/风险提示/事先告知」类。
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
RAW = ROOT / "delisted_raw.jsonl"
URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"}
PLATES = ("szmb", "shmb")
SE = "2016-01-01~2026-11-08"
KEY = "终止上市"
EXCLUDE = ("可能", "风险提示", "事先告知", "提示性", "进展", "问询", "回复",
           "申请", "听证", "复核", "整理期", "摘牌后", "股份确权", "转让")


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
            out.append({
                "code": a.get("secCode") or "",
                "name": a.get("secName") or "",
                "title": clean(a.get("announcementTitle") or ""),
                "time": a.get("announcementTime"),
                "id": a.get("announcementId") or "",
                "plate": plate,
            })
        if len(anns) < 30 or not anns:
            break
        page += 1
        if page > 400:
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
        if not code or not r["time"]:
            continue
        if KEY not in t:
            continue
        if any(x in t for x in EXCLUDE):
            continue
        r["date"] = time.strftime("%Y-%m-%d", time.localtime(r["time"] / 1000))
        kept.append(r)

    # 同一代码多份公告只留最早一条（首次宣布终止上市）
    first: dict[str, dict] = {}
    for r in sorted(kept, key=lambda x: x["date"]):
        first.setdefault(r["code"], r)

    out = ROOT / "delisted_list.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "delist_announce_date", "title", "announcement_id"])
        for code, r in sorted(first.items(), key=lambda kv: kv[1]["date"]):
            w.writerow([code, r["name"], r["date"], r["title"], r["id"]])

    by_year: dict[str, int] = {}
    for r in first.values():
        by_year[r["date"][:4]] = by_year.get(r["date"][:4], 0) + 1
    print(json.dumps({"raw": len(rows), "after_filter": len(kept),
                      "unique_codes": len(first), "by_year": dict(sorted(by_year.items()))},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())