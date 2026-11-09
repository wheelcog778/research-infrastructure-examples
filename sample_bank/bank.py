"""样本库（sample bank）· 只读摄取产品每日输出 + 事后打标签。

用途：把「软件每天看到什么、选了什么、为什么打回、后来涨没涨」存成可复算的面板，
供后续迭代与新 alpha 研究使用。不修改产品本体，只读 reports/ 下的产物。

子命令：
  python bank.py init
  python bank.py ingest            # 扫 product/reports/<date>/<time>_<mode>/pool.csv + summary.txt
  python bank.py label             # 用腾讯前复权日线补 T+1..T+60 收益
  python bank.py report            # 一页统计：覆盖、分数-收益关系、阻断频次

库：研究/sample_bank/sample_bank.db（SQLite）
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "sample_bank.db"
REPORTS = Path("~/product/reports")
CACHE = ROOT / "_kline_cache.jsonl"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY,
  run_date TEXT, run_time TEXT, mode TEXT,
  product_version TEXT, market_line TEXT,
  funnel TEXT, committee TEXT,
  n_rows INTEGER, src_dir TEXT, src_sha TEXT, ingested_at TEXT
);
CREATE TABLE IF NOT EXISTS samples(
  run_id TEXT, code TEXT, name TEXT, industry TEXT, score REAL, category TEXT,
  steps INTEGER, price REAL, change_pct REAL, vwap REAL, vwap_dev REAL,
  stop REAL, stop_dist REAL, rr REAL, leg_gain REAL, vol_peak REAL, amount_yi REAL,
  verdict TEXT, rounds TEXT, reasons TEXT,
  PRIMARY KEY(run_id, code)
);
CREATE TABLE IF NOT EXISTS labels(
  run_id TEXT, code TEXT, entry_date TEXT,
  ret1 REAL, ret5 REAL, ret10 REAL, ret20 REAL, ret60 REAL,
  ex5 REAL, ex20 REAL,
  flag TEXT, src TEXT, labeled_at TEXT,
  PRIMARY KEY(run_id, code)
);
CREATE TABLE IF NOT EXISTS daily_memory(
  date TEXT PRIMARY KEY, regime TEXT, funnel TEXT, committee TEXT,
  n_pool INTEGER, n_pass INTEGER, n_block INTEGER, note TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_notes(
  run_id TEXT, code TEXT, speaker TEXT, text TEXT
);
"""


def conn():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript(SCHEMA)
    return c


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def parse_summary(text: str) -> dict:
    out = {"market_line": "", "funnel": "", "committee": ""}
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("大盘定档"):
            out["market_line"] = s
        elif s.startswith("漏斗"):
            out["funnel"] = s
        elif s.startswith("委员会"):
            out["committee"] = s
    return out


def fnum(x, default=None):
    try:
        v = float(str(x).replace("%", "").strip())
        return v
    except Exception:
        return default


def parse_notes(text: str) -> list:
    notes, cur = [], None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"·\s*(.+?)\((\d{6})\)", s)
        if m:
            cur = m.group(2)
            continue
        m2 = re.match(r"(多|空|审)：(.*)", s)
        if m2 and cur:
            notes.append((cur, m2.group(1), m2.group(2)))
    return notes


def ingest() -> int:
    c = conn()
    n_runs = n_rows = 0
    for run_dir in sorted(REPORTS.glob("*/*/")):
        pool = run_dir / "pool.csv"
        if not pool.exists():
            continue
        date_part, time_mode = run_dir.parent.name, run_dir.name
        m = re.match(r"(\d{4,6})_(\w+)(?:-\d+)?$", time_mode)
        if not m:
            continue
        hhmmss, mode = m.group(1), m.group(2)
        run_id = f"{date_part}T{hhmmss}_{mode}"
        summary = run_dir / "summary.txt"
        stext = summary.read_text(encoding="utf-8", errors="ignore") if summary.exists() else ""
        sm = parse_summary(stext)
        src_sha = sha(pool) + ":" + (sha(summary) if summary.exists() else "")
        rows = []
        with pool.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows.append((
                    run_id, r.get("代码", ""), r.get("名称", ""), r.get("赛道", ""),
                    fnum(r.get("决胜分")), r.get("分类", ""),
                    int(fnum(r.get("五格"), 0) or 0), fnum(r.get("现价")), fnum(r.get("涨跌%")),
                    fnum(r.get("VWAP")), fnum(r.get("VWAP偏离%")), fnum(r.get("止损")),
                    fnum(r.get("止损距离%")), fnum(r.get("盈亏比")), fnum(r.get("前波涨幅%")),
                    fnum(r.get("回调量/峰值")), fnum(r.get("成交额(亿)")),
                    r.get("委员会", "") or "未审", r.get("轮次", ""), r.get("依据", ""),
                ))
        c.execute(
            "INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, date_part, hhmmss, mode,
             "v1.5.x" if date_part >= "2026-11-01" else "v1.3.x",
             sm.get("market_line", ""), sm.get("funnel", ""), sm.get("committee", ""),
             len(rows), str(run_dir), src_sha, datetime.now().isoformat(timespec="seconds")),
        )
        c.executemany("INSERT OR REPLACE INTO samples VALUES(" + ",".join(["?"] * 20) + ")", rows)
        c.execute("DELETE FROM agent_notes WHERE run_id=?", (run_id,))
        for code_, spk, txt in parse_notes(stext):
            c.execute("INSERT INTO agent_notes VALUES(?,?,?,?)", (run_id, code_, spk, txt))
        # daily memory：同一天取最后一次 run 汇总
        n_pass = 0
        if sm.get("committee"):
            mm = re.search(r"通过\s*(\d+).*?条件通过\s*(\d+).*?打回淘汰\s*(\d+)", sm["committee"])
            if mm:
                n_pass = int(mm.group(1)) + int(mm.group(2))
        n_block = sum(1 for r in rows if r[17] == "打回淘汰")
        c.execute(
            "INSERT OR REPLACE INTO daily_memory VALUES(?,?,?,?,?,?,?,?,?)",
            (date_part, sm.get("market_line", ""), sm.get("funnel", ""), sm.get("committee", ""),
             len(rows), n_pass, n_block, "", datetime.now().isoformat(timespec="seconds")),
        )
        n_runs += 1
        n_rows += len(rows)
        print(f"  {run_id}: {len(rows)} rows  {sm.get('funnel','')[:40]}")
    c.commit()
    print(f"ingested runs={n_runs} rows={n_rows} -> {DB}")
    return 0


def http_json(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as fh:
                return json.loads(fh.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def fetch_kline(code: str, start: str, end: str = "2026-11-08"):
    if code == "000300":
        sym = "sh000300"
    else:
        sym = ("sh" if code.startswith("6") else "sz") + code
    q = urllib.parse.quote(f"{sym},day,{start},{end},640,qfq")
    j = http_json("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=" + q)
    node = (j.get("data") or {}).get(sym) or {}
    rows = node.get("qfqday") or node.get("day") or []
    return [[r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4])] for r in rows]  # date, open, close, high, low


def load_cache() -> dict:
    out = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                o = json.loads(line)
                out[o["code"]] = o["bars"]
    return out


def label() -> int:
    c = conn()
    cache = load_cache()
    todo = c.execute(
        "SELECT s.run_id, s.code, r.run_date FROM samples s JOIN runs r USING(run_id) "
        "LEFT JOIN labels l ON l.run_id=s.run_id AND l.code=s.code WHERE l.code IS NULL"
    ).fetchall()
    by_code = {}
    for rid, code, d in todo:
        by_code.setdefault(code, []).append((rid, d))
    print(f"to label: {len(todo)} rows, {len(by_code)} codes")
    idx = None
    try:
        idx = fetch_kline("000300", "2026-09-01")
    except Exception as e:
        print("WARN index unavailable:", e)
    idx_map = {r[0]: r for r in idx} if idx else {}
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    with CACHE.open("a", encoding="utf-8") as fh:
        for i, (code, items) in enumerate(sorted(by_code.items()), 1):
            if code not in cache:
                try:
                    bars = fetch_kline(code, "2026-09-01")
                    cache[code] = bars
                    fh.write(json.dumps({"code": code, "bars": bars}, ensure_ascii=False) + "\n")
                    fh.flush()
                    time.sleep(0.12)
                except Exception as e:
                    print("  fail", code, e)
                    continue
            bars = cache[code]
            bmap = {b[0]: b for b in bars}
            for rid, d in items:
                after = sorted(x for x in bmap if x > d)
                if not after:
                    continue
                e = after[0]
                ent = bmap[e]
                flag = "suspend" if not bars else "ok"
                if ent[3] == ent[4]:
                    flag = "one_word"
                def ret(k):
                    tgt = after[k] if len(after) > k else None
                    if not tgt:
                        return None
                    ex = bmap[tgt]
                    return ex[2] / ent[1] - 1 if ent[1] else None   # T+1 开盘 -> T+1+k 收盘
                def ex(k):
                    if not idx_map:
                        return None
                    tgt = after[k] if len(after) > k else None
                    if not tgt or tgt not in idx_map:
                        return None
                    ib = [x for x in sorted(idx_map) if x > d]
                    if len(ib) <= k:
                        return None
                    r0, r1 = idx_map[ib[0]], idx_map[ib[k]]
                    return (ret(k) or 0) - (r1[2] / r0[1] - 1)
                c.execute(
                    "INSERT OR REPLACE INTO labels VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, code, e, ret(0), ret(4), ret(9), ret(19), ret(59),
                     ex(4), ex(19), flag, "tencent_qfq", now),
                )
                n += 1
            if i % 20 == 0:
                print(f"  {i}/{len(by_code)} codes")
    c.commit()
    print(f"labeled rows={n}")
    return 0


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    if len(xs) < 5:
        return None
    a, b = rank(xs), rank(ys)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = sum((v - ma) ** 2 for v in a) ** 0.5
    db = sum((v - mb) ** 2 for v in b) ** 0.5
    return num / (da * db) if da and db else None


def report() -> int:
    c = conn()
    runs = c.execute("SELECT run_id, run_date, n_rows, funnel, committee FROM runs ORDER BY run_date").fetchall()
    print(f"runs={len(runs)}  samples={c.execute('SELECT COUNT(*) FROM samples').fetchone()[0]}  "
          f"labels={c.execute('SELECT COUNT(*) FROM labels').fetchone()[0]}")
    for r in runs:
        print(f"  {r[0]}  rows={r[2]}  {r[3][:46]}")
    print("\n按日去重（每天只取最后一次 run，避免同一截面重复计数）：")
    for (d,) in c.execute("SELECT DISTINCT run_date FROM runs ORDER BY run_date").fetchall():
        rid = c.execute("SELECT run_id FROM runs WHERE run_date=? ORDER BY run_time DESC LIMIT 1", (d,)).fetchone()[0]
        parts = []
        for col in ("ret1", "ret5", "ret10", "ret20"):
            rows = c.execute(
                f"SELECT s.score, l.{col} FROM samples s JOIN labels l USING(run_id, code) "
                f"WHERE s.run_id=? AND l.{col} IS NOT NULL", (rid,)).fetchall()
            xs = [r[0] for r in rows if r[0] is not None]
            ys = [r[1] for r in rows]
            ic = spearman(xs, ys)
            parts.append(f"{col} n={len(xs)} IC={'-' if ic is None else round(ic,3)}")
        print(f"  {d}  {rid}  " + "  ".join(parts))

    print("\n分数与前瞻收益（同一 run 内 Spearman，n>=5）：")
    for k, col in [(1, "ret1"), (5, "ret5"), (10, "ret10"), (20, "ret20")]:
        ics = []
        for (rid,) in c.execute("SELECT run_id FROM runs").fetchall():
            rows = c.execute(
                f"SELECT s.score, l.{col} FROM samples s JOIN labels l USING(run_id, code) "
                "WHERE s.run_id=? AND l." + col + " IS NOT NULL", (rid,)).fetchall()
            xs = [r[0] for r in rows if r[0] is not None]
            ys = [r[1] for r in rows]
            ics.append((rid, len(xs), spearman(xs, ys)))
        for rid, n, ic in ics:
            if n >= 5:
                print(f"  {col:5s} {rid}  n={n}  IC={ic if ic is None else round(ic,3)}")
    print("\n委员会判定分布：")
    for row in c.execute("SELECT verdict, COUNT(*) FROM samples GROUP BY verdict ORDER BY 2 DESC"):
        print(f"  {row[0] or '(空)':8s} {row[1]}")
    print("\n覆盖：")
    for row in c.execute("SELECT run_date, COUNT(DISTINCT code), SUM(CASE WHEN l.code IS NOT NULL THEN 1 ELSE 0 END) "
                         "FROM samples s JOIN runs r USING(run_id) LEFT JOIN labels l USING(run_id, code) "
                         "GROUP BY run_date"):
        print(f"  {row[0]}  codes={row[1]}  labeled={row[2]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "ingest", "label", "report"])
    a = ap.parse_args()
    if a.cmd == "init":
        conn().commit()
        print("db ready", DB)
        return 0
    return {"ingest": ingest, "label": label, "report": report}[a.cmd]()


if __name__ == "__main__":
    raise SystemExit(main())