## 一、任务总目标

请实现一个 SEC filing backend，满足以下目标：

* [ ] 从 SEC 抓取目标 filings，支持历史冷启动和后续增量同步。
* [ ] 对 raw filing、primary document、附件、解析文本、结构化结果、映射结果、审计证据进行完整持久化。
* [ ] 构建一个**分层 fallback 解析体系**，在不牺牲真实性的前提下尽量提高自动通过率。
* [ ] 把人工复核限制在必要场景，并给出明确、可解释的复核原因。
* [ ] 支持 spaCy 微调、版本管理、回滚和评估，用来持续降低人工复核比例。
* [ ] 明确限制 LLM 的职责：**仅对已定位的 narrative snippet 做 schema-constrained structuring**。
* [ ] 所有自动化结果都必须可追溯、可回放、可审计、可重新计算。

---

## 二、硬性原则

### 1) 正确率优先

* [ ] 以 **precision-first** 为最高目标。
* [ ] 不确定时，**宁可不产出 fact，也不能猜一个看起来像真的 fact**。
* [ ] 对关键字段（issuer CIK、owner、CUSIP、shares、value、percent、period/report date、amendment identity）采用更严格的自动通过门槛。
* [ ] 任何自动入库 fact 都必须有原始证据、定位信息、提取方法、置信度和校验结果。

### 2) 来源优先级固定

* [ ] 不同来源冲突时，按以下优先级裁决：
  **structured XML/XBRL > official table/information table > deterministic DOM/regex/rule parser > spaCy > LLM structuring**。
* [ ] 低优先级结果只能补缺，**不能无条件覆盖**高优先级结果。
* [ ] 发生冲突时，必须进入 review queue，不能静默覆盖。

### 3) LLM 职责边界固定

* [ ] LLM 不参与 SEC 抓取、发现、下载、重试、去重、回放。
* [ ] LLM 不参与事实真伪复核，不作为最终“truth arbiter”。
* [ ] LLM 不负责 security mapping 的最终裁决。
* [ ] LLM 只能接收**已经被本地规则或模型定位好的 snippet**，输出严格 schema JSON。
* [ ] LLM 不能“搜索全文后自己找答案”，也不能生成证据之外的数值。

### 4) amendment 与幂等原则固定

* [ ] original 与 amendment 必须同时保留，绝不覆盖原记录。
* [ ] 必须使用 ETL 侧自然键/去重键保证幂等，不能依赖 ClickHouse `UPDATE`、`FINAL`、事后修表来保证正确性。
* [ ] `acceptance_datetime_utc` 是首选事件时间，缺失时才允许降级。 

---

## 三、范围定义

### In Scope

* [ ] issuer-centric forms
* [ ] owner/insider-centric forms
* [ ] holdings/fund forms，特别是 `13F-HR` / `13F-HR/A`
* [ ] raw artifact persistence
* [ ] canonical filing index / document index / extracted facts / route-specific fact tables
* [ ] security mapping
* [ ] confidence scoring / review queue / QA reporting
* [ ] spaCy fine-tune pipeline
* [ ] LLM snippet structuring adapter
* [ ] 冷启动、增量、重放、回归测试、runbook

### Out of Scope

* [ ] 人工审核 UI 前端
* [ ] 面向终端用户的 serving / as-of query 产品层
* [ ] 用 LLM 替代 SEC acquisition / truth verification
* [ ] 用 ClickHouse 事后修表替代 ingestion correctness

---

## 四、支持的表单与路由要求

* [ ] issuer route 至少覆盖：`10-K`, `10-K/A`, `10-Q`, `10-Q/A`, `8-K`, `8-K/A`, `NT 10-Q`, `NT 10-Q/A`, `NT 10-K`, `NT 10-K/A`, `6-K`, `6-K/A`, `20-F`, `20-F/A`, `S-1`, `S-1/A`, `424B4`, `DEF 14A`, `DEF 14A/A`, `SC TO-I`, `SC TO-I/A`, `SC 13E3`, `SC 13E3/A`。
* [ ] owner route 至少覆盖：`3`, `3/A`, `4`, `4/A`, `5`, `5/A`, `13D`, `13D/A`, `13G`, `13G/A`, `144`, `144/A`。
* [ ] holdings route 至少覆盖：`13F-HR`, `13F-HR/A`。
* [ ] 13F 必须作为**独立 holdings route**，不能复用 issuer-CIK-only discovery 逻辑。 

---

## 五、抓取与原始数据持久化要求

* [ ] SEC client 必须支持合规 user-agent、限流/重试、可观测错误、可重放下载。
* [ ] 对每个 filing，必须保存：metadata、submission payload、primary document、附件、抓取时间、来源 URL、content-type、字节长度、SHA-256。
* [ ] raw store 必须采用**确定性路径 + 内容哈希**策略，支持去重与重放。
* [ ] 必须保留 filing-level 与 document-level 两层 raw artifacts。
* [ ] 文档解码后文本也要保存，保留原文与清洗后文本的对应关系。
* [ ] 保存 parser 输入快照，保证未来可离线重跑解析。

---

## 六、标准化与索引层要求

* [ ] 对 form type 做 canonicalization，区分 `form_type_raw`、`form_type_base`、`is_amendment`。
* [ ] accession 必须规范化，同时保留原始字符串。
* [ ] 构建 `filing_index`、`filing_document`、`filing_security_link`、`extracted_fact` 以及 route-specific fact tables。
* [ ] 记录 `acceptance_datetime_utc`、`filing_date`、`period_of_report`、`report_date`、`file_number`、`primary_document`。
* [ ] 需要 `amendment_group_key` 与 `amendment_sequence`，用于把 original 与 amendments 归到同一家族。
* [ ] original sequence 必须为 `0`，后续 amendments 递增。
* [ ] 增量状态要同时跟踪 `last_acceptance_datetime_utc` 与 `last_accession_no`。

---

## 七、解析流水线与 fallback 规则

### 解析总顺序

对每类 fact，必须按以下顺序尝试：

* [ ] `structured_xbrl`
* [ ] `structured_xml`
* [ ] `official_table` / `information_table`
* [ ] `deterministic_rule`（DOM / XPath / regex / header/table parser）
* [ ] `spacy_model`
* [ ] `llm_structuring`

### fallback 原则

* [ ] 只有在上一级来源**不可用、字段不完整、或明显不适用**时，才能进入下一级。
* [ ] 需要记录每一次 fallback 的原因，例如：`missing_xml`, `table_not_found`, `unsupported_layout`, `mandatory_field_missing`。
* [ ] fallback 是**受控降级**，不是“任何方法都试一下然后选一个最好看的”。
* [ ] 每个 fact 需要保存：`chosen_method`、`attempted_methods`、`fallback_reason`、`competing_candidates`。

### form-specific 解析约束

* [ ] Forms `3/4/5` 的核心交易与持股字段，应优先来自 XML，不允许让 LLM 主导。
* [ ] `13F-HR` 的 holdings 行，必须优先来自 information table / structured table，不允许让 LLM 直接从全文生成 holdings。
* [ ] issuer narrative 类字段（例如 8-K item narrative、部分公告文本）可以由 rule / spaCy / LLM structuring 补强，但必须有 snippet evidence。
* [ ] 关键 numeric facts 只能在有明确数字证据且通过校验时自动通过。

---

## 八、正确率保障机制

### 证据与可解释性

* [ ] 每个 fact 必须带 `snippet_text`、`snippet_locator`、`document_filename`。
* [ ] `snippet_locator` 至少要能定位到 section / table row / xpath / line-range / anchor 之一。
* [ ] 对 table/structured source，证据要能定位到具体 row / cell。
* [ ] 证据必须直接支持 fact 本身，而不是泛泛相关文本。

### 校验规则

* [ ] 数值字段要有单位、数值范围和类型校验。
* [ ] 百分比必须在合理区间。
* [ ] share/value/amount 不能出现明显非法值。
* [ ] CUSIP、CIK、accession、date、form family 必须做格式校验。
* [ ] amendment 与 original 的关系必须做一致性校验。
* [ ] 相同 fact 在多个 extractor 间冲突时必须进入 review。

### 共识与冲突

* [ ] 若两个独立高优先级解析器对同一 fact 一致，可提升置信度。
* [ ] 若 deterministic parser 与 spaCy/LLM 冲突，以 deterministic 为主，低优先级结果只作候选。
* [ ] 若 structured source 与任何文本提取冲突，以 structured source 为主，其他结果仅保留审计信息。

---

## 九、人工复核最小化策略

### review queue 只接收异常样本

* [ ] 复核队列必须是“异常驱动”，而不是“全量兜底”。
* [ ] review reason 至少包括：

  * `source_conflict`
  * `mandatory_field_missing`
  * `ambiguous_security_mapping`
  * `low_confidence`
  * `parser_disagreement`
  * `unsupported_layout`
  * `amendment_conflict`
  * `outlier_numeric`

### 自动通过策略

* [ ] 对**关键字段**，只有高优先级来源 + 通过规则校验时才能 auto-accept。
* [ ] spaCy 输出默认不能单独自动通过关键 numeric/identifier facts，除非有强 corroboration。
* [ ] LLM 输出默认不能单独自动通过关键 numeric/identifier facts。
* [ ] LLM 更适合补充 narrative / categorical / event-structure 类字段。
* [ ] 低风险 narrative 字段可在更严格 schema 校验 + 无冲突 + 有证据时 auto-accept。

### 复核负载控制

* [ ] 系统要尽量把 review 压缩到“高价值、低量”的样本。
* [ ] 对 auto-accepted 样本，要支持抽样审计，而不是人工全看。
* [ ] 要有按 form / parser_method / fact_type 的 review rate 统计，用来驱动阈值优化。

---

## 十、security mapping 要求

* [ ] security mapping 顺序固定为：
  **exact CUSIP / issuer CIK / explicit ticker history > composite keys > fuzzy issuer name**。
* [ ] 必须记录 `match_method`、`match_key_raw`、`match_confidence`、`candidate_count`。
* [ ] fuzzy name match 只能在候选足够单一时自动通过。
* [ ] 有多个高相似候选时必须进入 review，不得盲配。
* [ ] mapping 输出必须可追溯到上游 reference rows。
* [ ] reviewed mapping correction 必须能回流到 alias / ticker history / security master。

---

## 十一、spaCy 微调能力要求

### 角色定位

* [ ] spaCy 是为了减少人工复核，主要用于**narrative 片段中的实体、span、关系、字段定位**。
* [ ] spaCy 不负责 SEC crawling，不负责 truth review，不替代 deterministic parser。
* [ ] spaCy 是 deterministic parser 与 LLM structuring 之间的重要降人工层。

### 能力要求

* [ ] 支持 route/form-specific spaCy pipeline。
* [ ] 支持至少一种 span/NER 任务，以及必要时的 relation extraction 或 span categorization。
* [ ] 支持弱监督训练数据：高精度规则产出的 silver labels。
* [ ] 支持人工复核后的 gold labels 回流。
* [ ] 支持模型版本管理、指标记录、回滚、shadow mode。
* [ ] 每个 fact 必须记录 `spacy_model_version`（如果经过 spaCy）。

### 训练与评估

* [ ] 建立训练集、验证集、时间外测试集，避免只在历史同分布上看指标。
* [ ] 评估维度至少包括：precision、recall、F1、review-rate reduction、false-positive rate。
* [ ] 模型上线门槛以**precision 不下降**为前提，再追求 review rate 下降。
* [ ] 新模型必须支持与旧模型 A/B 或 shadow 比较。
* [ ] reviewed corrections 必须能自动沉淀为下一轮训练数据。

### 主动学习

* [ ] 低置信、冲突、多候选、unsupported layout 样本要优先进入标注池。
* [ ] 要支持从 review queue 自动生成训练样本。
* [ ] 要支持基于 form/fact type 的 targeted fine-tune，而不是一锅训练。

---

## 十二、LLM 结构化要求

### 允许做什么

* [ ] 输入：**已定位 snippet + 目标 schema + 允许字段定义 + 禁止编造约束**。
* [ ] 输出：严格 JSON，必须通过 schema validation。
* [ ] 输出必须回带 snippet 中可验证的 supporting evidence。
* [ ] 可用于将复杂 narrative 文本归一化成结构字段。

### 禁止做什么

* [ ] 禁止读取整份 filing 后“自主决定抓什么”。
* [ ] 禁止在没有 snippet 的情况下直接抽 facts。
* [ ] 禁止补造未在 snippet 中出现的数字、日期、比例或实体。
* [ ] 禁止作为 security mapping 或 truth verification 的最终裁判。

### 结果落地

* [ ] LLM 结果必须标记为 `parser_method=llm_structuring`。
* [ ] LLM 结果置信度上限默认低于 structured / deterministic methods。
* [ ] LLM 结果默认只补充高层 narrative structuring，不覆盖 structured numeric facts。

---

## 十三、置信度与决策层要求

* [ ] 置信度必须同时有 `score` 和 `bucket`。
* [ ] 置信度不仅取决于 parser_method，还要考虑：

  * 来源级别
  * 字段完整性
  * 规则校验是否通过
  * 与其他方法是否一致
  * mapping 是否明确
  * 是否为 amendment / unusual layout
* [ ] 决策状态至少包括：

  * `accepted`
  * `accepted_with_warning`
  * `needs_review`
  * `dropped`
* [ ] 系统必须显式给出“为什么被接受 / 为什么进入复核 / 为什么被丢弃”。

---

## 十四、存储与 ClickHouse 要求

* [ ] 所有主表 append-only。
* [ ] 至少包括：

  * `filing_index`
  * `filing_document`
  * `filing_security_link`
  * `extracted_fact`
  * `issuer_facts`
  * `ownership_facts`
  * `holdings_facts`
  * `ingestion_state`
  * `review_queue`
  * `model_registry` / `parser_registry`（可独立表）
* [ ] 所有表都要有确定性自然键或去重键。
* [ ] 必须支持同一 accession 的重复跑批不产生重复事实。
* [ ] 必须支持 original 与 amendment 并存。
* [ ] 不允许通过事后“清洗 SQL”弥补 ingestion correctness。

---

## 十五、QA、监控与审计要求

* [ ] 每日 QA 报表至少包含：

  * 新增 filings 数
  * 抓取失败率
  * 解析失败率
  * parser method 分布
  * auto-accept rate
  * review rate
  * low-confidence rate
  * unmapped rate
  * conflict rate
  * amendment retention coverage
  * duplicate-skip rate
* [ ] 必须支持按 form / route / parser_method / fact_type 分层看指标。
* [ ] 必须有 gold set / audit set 用来估算真实 precision。
* [ ] 必须支持对 auto-accepted 样本做随机抽检。
* [ ] 必须支持回放某个 accession 的完整处理轨迹。

---

## 十六、测试与验收要求

### 单元测试

* [ ] accession normalization
* [ ] form canonicalization / route dispatch
* [ ] amendment grouping
* [ ] raw store hashing and dedup
* [ ] deterministic parsers per form family
* [ ] security mapping precedence
* [ ] confidence / decision rules
* [ ] review queue reason generation
* [ ] spaCy inference adapter
* [ ] LLM schema validation

### 集成测试

* [ ] cold-start happy path
* [ ] incremental idempotency
* [ ] original + amendment 同时保留
* [ ] 13F 独立 discovery
* [ ] structured parser 失败后 fallback 到 deterministic / spaCy / LLM
* [ ] structured source 与低优先级提取冲突时的裁决
* [ ] review queue 与 audit trail 完整性

### 建议默认验收阈值

这些阈值建议作为第一版默认门槛，后续可按真实标注集微调：

* [ ] 关键 numeric / identifier facts 的 auto-accepted precision 目标：**≥ 99%**
* [ ] exact-ID security mapping precision 目标：**≥ 99%**
* [ ] narrative structuring 的 auto-accepted precision 目标：**≥ 95%**
* [ ] 人工复核率要能按 form/fact type 明显下降，并以不降低 precision 为前提
* [ ] 新版 spaCy 模型若不能在 precision 不下降的前提下降低 review rate，则不得推广

---

## 十七、agent 的实施任务拆分

### Phase 1：基础骨架

* [ ] 建 package / config / enums / models / schema / CLI
* [ ] 固化 routes、forms、amendment rules、event time rules
* [ ] 建 ingestion state 与 idempotent keys

### Phase 2：抓取与 raw archive

* [ ] SEC client
* [ ] issuer/owner discovery
* [ ] 13F filer-stream discovery
* [ ] raw artifact persistence
* [ ] replayable fetch trace

### Phase 3：高优先级确定性解析

* [ ] ownership XML parser
* [ ] 13F information-table parser
* [ ] issuer HTML/DOM/rule parser
* [ ] evidence/snippet locator
* [ ] mandatory field matrix

### Phase 4：fallback 与决策层

* [ ] parser cascade engine
* [ ] conflict resolution
* [ ] confidence scoring
* [ ] review queue
* [ ] audit trail persistence

### Phase 5：security mapping

* [ ] exact-ID mapping
* [ ] ticker history
* [ ] fuzzy issuer fallback
* [ ] ambiguity guard
* [ ] mapping QA metrics

### Phase 6：spaCy 微调支持

* [ ] spaCy inference adapter
* [ ] training data format
* [ ] reviewed correction feedback loop
* [ ] model registry / versioning / shadow mode
* [ ] evaluation pipeline

### Phase 7：LLM snippet structuring

* [ ] schema-constrained extractor
* [ ] prompt / response validation
* [ ] no-hallucination guardrails
* [ ] narrative-only usage policy
* [ ] parser precedence integration

### Phase 8：QA 与验收

* [ ] daily QA reporting
* [ ] benchmark on gold set
* [ ] random audit sampling
* [ ] runbook
* [ ] full end-to-end tests

---

## 十八、明确禁止的实现方式

* [ ] 禁止让 LLM 负责 SEC 数据抓取或 filing discovery。
* [ ] 禁止让 LLM 直接从整篇 filing 生成完整事实集。
* [ ] 禁止让 LLM 作为最终 truth reviewer。
* [ ] 禁止用 ClickHouse `FINAL` / `UPDATE` 当作正确性的主要保障。
* [ ] 禁止把 amendment 覆盖成单一最终状态。
* [ ] 禁止没有 evidence/snippet 就写 fact。
* [ ] 禁止 fuzzy security mapping 无歧义检查直接自动入库。
* [ ] 禁止没有模型版本和评估报告就上线 spaCy 微调模型。

---

## 一段可直接发给 agent 的任务说明

请构建一个 precision-first 的 SEC filing backend。系统必须支持 cold-start 与 incremental ingestion，按 issuer / owner / holdings(13F) 三条 route 抓取 SEC filings，先保存 raw filing 与 document，再做标准化、解析、security mapping 与 ClickHouse append-only 落表。必须保留 original 与 amendment，使用 ETL-side deterministic dedup 保证幂等，不能依赖 ClickHouse UPDATE/FINAL。解析必须采用受控 fallback：structured XBRL/XML > official table > deterministic rule parser > spaCy > LLM structuring。目标是最大化真实正确率并最小化人工复核；不确定时宁可不产出 fact。所有 fact 必须带 evidence snippet、locator、parser_method、confidence、decision_state。spaCy 微调是正式能力，要支持训练数据沉淀、模型版本化、shadow evaluation 与 reviewed feedback loop，用来持续降低 review rate。LLM 仅用于对已定位 narrative snippet 做 schema-constrained structuring，不得用于 SEC 抓取、truth verification、security mapping final decision 或整篇 filing 的自主抽取。基础能力与路线要求沿用现有方案中的 cold-start/incremental、raw persistence、13F 独立 route、append-only、evidence/confidence、amendment preservation 等约束。 