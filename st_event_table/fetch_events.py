"""ST / 风险警示事件表 · 数据闸（只抓公告，不跑收益）。

用途：回答「2016–2026 到底有多少个可用的实施/撤销事件」，决定 ST 线开不开。
边界：只读公开公告接口；不改产品；不写任何收益结论。

输出：
  research/st_event_table/raw/<key>_<plate>.jsonl
  research/st_event_table/event_table.csv
  research/st_event_table/summary.json
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
RAW = ROOT / "raw"
URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
HEAD = {"User-Agent": "Mozilla/5.0",
        "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"}
KEYS = {
    "实施退市风险警示": "imp_delist",
    "实施其他风险警示": "imp_other",
    "撤销退市风险警示": "rem_delist",
    "撤销其他风险警示": "rem_other",
}
PLATES = ("szmb", "shmb")
SE = "2016-01-01~2026-11-08"
EXCLUDE = ("申请", "律师", "问询", "回复", "进展", "提示", "继续被实施", "部分撤销", "撤销部分", "事先告知",
           "存在被实施", "可能被实施", "将被实施", "存在被", "可能被", "风险提示")


def clean(t: str) -> str:
    return re.sub(r"<[^>]+>", "", t or "").strip()


def fetch(key: str, plate: str) -> list[dict]:
    out, page = [], 1
    while True:
        data = {
            "pageNum": page, "pageSize": 30, "column": "szse", "tabName": "fulltext",
            "plate": plate, "stock": "", "searchkey": key, "secdate": "", "tdate": "",
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
                time.sleep(2)
        anns = j.get("announcements") or []
        total = j.get("totalAnnouncement") or 0
        for a in anns:
            out.append({
                "code": a.get("secCode") or "",
                "name": a.get("secName") or "",
                "title": clean(a.get("announcementTitle") or ""),
                "time": a.get("announcementTime"),
                "id": a.get("announcementId") or "",
                "key": key, "plate": plate,
            })
        if len(anns) < 30 or not anns:
            break
        page += 1
        if page > 300:
            print(f"  WARN page cap hit {key} {plate}", file=sys.stderr)
            break
        time.sleep(0.3)
    return out


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    rebuild = "--rebuild" in sys.argv
    allrows = []
    for key, tag in KEYS.items():
        for plate in PLATES:
            p = RAW / f"{tag}_{plate}.jsonl"
            if rebuild and p.exists():
                rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
                print(f"{key} {plate}: {len(rows)} (raw)", flush=True)
            else:
                rows = fetch(key, plate)
                with p.open("w", encoding="utf-8") as fh:
                    for r in rows:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"{key} {plate}: {len(rows)}", flush=True)
            allrows.extend(rows)

    kept = []
    for r in allrows:
        t = r["title"]
        if any(x in t for x in EXCLUDE):
            continue
        if not r["code"] or not r["time"]:
            continue
        r["date"] = time.strftime("%Y-%m-%d", time.localtime(r["time"] / 1000))
        kept.append(r)

    # 同 (code, key) 90 天内只留最早一条
    from datetime import date
    events, last = [], {}
    for r in sorted(kept, key=lambda x: (x["code"], x["key"], x["date"])):
        k = (r["code"], r["key"])
        prev = last.get(k)
        if prev is None or (date.fromisoformat(r["date"]) - date.fromisoformat(prev["date"])).days > 90:
            r["type"] = KEYS[r["key"]]
            if r["type"] == "rem_delist" and "继续实施" in r["title"]:
                r["type"] = "rem_delist_keep_other"
            events.append(r)
            last[k] = r

    events.sort(key=lambda x: (x["date"], x["code"], x["key"]))
    out = ROOT / "event_table.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "type", "event_date", "title", "announcement_id"])
        for r in events:
            w.writerow([r["code"], r["name"], r["type"], r["date"], r["title"], r["id"]])

    summary = {
        "raw_announcements": len(allrows),
        "after_title_filter": len(kept),
        "deduped_events": len(events),
        "by_type": {},
        "by_year": {},
    }
    for r in events:
        summary["by_type"][r["type"]] = summary["by_type"].get(r["type"], 0) + 1
        y = r["date"][:4]
        summary["by_year"][y] = summary["by_year"].get(y, 0) + 1
    (ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())