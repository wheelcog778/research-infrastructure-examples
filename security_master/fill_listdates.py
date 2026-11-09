"""T-201：补齐 listdates.json（腾讯失败 → 新浪兜底）。

新浪上限 1023 条：若返回 1023 条，说明该股至少上市 4 年，first 只是「下界」，
字段 src=sina_capped 标记；返回 <1023 条时 first 视为上市首日（准确）。
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "listdates.json"
UA = {"User-Agent": "Mozilla/5.0"}


def mkt(code: str) -> str:
    return "sh" if code.startswith(("6", "9")) else "sz"


def tx(code: str) -> tuple[str | None, int, str]:
    url = ("https://ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={mkt(code)}{code},day,2016-01-01,2026-11-08,900,qfq")
    j = requests.get(url, headers=UA, timeout=15).json()
    d = (j.get("data") or {}).get(f"{mkt(code)}{code}") or {}
    rows = d.get("qfqday") or d.get("day") or []
    if not rows:
        return None, 0, "tx_empty"
    return rows[0][0], len(rows), "tx"


def sina(code: str) -> tuple[str | None, int, str]:
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           f"CN_MarketData.getKLineData?symbol={mkt(code)}{code}&scale=240&ma=no&datalen=1023")
    j = requests.get(url, headers=UA, timeout=20).json()
    if not isinstance(j, list) or not j:
        return None, 0, "sina_empty"
    return j[0]["day"], len(j), ("sina" if len(j) < 1023 else "sina_capped")


def work(code: str) -> tuple[str, dict]:
    try:
        d, n, src = tx(code)
        if d:
            return code, {"first": d, "n": n, "src": src}
    except Exception:  # noqa: BLE001
        pass
    try:
        d, n, src = sina(code)
        return code, {"first": d, "n": n, "src": src}
    except Exception as e:  # noqa: BLE001
        return code, {"first": None, "n": 0, "src": "fail", "err": str(e)[:60]}


def main() -> int:
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    todo = [c for c, v in cache.items() if not v.get("first")]
    print("todo", len(todo), flush=True)
    t0 = time.time()
    ok = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        for i, f in enumerate(as_completed(futs), 1):
            code, rec = f.result()
            cache[code] = rec
            ok += 1 if rec.get("first") else 0
            if i % 20 == 0 or i == len(todo):
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"{i}/{len(todo)} ok={ok} {int(time.time()-t0)}s", flush=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    print(Counter(v.get("src") for v in cache.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())