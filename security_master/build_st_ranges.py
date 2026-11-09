"""T-201：从 ST 事件表生成按日 ST 区间（近似）。

输入：研究/st_event_table/event_table.csv
输出：st_ranges.csv（code, start, end, type_start, end_reason, days, open）

规则（状态机，按代码+日期排序）：
  - imp_delist / imp_other → 开区间；若已开，记录升级（imp_other→imp_delist）
  - rem_delist_keep_other → 撤销退市但仍 ST，区间继续，type 改为 other
  - rem_delist / rem_other → 闭区间
  - 未闭合的区间 open=1（截至 2026-11-08 仍在 ST）
局限：2016 年前无线索；只看标题，不分财务/违规类。
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # 研究/
SRC = ROOT / "st_event_table" / "event_table.csv"
OUT = Path(__file__).resolve().parent / "st_ranges.csv"

IMP = {"imp_delist", "imp_other"}
REM = {"rem_delist", "rem_other"}


def main() -> int:
    rows = list(csv.DictReader(SRC.open(encoding="utf-8-sig")))
    by_code: dict[str, list[dict]] = {}
    for r in rows:
        by_code.setdefault(r["code"], []).append(r)

    out = []
    for code, evs in by_code.items():
        evs.sort(key=lambda x: x["event_date"])
        cur = None
        for e in evs:
            t, d = e["type"], e["event_date"]
            if t in IMP:
                if cur is None:
                    cur = {"code": code, "name": e["name"], "start": d, "type_start": t}
                elif t == "imp_delist" and cur["type_start"] == "imp_other":
                    cur["type_start"] = "imp_delist"          # 升级，不改起点
                # 同期重复实施：忽略
            elif t == "rem_delist_keep_other":
                if cur is not None:
                    cur["type_start"] = "other_after_rem_delist"
            elif t in REM:
                if cur is not None:
                    cur["end"] = d
                    cur["end_reason"] = t
                    out.append(cur)
                    cur = None
                # 无开区间的孤立撤销：忽略（可能 2016 前已实施）
        if cur is not None:
            cur["end"] = ""
            cur["end_reason"] = "still_st"
            out.append(cur)

    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "name", "start", "end", "type_start", "end_reason", "days", "open"])
        for r in sorted(out, key=lambda x: (x["start"], x["code"])):
            if r["end"]:
                days = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
                op = 0
            else:
                days = (date(2026, 11, 8) - date.fromisoformat(r["start"])).days
                op = 1
            w.writerow([r["code"], r["name"], r["start"], r["end"], r["type_start"],
                        r["end_reason"], days, op])

    opens = sum(1 for r in out if not r["end"])
    print(f"ranges={len(out)} open={opens} codes={len(by_code)} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())