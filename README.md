# Research Infrastructure Building Blocks

Three small modules that a point-in-time equity research pipeline needs before it
can produce a single trustworthy number:

1. **`security_master/`** — a point-in-time universe: delisted names included,
   ST status by date, and the fields `first_bar_date` / `delist_date`. Listing
   dates are not obtainable from the free sources tested; the field is named
   `first_bar_date` precisely so nobody mistakes it for a listing date. The
   verification scripts show which fields are actually obtainable and which
   are not.
2. **`st_event_table/`** — an ST / risk-warning event table built from exchange
   announcements, with the deduplication rules written down.
3. **`sample_bank/`** — a decision-time sample store: what the system saw, what it
   picked, what it rejected, and how each one turned out.

Each module is independent. None of them ships data: a fresh clone contains no
`.db`, no `.csv` data files and no `raw/*.jsonl`. The measured numbers in these
READMEs — 232 names of which 215 usable, 16 suspect, 1 suspended; 632 intervals
across 504 stocks; 7,369 announcements → 1,932 events; 10 runs / 504 samples —
were produced on the author's machine and cannot be recomputed from a fresh
clone. Each README states what the module can and cannot do, with those measured
numbers behind that statement.

## Why these three

Most "no alpha" conclusions are actually data defects wearing a statistics costume:

- the universe excludes delisted stocks, so every historical backtest is survivorship-biased
- ST status is taken from today's name, not from the name on that date
- the sample only contains the picks, never the rejects, so you learn what the model *likes* rather than what *works*
- an event table counts the same announcement three times because three mirrors returned it

Fixing these is unglamorous and it is the difference between a backtest and a
wish. Each module here was built because a research line was blocked on exactly
one of these defects.

## Module summaries

### security_master

- Universe: Shanghai and Shenzhen main boards, 2016–2026 event window.
- Delisted list from exchange announcements: 232 names, of which 215 usable after
  price verification, 16 suspect (still trading under a new name), 1 suspended.
- ST ranges: 632 intervals across 504 stocks, built from dated announcements.
- Known limit, stated up front: listing dates are not obtainable from the free
  sources tested. The field is named `first_bar_date` precisely so nobody mistakes
  it for a listing date.
- Verifiers included: `verify_list.py`, `verify_all.py`, `probe_sources.py`.
  These are not standalone entry points: `verify_all.py` reads
  `delisted_list.csv` (232 rows), which `fetch_delisted.py` produces first. The
  full command order is in `security_master/README.md`, section "六、复现".
  `fetch_listings.py` also exists in that directory but is not described by any
  README here.

Read: [`security_master/README.md`](security_master/README.md)

### st_event_table

- Source: exchange announcement full-text search, main boards, 2016-01-01 to 2026-11-08.
- Raw: 7,369 announcements; after deduplication: 1,932 events.
- These counts come from the author's run. `event_table.csv` (1,932 rows),
  `summary.json` and `raw/*.jsonl` (7,369 announcements) are not shipped, so a
  fresh clone cannot recompute them; `st_event_table/README.md` documents the
  deduplication rule but gives no command to rebuild the table.
- The README documents the deduplication rule and the four categories that were
  merged (implementation, revocation, delisting-related, other).

Read: [`st_event_table/README.md`](st_event_table/README.md). The three
artifacts named there — `event_table.csv` (1,932 rows), `summary.json` and
`raw/*.jsonl` (7,369 announcements) — are not shipped with this repository.
`st_event_table/` contains only `fetch_events.py` and `README.md`, and that
README contains no reproduction command; the script's arguments and outputs
have to be read from the file itself.

### sample_bank

- Stores a decision-time snapshot per run: every candidate the system saw, the
  ones it picked, the ones it dropped and why, plus the forward outcome.
- Four requirements are enforced: point-in-time fields only, negatives included,
  every row traceable to a run, every label reproducible.
- Schema: `runs`, `samples`, `labels`, `daily_memory`, `agent_notes`. These five
  names are exactly what `selftest.py` checks: it points `sample_bank/bank.py`
  at a temporary database, lets `conn()` create the tables, verifies the five
  are present, then deletes the temporary database. Being able to create the
  schema is not the same as having any row. For which table is valid for
  statistics, see `sample_bank/README.md`, section "六、四条防自欺规则", rule 1
  (the de-duplicated table produced by `report`).

Read: [`sample_bank/README.md`](sample_bank/README.md)

## What is not included

- Price panels, announcement JSONL, SQLite databases — the code expects you to
  bring your own. Most paths are relative to the module; two inputs point at a
  private layout and **must be repointed**: `REPORTS` in `sample_bank/bank.py`
  and `POOL` in `security_master/build_master.py`. After a fresh clone neither
  input file exists — there is no `product/reports/` directory in this
  repository. Before running `sample_bank/bank.py ingest` or
  `security_master/build_master.py`, open those two `.py` files, find the two
  variables, and replace their values with paths to your own inputs. The READMEs
  do not describe the input file format, so read the code at the point where
  each variable is used instead of guessing a format.
- Any live endpoint credentials. The fetchers call public endpoints, need
  network access, and are meant to be adapted. `security_master/README.md`
  records that `web.ifzq.gtimg.cn` returns 501 from the WAF after bulk requests
  (use `ifzq.gtimg.cn`, without the `web` prefix), that Eastmoney `push2his`
  and Netease were unreachable behind the author's proxy, and that
  `datacenter-web` worked. These are environment differences to re-test on
  your own machine, not credentials you can fill in.

## Requirements (install before Quick start)

`requests` for the fetchers; everything else is standard library.

```bash
pip install requests
```

The author's measured environment is python 3.14.9 + requests 2.34.2
(`security_master/README.md`, section "六、复现"); other versions are
unverified. `selftest.py` itself uses only the standard library, but it loads
`sample_bank/bank.py` at runtime (`selftest.py:26-31`), so have `requests`
installed before running it as well.

## Quick start

```bash
python selftest.py      # syntax of every .py + sample_bank schema in a temp db; exit 0 = all pass
```

`selftest.py` only parses every `.py` for syntax and creates the five
`sample_bank` tables (`runs`, `samples`, `labels`, `daily_memory`,
`agent_notes`) in a temporary database, then deletes that database. It does not
fetch anything, does not create `sample_bank.db`, and does not produce
`master.csv` or `event_table.csv`. PASS / exit 0 therefore means "the Python
files parse and the schema can be created" — not "the modules ran", and not
"there is data". The module commands are in
[`sample_bank/README.md`](sample_bank/README.md),
[`security_master/README.md`](security_master/README.md) and
[`st_event_table/README.md`](st_event_table/README.md); only
`security_master/README.md` currently contains a full reproduction sequence,
and `st_event_table/README.md` contains no command at all.

## License

MIT. See [LICENSE](LICENSE).

## Contact

Author: wheelcog778 · 753073396@qq.com
