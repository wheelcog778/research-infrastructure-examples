#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest —— 零依赖自检：语法 + sample_bank schema。

不碰仓库里的数据：schema 检查用临时库（monkeypatch bank.DB），跑完删掉。
用法：python selftest.py   （exit 0 = 全过 / 1 = 有失败）
"""
import ast
import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQUIRED = ["runs", "samples", "labels", "daily_memory", "agent_notes"]
results = []


def chk(name, ok, extra=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {extra}" if extra and not ok else ""))


def load_bank():
    spec = importlib.util.spec_from_file_location("bank_under_test", ROOT / "sample_bank" / "bank.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    py_files = sorted(p for p in ROOT.rglob("*.py") if "__pycache__" not in p.parts)
    bad = []
    for p in py_files:
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            bad.append(f"{p.relative_to(ROOT)}:{exc.lineno}")
    chk(f"语法：{len(py_files)} 个 .py 全部可解析", not bad, ", ".join(bad[:3]))

    tmp = tempfile.mkdtemp(prefix="rie_selftest_")
    db = os.path.join(tmp, "t.db")
    try:
        bank = load_bank()
        setattr(bank, "DB", Path(db))
        c = bank.conn()
        c.commit()
        c.close()
        con = sqlite3.connect(db)
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        missing = [t for t in REQUIRED if t not in have]
        chk("sample_bank schema：五张表齐全", not missing, f"缺 {missing}")
        chk("临时库已落盘且非空", os.path.getsize(db) > 0)
    finally:
        try:
            for name in os.listdir(tmp):
                os.remove(os.path.join(tmp, name))
            os.rmdir(tmp)
        except OSError:
            pass  # Windows 偶尔仍持有句柄；临时目录交给系统清理

    ok = all(results)
    print(f"selftest: {'PASS' if ok else 'FAIL'} {sum(results)}/{len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())