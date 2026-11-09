"""T-201：把 232 只「终止上市」公告名单逐只用行情验证，剔除假阳性与长期停牌。

判据：
  A 可研究：腾讯返回 >=100 条，且末条距公告日 <= 400 天
  B 长期停牌：末条距公告日 > 400 天（退市前已停牌，事件窗口不可用）
  C 疑似在市：末条距今 < 60 天（公告标题含终止上市但股票仍在交易）
输出 verify_result.csv + verify_summary.json
"""
from __future__ import annotations

import csv
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0"}
TODAY = date(2026, 11, 8)


def mkt(code: str) -> str:
    return "sh" if code.startswith(("6", "9")) else "sz"


def kline(code: str) -> list[tuple[str, float]]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={mkt(code)}{code},day,2000-01-01,2026-11-08,900,qfq")
    j = requests.get(url, headers=UA, timeout=20).json()
    d = (j.get("data") or {}).get(f"{mkt(code)}{code}") or {}
    rows = d.get("qfqday") or d.get("day") or []
    return [(r[0], float(r[2])) for r in rows if len(r) >= 3]


def main() -> int:
    rows = list(csv.DictReader((ROOT / "delisted_list.csv").open(encoding="utf-8-sig")))
    out = []
    for i, r in enumerate(rows, 1):
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
            elif gap is not None and gap > 400:
                cls = "B 长期停牌"
            elif len(ks) < 100:
                cls = "E 样本过短"
            else:
                cls = "A 可研究"
        out.append({"code": code, "name": r["name"], "ann": ann, "n": len(ks),
                    "first": first, "last": last, "gap_days": gap, "class": cls, "err": err})
        if i % 20 == 0 or i == len(rows):
            print(f"{i}/{len(rows)}", flush=True)
        time.sleep(0.3)

    with (ROOT / "verify_result.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    cnt = Counter(x["class"] for x in out)
    summary = {"total": len(out), "by_class": dict(cnt),
               "usable_codes": sum(1 for x in out if x["class"] == "A 可研究")}
    (ROOT / "verify_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())