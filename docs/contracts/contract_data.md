# 契约二：数据契约（contract_data）

- 版本：v1.1（2026-10-02）
- 状态：**M0 定稿**（§4/§8 已回填 MetaQuotes-Demo 实测值；切换 broker 时重探并追加快照）
- 变更流程：改本文件必须同步改 `tests/test_contract_data.py` 与实现（`data/database.py`、`tools/export_ohlcv_parquet.py`、`tools/clean_ohlcv.py`），版本号 +1。
- 血统：ohlcv schema 与只读分层继承旧库 `data/database.py` + `AGENTS.md` §2/§5 + 清洗工具 v2 实践；**时间戳语义换掉**（旧库存 MT4 server time，新库存 UTC——这是本次迁移最大的语义修正）。

---

## 1. 分层模型（只读单向，继承旧库纪律）

```
┌─ L1 权威库 ─────────────────────────────┐
│ data/market_data.db :: ohlcv            │ 唯一写入者：引擎 DataFactory（append/upsert）
│                                          │ 工具打开一律 mode=ro + query_only=ON
├─ L2 研究层 ─────────────────────────────┤
│ data/am_parquet/{SYMBOL}_{TF}.parquet   │ 单向：L1 → parquet，永不回写
│ 唯一生产者 tools/export_ohlcv_parquet.py│ 唯一读者 data/parquet_store.py
├─ L3 清洗产物 ───────────────────────────┤
│ ohlcv_clean 表 + data/clean/*.parquet   │ 清洗三规则产物；独立表，永不覆盖 L1
└─────────────────────────────────────────┘
```

回测只允许读 L2/L3；实时引擎只写 L1。任何"研究脚本直接写 L1"的路径 = 违约。

## 2. ohlcv schema

```sql
CREATE TABLE ohlcv (
    timeframe TEXT NOT NULL,      -- 'M1','M5','M15','M30','H1','H4','D1','W1'
    timestamp INTEGER NOT NULL,   -- UTC Unix 秒（int64），= 该 bar 开盘时刻
    open  REAL NOT NULL,
    high  REAL NOT NULL,
    low   REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,         -- tick volume
    PRIMARY KEY (timeframe, timestamp)
);
```

- D1 语义：**入库前必须转 UTC**（`mt5_client.to_utc()`），库内不允许出现 server-time 时间戳。
- `INSERT OR REPLACE` 幂等 upsert；读取按 timestamp 升序。
- `ohlcv` 永不在 git 里；清洗产物 `ohlcv_clean` 独立存在（旧库事故教训：DB 瘦身时把 `ohlcv_clean` 弄丢了——新库的 L3 产物必须落 parquet 文件留底，不只在 DB 里）。

## 3. 时间戳纪律

1. 存储：一律 UTC 秒 int64。显示：UTC+8 仅在渲染层（`config.settings.local_dt()`）。
2. 禁止裸 `datetime.fromtimestamp()` / `datetime.now()`（本地时区泄漏）；统一 `utc_now()` / `utc_dt()`。
3. **server offset 实测不假设**（R6）：
   - `mt5_client.server_offset_sec = 最新 tick.time − 本机 UTC`，启动校准 + 每 6h 重校准；
   - 漂移 > 30 min → 告警"疑似 broker DST 切换"并更新（方法论照搬旧库 v4.1 补丁）；
   - offset 持久化（`data/server_offset.json`），probe 工具每次 M0/M1 巡检输出。
4. journal/trades/signals 表内时间字段全部 UTC 秒。

## 4. 桶对齐（D1 + 旧库 §5 方法论）

- 公式：`bucket = ((ts_utc − OFFSET) // step) * step + OFFSET`，禁止裸 `(ts // step) * step`。
- `OFFSET` = broker 日线开市时刻相对 00:00 UTC 的偏移（秒）。**每个经纪商不同，且可能随 DST 变化**——永远探测，不写常量。
- 探测法（照搬旧库 `detect_offset`）：对已入库 bar 序列取 `mode(ts % step)`，一致率 < 95% 时告警并重新探测。
- **M0 实测（2026-10-02，MetaQuotes-Demo，server offset = +3.00h 整）**：server-time 域内 M1/M5/M15/M30/H1/H4/D1 全部 `桶偏移=0`、一致率 100%（broker 按服务器整点对齐 K 线）。换算到 UTC 存储域：`OFFSET_utc = (−server_offset) mod step`，即 H1=0s、**H4=3600s（UTC 桶起点 01:00/05:00/09:00/13:00/17:00/21:00）**——与旧库 MT4 的 H4 形态巧合一致（两者同为 UTC+3 服务器），但这是探测结果、不是常量；**切换 broker（Dukascopy MT5）后必须重探**。详见 `docs/probe/mt5_probe_report.md`。
- 自建高周期桶（如 H2 合成）只允许用覆盖完整周期的桶，禁止 fabricate（旧库 ghost bar 教训，见 §6）。

## 5. 研究层 parquet（L2，继承旧库六列契约）

- 列严格六列：`time(int64, UTC 秒) / open / high / low / close / volume(float64)`，无额外列、无 index。
- 唯一生产者 `tools/export_ohlcv_parquet.py`：全量重写式（dedupe → sort → validate → 写文件 → 更新 `_manifest.json`）。
- 唯一读者 `data/parquet_store.py`：`load_ohlcv / load_multi / summary / is_stale`（staleness = 24h）。
- 研究代码不得直接读 L1 SQLite（保证口径一致 + 不锁库）。

## 6. 清洗三规则（L3，继承旧库 clean 工具 v2）

针对"目标 TF bar 存在但源数据不支持"与"聚合偏差"：

1. **ghost 删除**：目标 TF bar 存在、但其窗口内 M1/M5 源 bar 数为零 → 删除（H4 类似旧库可配 keep 策略，须在报告中列明保留理由）。
2. **偏差重建**：聚合重算价与现存 bar 偏差 > 0.5%（close 或 OHLC 口径）→ 以聚合结果重建。
3. **反向补洞**：源数据覆盖而目标 TF 缺失的桶 → 用聚合补插。

安全边界（逐条继承）：
- 源库只读打开（`mode=ro` + `PRAGMA query_only=ON`）；
- `FORBIDDEN_TABLES = ("ohlcv",)` 硬断言：清洗只写 `ohlcv_clean` 与 L3 parquet；
- 默认 dry-run，`--apply` 才落盘；自动备份；幂等。

## 7. bar0/bar1 供给语义（对 INV-S1 的数据侧支撑）

- `copy_rates` 返回的**末根是 forming bar**（bar0），`[-2]` 才是 bar1。
- DataFactory 暴露给策略的缓存：
  - `candles`：升序列表，`[-1]`=bar0（仅展示/价格触发）、`[-2]`=bar1；
  - 顶层指标键 = **bar1 值**（本地计算，取 `ta[bar1.time]`）；
  - `get_indicator_series(name, n)`：从 `indicator_snapshots` 按 bar 时间对齐取旧→新序列，末项 = 当前 bar1。
- 指标快照表 `indicator_snapshots(timeframe, ts, key, value)`：每闭合 bar 每 key 一行，UTC 秒主键对齐。

## 8. symbol spec（MT5 新增节，probe 回填）

`core/mt5_client.symbol_spec()` 缓存并暴露：

| 字段 | 用途 |
|------|------|
| `digits` / `point` | 报价精度与最小变动（D4：pip 推导基准） |
| `trade_tick_value` / `trade_tick_size` | PnL 换算（0.01 lot = 1 oz 的旧惯例 → 由 tick_value 运行时推导） |
| `volume_min/step/max` | 手数合法性 |
| `filling_mode` 掩码 | 下单填充策略自适应（D6） |
| `stops_level` / `freeze_level` | SL/TP 最小距离校验 |
| `trade_mode` | 是否允许交易（demo/实盘差异探测） |

**M0 实测快照（2026-10-02，MetaQuotes-Demo #113526190）**：

| 字段 | 实测值 | 解读 |
|------|--------|------|
| digits / point | 2 / 0.01 | 与旧库 2 位报价惯例一致，pip_size=0.01 |
| tick_value / tick_size | 0.1 / 0.01 | 0.01 lot 每跳 $0.001…注意 PnL 换算用 tick_value 而非旧库 "$1/点" 硬编码 |
| volume min/step/max | 0.01 / 0.01 / 100 | 手数合法域 |
| stops_level / freeze_level | 0 / 0 | 无最小距离限制（MetaQuotes demo 宽松；真 broker 可能非 0） |
| filling_mode 掩码 | 3 | FOK(1) + IOC(2) 允许，RETURN 不允许 → 下单包装层按位选 |
| trade_mode | 4 | full，可交易 |
| 账户模式 | HEDGING（对冲） | R4 解除：与 MT4 语义一致，v1 门禁无需调整 |

> 该快照属于 MetaQuotes-Demo 通用 feed；其 demo feed 恰为 2 位报价。接入 Dukascopy MT5 后重跑 probe 并追加新快照（不覆盖，按 broker 留档）。

---

## 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-10-02 | 初版：时间戳改 UTC；分层/清洗/研究层契约继承旧库；§4/§8 留待 probe 实测回填 |
| v1.1 | 2026-10-02 | §4/§8 回填 MetaQuotes-Demo 实测值；新增实测快照表与桶偏移换算结论；标记 M0 定稿 |
