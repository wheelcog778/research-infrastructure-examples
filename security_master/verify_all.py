"""T-201：232 只「终止上市」名单逐只行情验证（并发版，可断点续跑）。

判据：
  A 可研究：腾讯返回 >=100 条，且末条距公告日 <= 400 天
  B 长期停牌：末条距公告日 > 400 天
  C 疑似在市：末条距今 < 60 天（公告说终止上市但股票还在交易）
  D 无行情 / E 样本过短（<100 条）
输出 verify_result.csv + verify_summary.json；每 10 只落盘。
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0"}
TODAY = date(2026, 11, 8)
OUT = ROOT / "verify_result.csv"
FIELDS = ["code", "name", "ann", "n", "first", "last", "gap_days", "class", "err"]


def mkt(code: str) -> str:
    return "sh" if code.startswith(("6", "9")) else "sz"


def kline(code: str) -> list[tuple[str, float]]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={mkt(code)}{code},day,2000-01-01,2026-11-08,900,qfq")
    j = requests.get(url, headers=UA, timeout=15).json()
    d = (j.get("data") or {}).get(f"{mkt(code)}{code}") or {}
    rows = d.get("qfqday") or d.get("day") or []
    return [(r[0], float(r[2])) for r in rows if len(r) >= 3]


def work(r: dict) -> dict:
    code, ann = r["code"], r["delist_announce_date"]
    try:
        ks = kline(code)
        err = ""
    except Exception as e:  # noqa: BLE001
        ks, err = [], f"{type(e).__name__}: {e}"[:80]
    last = ks[-1][0] if ks else None
    first = ks[0][0] if ks else None
    if not ks:
        cls, gap = "D 无行情", None
    else:
        gap = (date.fromisoformat(ann) - date.fromisoformat(last)).days
        if (TODAY - date.fromisoformat(last)).days < 60:
            cls = "C 疑似在市"
        elif gap > 400:
            cls = "B 长期停牌"
        elif len(ks) < 100:
            cls = "E 样本过短"
        else:
            cls = "A 可研究"
    return {"code": code, "name": r["name"], "ann": ann, "n": len(ks),
            "first": first, "last": last, "gap_days": gap, "class": cls, "err": err}


def dump(rows: list[dict], done: dict[str, dict]) -> None:
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            x = done.get(r["code"])
            if x:
                w.writerow({k: x.get(k, "") for k in FIELDS})


def main() -> int:
    rows = list(csv.DictReader((ROOT / "delisted_list.csv").open(encoding="utf-8-sig")))
    done: dict[str, dict] = {}
    if OUT.exists():
        for x in csv.DictReader(OUT.open(encoding="utf-8-sig")):
            done[x["code"]] = x
        print(f"resume: {len(done)} done", flush=True)
    todo = [r for r in rows if r["code"] not in done]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, r): r for r in todo}
        for i, f in enumerate(as_completed(futs), 1):
            done[futs[f]["code"]] = f.result()
            if i % 10 == 0 or i == len(todo):
                dump(rows, done)
                print(f"{i}/{len(todo)}  {int(time.time()-t0)}s", flush=True)
    dump(rows, done)

    vals = list(done.values())
    cnt = Counter(x["class"] for x in vals)
    summary = {"total": len(vals), "by_class": dict(cnt),
               "usable_codes": cnt.get("A 可研究", 0)}
    (ROOT / "verify_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())