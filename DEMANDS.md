# Precision-First SEC Filing Backend 需求与总架构文档 (DEMANDS)

## 一、任务总目标
构建一个 **Precision-First（高准度优先）**的 SEC 财报及公告结构化抽取后台。
系统需支持冷启动 (Cold-Start) 全量拉取与增量同步 (Incremental Ingestion)，底层数据拉取和初级解析的核心依赖必须使用 `edgartools`。

## 二、架构选型与核心原则 (Architecture & Principles)
1. **分层抽取策略**：`edgartools` (XBRL / Obj) 为绝对优先 (Tier 1) -> 定向 XML/HTML 解析次之 (Tier 2) -> 局部正则锚点兜底 -> LLM 仅作末端 JSON 序列化。禁止大模型在全文中盲猜找值，**不需要使用 spaCy**。详见 [EXTRACTION_METHOD.md](./EXTRACTION_METHOD.md) 与 [EXTRACTOR_CORRECTNESS.md](./EXTRACTOR_CORRECTNESS.md)。
2. **严谨的基准集 (Golden Set V2)**：摒弃混合真值的统计方法。构建独立可审计的 Gold、Silver 和 Invariant 数据集与点对点的精准打标库，用确切的 SQL Denominators 计算提取正确率。所有具体的概念（Concepts）、公式、测试用例都必须以版本化配置（YAML）沉淀。详见 [GOLDEN_SET_PLAN.md](./GOLDEN_SET_PLAN.md)。
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
- **目标清单与字段**：本期重点突破核心的 53 个确定性数值字段以及特定锚区中的大段文本。详见 [EXTRACTION_FILED.md](./EXTRACTION_FILED.md)。
- **/A 修正案处理 (Amendment)**： `/A` 修正案的文件视作当期信息的直接新切片。由于提交时间不同，处理时将其按新文档进行特征重新计算覆盖；如 /A 中缺失某值则视同该值本期未重述，不做硬性回溯。
- **特征因子消费的优先级 (Timeline Fetching)**：
  向下游量化端吐出数据时，按照提交时间由远至近，选取深度最深的真值。**人工审查修正值 (Ground Truth) > 解析原生值**。

## 六、人工审核产品交互刚需 (UI/UX Requirement)
- 高效的人工审核面板（UI）**必须并排展示原文 Span 区块 与 抽取结果**（Side-by-side），支持对长文档直接高亮对应锚点。若让审核人员脱离原文盲审 JSON，效率低且极易出现盲目确认。

## 七、研发里程碑与大包规划 (Roadmap)
为了匹配 Golden Set V2 计划的落地，我们对此前的粗放规划进行了严谨整合重排：

- **第一期：基础设施构筑与目录冻结 (Phase 0/1)**
  - 设计落地新版的 `src/pipeline/golden/` 数据库 ORM (Case/Subject/Truth/Result 分离)。
  - 冻结 53 个字段与 `concept_registry` / `invariants` YAML 配置文件。
  - 完成确定性最高的 **Tier 1 抽取器** (`ObjPath`, `XbrlConcept`, `XmlPath`) 的编写。
- **第二期：硬骨头攻坚与白马股测试 (Phase 1/2 评估)**
  - 首先引入特定种子企业 (如 MSFT，JPM，TSLA) 的精选验证集运行。
  - 让纯数值类型的抽取在复杂财年或复杂银行流水上跑通，保障金标正确率。确信准确后才将处理逻辑扩展到非标准结构的图表 (开放 **Tier 2** 半结构化抽取)。
- **第三期：兜底逻辑、交叉验证域审核系统开发 (Phase 3)**
  - 引入交叉检查 (Cross Checks) 作为 Invariants 评价项；完成包含人工修正队列 (Review Queue) 的审核流 API 界面支持。
- **第四期：LLM 介入及文本片段化处理 (Phase 4)**
  - 前面层级人工审核反馈后，LLM (Tier 3) 才会根据被限定和校验过的精确文本片段执行 JSON 生成；不达标情况下避免让 LLM 跑“全表发漫游”，浪费 API 本钱。
- **第五期：历史清洗与稳定调度**
  - 所有管道指标在 Golden Set 达标后，启动多线程池全速进行长周期历史 Filing 洗库，此后平稳并入 Daily Incremental 定时系统。