# Research Infrastructure Building Blocks

Three small modules that a point-in-time equity research pipeline needs before it
can produce a single trustworthy number:

1. **`security_master/`** — a point-in-time universe: delisted names included, ST
   status by date, first and last trading day, plus the verification scripts that
   show which fields are actually obtainable and which are not.
2. **`st_event_table/`** — an ST / risk-warning event table built from exchange
   announcements, with the deduplication rules written down.
3. **`sample_bank/`** — a decision-time sample store: what the system saw, what it
   picked, what it rejected, and how each one turned out.

Each module is independent. None of them ships data. Each README states what the
module can and cannot do, with the measured numbers behind that statement.

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

Read: [`security_master/README.md`](security_master/README.md)

### st_event_table

- Source: exchange announcement full-text search, main boards, 2016-01-01 to 2026-11-08.
- Raw: 7,369 announcements; after deduplication: 1,932 events.
- The README documents the deduplication rule and the four categories that were
  merged (implementation, revocation, delisting-related, other).

Read: [`st_event_table/README.md`](st_event_table/README.md)

### sample_bank

- Stores a decision-time snapshot per run: every candidate the system saw, the
  ones it picked, the ones it dropped and why, plus the forward outcome.
- Four requirements are enforced: point-in-time fields only, negatives included,
  every row traceable to a run, every label reproducible.
- Schema: `runs`, `samples`, `labels`, `daily_memory`, `agent_notes`.

Read: [`sample_bank/README.md`](sample_bank/README.md)

## What is not included

- Price panels, announcement JSONL, SQLite databases — the code expects you to
  bring your own. Most paths are relative to the module; two inputs point at a
  private layout and must be repointed: `REPORTS` in `sample_bank/bank.py` and
  `POOL` in `security_master/build_master.py`.
- Any live endpoint credentials. The fetchers call public endpoints and are meant
  to be adapted.

## Requirements

`requests` for the fetchers; everything else is standard library.
`pip install requests`

## License

MIT. See [LICENSE](LICENSE).

## Contact

Author: Q洗Y烟机 · 753073396@qq.com
