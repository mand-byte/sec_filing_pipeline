# Precision-First SEC Filing Backend 需求与总架构文档 (DEMANDS)

## 一、任务总目标
构建一个 **Precision-First（高准度优先）**的 SEC 财报及公告结构化抽取后台。
系统需支持冷启动 (Cold-Start) 全量拉取与增量同步 (Incremental Ingestion)，底层数据拉取和初级解析的核心依赖必须使用 `edgartools`。

## 二、架构选型与核心原则 (Architecture & Principles)
1. **分层抽取策略**：`edgartools` (XBRL / Obj) -> XML/HTML -> anchored regex -> LLM 为核心链路，**不需要使用 spaCy**。详见 [EXTRACTION_METHOD.md](./EXTRACTION_METHOD.md)。
2. **严谨的基准集 (Golden Set V2)**：摒弃混合真值的统计方法。构建独立可审计的 Gold、Silver 和 Invariant 数据集，基于版本化配置与可审计的 truth/evaluation 体系。详见 [GOLDEN_SET.md](./GOLDEN_SET.md)。
3. **“修一次不再重错”的修正闭环**：所有人工审核出的错误必须提取出对应 `error_code` + 计入 `golden_case` (回归测试集) + 单点修复 `patch`。回归测试挂掉则阻断系统发布。

## 三、目标集合与数据存储来源 (Data Source)
核心的上市公司集合及状态通过 ClickHouse 维护（本系统不强制绑定 CH，亦可无缝对接 PostgreSQL，只要 Schema 等价）。
数据源表 `data_quant.us_stock_universe` 结构范例：
```sql
CREATE TABLE IF NOT EXISTS us_stock_universe (
    ticker String,
    composite_figi FixedString(12),
    name                 String,
    cik                  FixedString(10),
    active               UInt8 DEFAULT 0,
    base_currency_name   Nullable(String),
    base_currency_symbol Nullable(FixedString(3)),
    currency_name        Nullable(String),
    currency_symbol      Nullable(FixedString(3)),
    delisted_utc         Nullable(DateTime64(3, 'UTC')),
    last_updated_utc     DateTime64(3, 'UTC'),
    locale               LowCardinality(String),
    market               LowCardinality(String),
    primary_exchange     Nullable(String),
    share_class_figi     Nullable(FixedString(12)),
    type                 Nullable(String),
    update_time DateTime64(3, 'UTC') DEFAULT now64(3)
) ENGINE = ReplacingMergeTree(update_time)
ORDER BY (composite_figi)
```
**数据处理边界规则**：
- 底库仅含普通股 (CS) 和 ADR，系统已从上游排除“多个 Ticker 共用 1 个 FIGI（如 GOOG/GOOGL）”的冗杂，FIGI 与 CIK 可以实现一对一确切映射。
- **退市处理**：当 `active=0` 时，仅处理 SEC 文件提交时间（`accepted_at`）小于等于 `delisted_utc` 的 Filing；晚于退市时间的垃圾/注销报备跳过。
- **解析监控**：解析过程的运行时数据、成功/失败标志与具体失败 Callstack 必须详细落盘存入 DB，以供分析。

## 四、程序调度与系统入口 (Entrypoints & State)
- **配置与鉴权**：统一收敛在 `.env` 中，包含 ClickHouse、PostgreSQL 的连接信息及初始化数据抓取的首个时间戳。
- **调度模块 (Scheduler)**：使用同步调度器循环触发处理。程序暴露 3 个独立的抓取与解析主干路（Route）：
  1. `issuer`（定期/事件报告主线）
  2. `owner`（内部人士持仓/交易变动线）
  3. `holding`（机构持仓主线）
- **无状态设计**：解析拉取进程自身无状态。每次调度执行，程序只需查询数据库得出待拉取 Tickers 的最新进度，依靠文件的接收时间 (`accepted_at` 时间戳) 进行断点续传式的增量游标推移。

## 五、提取对象与特征读取规则
- **目标清单与字段**：本期重点突破核心的 53 个确定性数值字段以及特定锚区中的大段文本。详见 [EXTRACTION_FIELDS.md](./EXTRACTION_FIELDS.md)。
- **/A 修正案处理 (Amendment)**： `/A` 修正案的文件视作当期信息的直接新切片。由于提交时间不同，处理时将其按新文档进行特征重新计算覆盖；如 /A 中缺失某值则视同该值本期未重述，不做硬性回溯。
- **特征因子消费的优先级 (Timeline Fetching)**：
  向下游量化端吐出数据时，按照提交时间由远至近，选取深度最深的真值。**人工审查修正值 (Ground Truth) > 解析原生值**。

## 六、人工审核产品交互刚需 (UI/UX Requirement)
- 高效的人工审核面板（UI）**必须并排展示原文 Span 区块 与 抽取结果**（Side-by-side），支持对长文档直接高亮对应锚点。若让审核人员脱离原文盲审 JSON，效率低且极易出现盲目确认。

## 七、研发里程碑与大包规划 (Roadmap)
为了匹配 Golden Set V2 计划的落地，我们对此前的粗放规划进行了严谨整合重排：

- **第一期：基础设施构筑与核心范围冻结**
  - 构建数据库 schema 与评估框架，冻结目标字段定义，搭建确定性最高的初始抽取链路。
- **第二期：白马股测试与核心字段验证**
  - 在代表性企业上验证核心字段准确率，达标后扩展至更复杂的数据结构。
- **第三期：兜底逻辑与人工审核支持**
  - 引入交叉校验机制，搭建人工修正队列与审核流程 API。
- **第四期：文本理解层引入**
  - 在前序层级稳定后，引入受约束的文本生成能力处理结构化抽取无法覆盖的内容。
- **第五期：历史数据回填与稳定运行**
  - 全量历史filing处理完成后，并入每日增量定时调度系统。