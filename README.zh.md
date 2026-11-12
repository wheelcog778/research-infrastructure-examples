# 研究基础设施三件套

一条点时（point-in-time）股票研究流水线，在产出第一个可信数字之前，必须先有三样东西：

1. **`security_master/`** —— 点时证券主表：含退市股、按日 ST，以及 `first_bar_date` / `delist_date` 两个字段。免费源拿不到上市日，字段因此命名为 `first_bar_date`，防止被当作上市日使用；外加一组验证脚本，用来说明哪些字段真的拿得到、哪些拿不到。
2. **`st_event_table/`** —— 从交易所公告构建的 ST / 风险警示事件表，去重规则写在文档里。
3. **`sample_bank/`** —— 决策时点样本库：系统看到了什么、选了什么、为什么刷掉、后来涨没涨。

三个模块互相独立，都不带数据：新 clone 里没有 `.db`、没有 `.csv` 数据文件、没有 `raw/*.jsonl`。各 README 里的实测数字——232 只中 215 只可研究、16 只疑似、1 只长期停牌；632 段区间覆盖 504 只；7,369 条公告去重后 1,932 条事件；10 个 run / 504 条样本——都是作者本机运行的结果，新 clone 复算不出来。每个 README 都写清了这个模块能做什么、不能做什么，以及支撑这句话的实测数字。

## 为什么是这三样

大多数"没有 alpha"的结论，其实是数据缺陷穿了统计学的衣服：

- 股票池不含退市股 → 所有历史回测都有幸存者偏差
- ST 状态取自今天的名称，而不是那一天的名称
- 样本只存选中的票，不存被刷掉的 → 学到的是"它喜欢什么"，不是"什么会涨"
- 同一份公告被三个镜像返回，事件表把它数了三遍

修这些不性感，但它是"回测"和"许愿"的分界线。这三个模块，每一个都是因为某条研究线卡在对应的缺陷上才建起来的。

## 三个模块

### security_master

- 范围：沪深主板，2016–2026 事件窗口。
- 退市名单来自交易所公告：232 只，价格校验后 215 只可研究，16 只疑似仍在市（改名），1 只长期停牌。
- ST 区间：632 段、覆盖 504 只，按公告日期构建。
- 已知边界（写在最前面）：免费源拿不到上市日。字段因此命名为 `first_bar_date`，防止被当作上市日使用。
- 自带验证：`verify_list.py`、`verify_all.py`、`probe_sources.py`。它们不是独立入口：`verify_all.py` 读的是 `fetch_delisted.py` 先产出的 `delisted_list.csv`（232 行）。完整命令顺序见 `security_master/README.md` 的「六、复现」；`fetch_listings.py` 也在该目录，但这里的 README 都没说明它的用途。

见 [`security_master/README.md`](security_master/README.md)。

### st_event_table

- 来源：交易所公告全文检索，沪深主板，2016-01-01 至 2026-11-08。
- 原始 7,369 条公告，去重后 1,932 条事件。
- 这些计数来自作者本机的一次运行。`event_table.csv`（1,932 行）、`summary.json`、`raw/*.jsonl`（7,369 条公告）都不随仓库提供，`st_event_table/README.md` 只写去重规则、没有重建命令，新 clone 无法复算。
- README 写明了去重规则，以及被合并的四类（实施、撤销、退市相关、其他）。

见 [`st_event_table/README.md`](st_event_table/README.md)。该 README 点名的三个产物——`event_table.csv`（1,932 行）、`summary.json`、`raw/*.jsonl`（7,369 条公告）——都不随仓库提供。`st_event_table/` 里只有 `fetch_events.py` 与 `README.md`，那篇 README 也没有任何复现命令；脚本的参数与输出只能到文件里读。

### sample_bank

- 每次运行存一份决策时点快照：系统看到的所有候选、选中的、刷掉的及原因，以及后续结果。
- 四条硬要求：只用决策时点可见字段、必须含反例、每行可追溯到某次运行、每个标签可复算。
- 表结构：`runs`、`samples`、`labels`、`daily_memory`、`agent_notes`。这五个名字正是 `selftest.py` 检查的表：它把 `sample_bank/bank.py` 的 `DB` 指到临时库，让 `conn()` 建表，查完五张是否存在就把临时库删掉；能建表不等于有数据。哪张表可用于统计，见 `sample_bank/README.md` 第六节「四条防自欺规则」第 1 条（`report` 的去重表）。

见 [`sample_bank/README.md`](sample_bank/README.md)。

## 不包含什么

- 行情面板、公告 JSONL、SQLite 数据库——代码假定你自己带数据。大部分路径相对于模块目录；有两处输入指向私有目录布局，**必须改成你自己的**：`sample_bank/bank.py` 的 `REPORTS` 与 `security_master/build_master.py` 的 `POOL`。新 clone 后这两个输入文件都不存在，仓库里也没有 `product/reports/` 目录。运行 `sample_bank/bank.py ingest` 或 `security_master/build_master.py` 之前，先打开这两个 `.py` 找到变量，把值换成你自己的输入路径。README 没有写输入文件的格式，请到变量被使用的地方读代码，不要猜格式。
- 任何线上接口凭证。抓取脚本调用公开接口、需要联网，也要按你的环境改造：`security_master/README.md` 记录 `web.ifzq.gtimg.cn` 批量请求后被 WAF 返回 501（去掉 `web` 前缀的 `ifzq.gtimg.cn` 正常），东财 `push2his` 与网易在作者本机代理下不通，`datacenter-web` 正常。这些是要在你自己机器上重测的环境差异，不是填个凭证就能解决的。

## 依赖（跑自检之前先装）

`requests` 用于抓取脚本，其余都是标准库。

```bash
pip install requests
```

作者实测环境是 python 3.14.9 + requests 2.34.2（见
`security_master/README.md` 的「六、复现」），其他版本未验证。
`selftest.py` 本身只用标准库，但运行时会加载 `sample_bank/bank.py`
（`selftest.py:26-31`），所以跑它之前也先装好 `requests`。

## 上手第一步

```bash
python selftest.py      # 全部 .py 语法 + 临时库建 sample_bank 五张表；exit 0 = 全过
```

`selftest.py` 只做两件事：解析全部 `.py` 的语法、在临时库里建 `sample_bank`
的五张表（`runs`、`samples`、`labels`、`daily_memory`、`agent_notes`），跑完把
临时库删掉。它不抓数据、不生成 `sample_bank.db`，也不生成 `master.csv` 或
`event_table.csv`。所以 PASS / exit 0 只代表「`.py` 能解析、表能建起来」，
不代表「模块跑过」，更不代表「有数据」。三个模块的命令见
[`sample_bank/README.md`](sample_bank/README.md)、
[`security_master/README.md`](security_master/README.md) 和
[`st_event_table/README.md`](st_event_table/README.md)；目前只有
`security_master/README.md` 的「六、复现」给出完整命令顺序，
`st_event_table/README.md` 一条命令都没有。

## 许可

MIT，见 [LICENSE](LICENSE)。

## 联系

作者：wheelcog778 · 753073396@qq.com
