"""T-201：退市股行情可得性探针（只读公开接口，不写任何收益结论）。

对 delisted_list.csv 按年份分层抽 20 只，逐源测试能否取到退市前日线：
  S1 腾讯 fqkline（前复权）
  S2 腾讯 fqkline（不复权）
  S3 新浪 getKLineData
  S4 东财 push2his
输出 probe_result.json + 控制台摘要。
"""
from __future__ import annotations

import csv
import json
import random
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0"}


def mkt(code: str) -> str:
    return "sh" if code.startswith(("6", "9")) else "sz"


def em_secid(code: str) -> str:
    return ("1." if mkt(code) == "sh" else "0.") + code


def s1_tx_qfq(code: str) -> list[tuple[str, float]]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={mkt(code)}{code},day,2000-01-01,2026-11-08,900,qfq")
    j = requests.get(url, headers=UA, timeout=20).json()
    data = (j.get("data") or {}).get(f"{mkt(code)}{code}") or {}
    rows = data.get("qfqday") or data.get("day") or []
    return [(r[0], float(r[2])) for r in rows if len(r) >= 3]


def s2_tx_raw(code: str) -> list[tuple[str, float]]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={mkt(code)}{code},day,2000-01-01,2026-11-08,900,")
    j = requests.get(url, headers=UA, timeout=20).json()
    data = (j.get("data") or {}).get(f"{mkt(code)}{code}") or {}
    rows = data.get("day") or []
    return [(r[0], float(r[2])) for r in rows if len(r) >= 3]


def s3_sina(code: str) -> list[tuple[str, float]]:
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={mkt(code)}{code}&scale=240&ma=no&datalen=1023")
    j = requests.get(url, headers=UA, timeout=20).json()
    if not isinstance(j, list):
        return []
    return [(r["day"], float(r["close"])) for r in j if r.get("day")]


def s4_em(code: str) -> list[tuple[str, float]]:
    url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={em_secid(code)}&klt=101&fqt=1&beg=19900101&end=20500101"
           "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")
    j = requests.get(url, headers={**UA, "Referer": "https://quote.eastmoney.com/"}, timeout=20).json()
    kl = ((j.get("data") or {}).get("klines")) or []
    out = []
    for line in kl:
        p = line.split(",")
        if len(p) >= 3:
            out.append((p[0], float(p[2])))
    return out


def probe(fn, code: str) -> dict:
    t0 = time.time()
    try:
        rows = fn(code)
        err = ""
    except Exception as e:  # noqa: BLE001
        rows, err = [], f"{type(e).__name__}: {e}"[:160]
    return {"n": len(rows), "first": rows[0][0] if rows else None,
            "last": rows[-1][0] if rows else None,
            "err": err, "ms": int((time.time() - t0) * 1000)}


def main() -> int:
    rows = list(csv.DictReader((ROOT / "delisted_list.csv").open(encoding="utf-8-sig")))
    by_year: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_year[r["delist_announce_date"][:4]].append(r)

    rng = random.Random(20261109)
    sample = []
    for y in sorted(by_year):
        pool = sorted(by_year[y], key=lambda x: x["code"])
        rng.shuffle(pool)
        sample.extend(pool[:2])
    sample = sample[:20]

    out = []
    for r in sample:
        code, ann = r["code"], r["delist_announce_date"]
        rec = {"code": code, "name": r["name"], "ann": ann,
               "S1_tx_qfq": probe(s1_tx_qfq, code),
               "S2_tx_raw": probe(s2_tx_raw, code),
               "S3_sina": probe(s3_sina, code),
               "S4_em": probe(s4_em, code)}
        out.append(rec)
        print(f"{code} {r['name']:8s} ann={ann} "
              f"S1={rec['S1_tx_qfq']['n']:4d}({rec['S1_tx_qfq']['first']}~{rec['S1_tx_qfq']['last']}) "
              f"S2={rec['S2_tx_raw']['n']:4d} S3={rec['S3_sina']['n']:4d} S4={rec['S4_em']['n']:4d}"
              f"{' ERR:' + rec['S1_tx_qfq']['err'] if rec['S1_tx_qfq']['err'] else ''}", flush=True)
        time.sleep(0.4)

    (ROOT / "probe_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    agg = {}
    for k in ("S1_tx_qfq", "S2_tx_raw", "S3_sina", "S4_em"):
        ok = [x[k] for x in out if x[k]["n"] > 0]
        agg[k] = {"hit": len(ok), "of": len(out),
                  "median_n": sorted(s["n"] for s in ok)[len(ok) // 2] if ok else 0,
                  "cover_ann_minus_30d": sum(
                      1 for x in out if x[k]["last"] and
                      (date.fromisoformat(x["ann"]) - date.fromisoformat(x[k]["last"])).days <= 30)}
    print(json.dumps(agg, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())