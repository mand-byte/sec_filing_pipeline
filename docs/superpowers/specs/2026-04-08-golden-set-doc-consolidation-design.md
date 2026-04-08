# Golden Set 文档合并设计

## 目标
将 `GOLDEN_SET.md` 与 `GOLDEN_SET_PLAN.md` 合并为一个新的唯一权威文档，最终保留 `GOLDEN_SET.md` 作为 golden set 功能的唯一说明。新文档必须消除旧版 mixed-truth 叙述、删除重复或易过时的执行细节，并补充 edgartools 通道边界、文档类型映射、truth source 可信度排序、交叉验证与会计恒等式方法。

## 背景问题
当前存在两个问题：

1. `GOLDEN_SET.md` 仍包含旧版混合 truth 设计，和 strict v2 模型存在歧义。
2. `GOLDEN_SET_PLAN.md` 同时承担规范文档和实施清单的角色，信息很全，但包含大量会快速过时的 task/test/commit 细节。

结果是：golden set 相关知识被分散在两个文档中，且同一概念在两处的定义层级不一致。

## 设计目标
新 `GOLDEN_SET.md` 必须满足：

- 一个功能只保留一个文档。
- 作为 strict numeric golden set v2 的唯一权威说明。
- 既保留最终规则，也保留必要的领域知识，不再依赖 `GOLDEN_SET_PLAN.md` 才能理解全貌。
- 明确 edgartools 的适用边界：哪些文档类型应走 XBRL，哪些应走 `filing.obj()` / XML / HTML。
- 明确 cross-check / invariants 的角色：用于验证，不作为 gold truth。
- 删除逐 task checklist、pytest 命令、commit message 模板等执行手册式内容。

## 非目标
新文档不承担以下职责：

- 不再作为逐步实施清单。
- 不记录具体 failing test 文本、pytest 命令、git commit 文案。
- 不保留“代码落地后再重写本文档”这类过渡性描述。
- 不重复 `DEMANDS.md`、`EXTRACTION_METHOD.md` 中的通用提取架构，只保留与 golden set 直接相关的规则。

## 推荐合并方案
采用“规范主文档”方案：

- 以 `GOLDEN_SET_PLAN.md` 中的 strict v2 规则为骨架。
- 吸收 `GOLDEN_SET.md` 中仍有价值的领域知识（concept candidates、cross-check 公式、seed ticker 理由、部分表单覆盖说明）。
- 生成一个新的 `GOLDEN_SET.md`。
- 删除或退役 `GOLDEN_SET_PLAN.md`，避免双文档并存。

## 新 `GOLDEN_SET.md` 的目标结构

### 1. 文档定位与范围
说明该文档是 strict numeric golden set 的唯一权威说明，覆盖：
- truth tiers
- 53 个 canonical numeric fields
- case / subject 粒度
- source/channel 规则
- invariants / cross-check
- schema / metrics / artifacts / sampling

### 2. Truth tiers
明确三层：
- **Gold**：仅允许 `manual_adjudication`、`raw_xbrl`、`raw_xml`
- **Silver**：`companyfacts`、`edgartools_obj` 等辅助来源
- **Invariant**：会计恒等式、内部一致性、sum/count/range checks

必须明确：
- silver 不参与 strict gold accuracy
- invariant 永远不是 truth

### 3. 通道类型与文档类型映射
新增一个固定章节，定义四类主通道：
- `XBRL-first`
- `Object/XML-first`
- `HTML/anchored-table-first`
- `Manual adjudication`

并按文档类型映射：
- `10-K` / `10-Q` / `20-F` → `XBRL-first`
- `8-K` → `filing.obj()` / item-aware / exhibit-aware，必要时局部取财务附件
- `DEF 14A` → HTML/table-first；个别字段可局部使用结构化来源
- `3` / `4` / `5` → `Object/XML-first`
- `13D` / `13G` → `Object/XML-first`
- `13F-HR` → `Object/XML-first`
- `144` → `Object/XML-first`
- `S-1` / `424B4` / `SC TO-I` / `SC 13E3` → 按字段分流，通常需要 raw filing + anchored parsing + manual review

### 4. Truth source reliability ranking
新增 ranking 规则，避免不同来源混用：

#### 财务报表型 filing
- `xbrl-querying` ≈ `getting-xbrl`
- `extract-statements`
- `company-facts`

解释：
- `xbrl-querying` / `getting-xbrl` 最接近单 filing raw XBRL，最适合 strict truth
- `extract-statements` 是高质量 statement abstraction，但比 raw fact 更抽象一层
- `company-facts` 属于 SEC 聚合 facts，只能作为 silver/bootstrap/surveillance

#### XML / object 型 filing
- `raw_xml`
- `filing.obj()` / typed object
- anchored HTML/XML parse
- manual adjudication

说明：对 3/4/5、13D/G、13F、144 等表单，主可信来源不是 XBRL，而是原始 XML 与对象化解析。

### 5. Canonical field inventory
保留并冻结 53 个 unique numeric fields，强调：

> 同一个 canonical field 在不同 form family 的重复出现，不增加字段总数。

保留 subject-type counts：
- `(issuer, filing)=20`
- `(issuer, proposal)=4`
- `(issuer, executive)=1`
- `(issuer, holder_row)=2`
- `(owner, transaction_row)=6`
- `(owner, reporting_person)=8`
- `(owner, form144_notice)=4`
- `(holding, holding_position)=5`
- `(holding, filing)=3`

### 6. Case / subject / record grain
保留 strict 粒度规则：
- 每条 truth keyed by `case_id + subject_id + field_name`
- filing-level truth 不能覆盖 multi-row subjects
- amendment 和 point-in-time metadata 必须显式存储

必须说明多行表单示例：
- Form 4 transactions
- 13F positions
- proposal vote rows
- executive comp rows
- holder beneficial ownership rows

### 7. Cross-check 与会计恒等式
新增一个明确章节，说明验证方法分层，并强调它们是 invariant，不是 truth。

建议按以下类型组织：

#### 7.1 报表类恒等式
- `diluted_eps ≈ net_income / shares_outstanding`
- `total_revenue >= operating_income`
- `cash_and_equivalents >= 0`
- `total_debt >= 0`

#### 7.2 发行/招股类勾稽
- `gross_proceeds ≈ offering_price_per_share × securities_offered_qty`
- `net_proceeds ≈ gross_proceeds - underwriter_discount_total`
- `offering_price_per_share > 0`

#### 7.3 所有权/交易类勾稽
- `shares_owned_following_txn == prior_balance + shares_acquired_or_disposed`
- `transaction_price_per_share > 0`
- `beneficial_ownership_pct ∈ [0,100]`
- `sole_voting_power + shared_voting_power >= beneficially_owned_shares`（通常）

#### 7.4 13F 汇总勾稽
- `sum(position_value_usd) ≈ info_table_value_total_usd`
- `count(positions) == info_table_entry_total`
- `sole_voting_auth_shares + shared_voting_auth_shares + none_voting_auth_shares == shares_or_principal_amount`

#### 7.5 适用性与约束说明
- invariant 失败不等于 truth 错误，但必须进入 mismatch / review 流程
- invariant pass 也不能单独提升为 gold truth
- 某些公式只在特定 subject / form / context 下适用，需允许 `not_applicable`

### 8. Concept registry 与 seed knowledge
保留旧文档中仍有价值的领域知识，但从叙述改成规则化表达：
- XBRL concept candidates
- fallback derivation
- invariant formulas
- curated seed tickers 与 rationale

强调这些内容应作为版本化配置的来源说明，而不是散落叙述。

### 9. Schema / artifacts / metrics
保留 strict v2 的核心定义：
- `golden_case`
- `golden_subject`
- `golden_truth`
- `golden_invariant_result`
- `golden_candidate`
- `golden_eval_run`
- `golden_eval_result`
- `golden_review_packet`

保留 artifact contract 与 metric definitions：
- `gold_strict_accuracy`
- `gold_coverage`
- `row_selection_accuracy`
- `not_applicable_precision`
- `silver_alignment`
- `invariant_pass_rate`

### 10. Sampling 与 phase gates
保留相对稳定的 phase 目标和 gate：
- domestic seed
- ADR / 20-F coverage
- amendment pairs
- multi-row entity cases
- historical expansion

删除会快速过时的部分：
- 每个 task 的 pytest 命令
- failing test 预期
- commit message 模板
- day-by-day 时间线估算

## 内容迁移规则

### 从 `GOLDEN_SET_PLAN.md` 保留
- strict truth tiers 逻辑
- 53 字段冻结清单
- subject 粒度与 schema
- artifact contract
- metrics
- phase gates

### 从 `GOLDEN_SET.md` 保留
- concept candidate 例子
- cross-check / invariant 公式
- seed ticker 选择理由
- 对不同表单家族的部分 field coverage 经验

### 必须删除或改写
- `A: companyfacts / B: xml_obj / C: cross_validate / D: manual_seed` 这套旧 truth strategy 章节
- 将 invariant 当成 truth 的表达
- 将 `companyfacts` / `edgartools_obj` 直接写成 gold truth 的表达
- 逐任务测试/提交步骤
- 与 strict v2 不一致的字段统计口径

## 最终文档状态
合并完成后，仓库中关于 golden set 只保留一个面向使用者和实现者的文档：
- `GOLDEN_SET.md` — 唯一权威文档

`GOLDEN_SET_PLAN.md` 应删除，避免出现第二份并行规范。

## 风险与防漂移策略
- 若继续保留 `GOLDEN_SET_PLAN.md`，未来极易再次分叉。
- 若新文档混入实施 checklist，它会再次变成过时计划书。
- 因此新 `GOLDEN_SET.md` 必须坚持“规范优先、实现细节最小化”。

## 实施验收标准
文档合并完成后，应满足：
- 读者无需再打开 `GOLDEN_SET_PLAN.md` 才能理解 golden set 全貌
- 文档中明确写出通道类型 × 文档类型映射
- 文档中明确写出 edgartools 边界与 truth source ranking
- 文档中明确写出 cross-check / 会计恒等式 / invariant 方法
- 文档中不再保留旧 mixed-truth 术语
- 仓库中 golden set 功能只保留一个正式文档
