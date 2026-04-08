# DEMANDS.md Deduplication Design

## 目标
在不改变 `DEMANDS.md` 作为“总架构/总需求文档”定位的前提下，清理它与 `EXTRACTION_METHOD.md`、`GOLDEN_SET.md` 的重复表述。目标不是压缩成高层 PRD，而是让 `DEMANDS.md` 保留项目级目标、系统边界、数据源、调度、产品要求与 roadmap，同时把已经被专门文档接管的细节改写成“总原则 + 链接”。

## 背景问题
当前仓库已经形成更清晰的主文档边界：

- `EXTRACTION_METHOD.md`：抽取方法、routing、正确性工程、冷启动与 review
- `GOLDEN_SET.md`：truth tiers、strict schema、evaluation、artifact、phase gates
- `DEMANDS.md`：项目总目标、总架构、系统边界、roadmap

但 `DEMANDS.md` 里仍保留了一些容易与这两个主文档重复的技术表述，特别是：
- 抽取策略的技术细节
- golden set v2 的技术性描述
- roadmap 中对技术层级的重复解释

这些内容并非完全错误，但会造成边界发散，后续维护容易再次漂移。

## 设计目标
新的 `DEMANDS.md` 必须满足：

- 继续作为总架构/总需求文档存在。
- 保留项目级目标、架构原则、数据边界、系统入口、UI/产品要求、roadmap。
- 对 extraction method 与 golden set 的技术细节，只保留项目级原则与链接。
- 不删除那些只有 `DEMANDS.md` 才适合承载的内容，例如：
  - ClickHouse / PostgreSQL 数据源边界
  - 退市处理规则
  - 调度与无状态游标原则
  - Side-by-side 审核 UI 要求
  - 阶段性 roadmap

## 非目标
这次不做：

- 不重写 `DEMANDS.md` 的整体结构。
- 不删除 roadmap。
- 不把 `DEMANDS.md` 改成极简文档。
- 不把 `DEMANDS.md` 中的项目级原则移走。

## 推荐方案：轻量去重
采用“轻量去重”方案：

- 保留 `DEMANDS.md` 的现有章节结构。
- 对重复最明显的两处做收敛：
  1. **分层抽取策略**：保留一句项目级原则 + 链接 `EXTRACTION_METHOD.md`
  2. **Golden Set V2**：保留一句项目级原则 + 链接 `GOLDEN_SET.md`
- 对 roadmap 中重复解释具体 extractor/tier 的段落，只做轻微压缩，不移除整个 roadmap。

## 建议修改点

### 1. 第二章“架构选型与核心原则”
保留三条原则，但减少重复解释：

#### 1. 分层抽取策略
保留：
- `edgartools (XBRL / Obj) -> XML/HTML -> anchored regex -> LLM normalization`
- 不使用 spaCy
- 链接到 `EXTRACTION_METHOD.md`

删除或压缩：
- 已经在 `EXTRACTION_METHOD.md` 详细展开的 extractor 级解释
- 与 runtime routing / cold-start / QA gate 相关的细节

#### 2. Golden Set V2
保留：
- 摒弃混合真值统计
- 独立可审计的 gold/silver/invariant 数据集
- 版本化配置沉淀 concepts / formulas / test cases
- 链接到 `GOLDEN_SET.md`

删除或压缩：
- 已经被 `GOLDEN_SET.md` 详细展开的 truth-tier / denominator / schema / phase gate 细节

### 2. Roadmap 章节
保留 roadmap 本身，但对技术细节做轻量收敛：

- 可以保留“第一期做 Tier 1 抽取器、冻结配置、落地 golden schema”这类阶段目标。
- 但避免写出会与专门文档重复、且未来更容易过时的技术说明。
- 例如：
  - 可以说“完成确定性最高的 Tier 1 抽取器”
  - 不必在 `DEMANDS.md` 再解释 Tier 1/Tier 2 各自的全部语义，因为这已由 `EXTRACTION_METHOD.md` 承担

### 3. 与其他文档的边界
建议在 `DEMANDS.md` 的“架构原则”或结尾增加一小段边界说明，形式可以很简短：

- `DEMANDS.md`：项目级目标、边界、路线图
- `EXTRACTION_METHOD.md`：抽取执行方法与正确性工程
- `GOLDEN_SET.md`：truth / evaluation / artifact / release gate

这会帮助未来维护时不再把细节回写进 `DEMANDS.md`。

## 最终文档边界
清理后，三个文档的角色应为：

- `DEMANDS.md` — 总架构/总需求文档
- `EXTRACTION_METHOD.md` — extraction 方法主文档
- `GOLDEN_SET.md` — golden set / truth / evaluation 主文档

## 实施验收标准
完成后应满足：
- `DEMANDS.md` 仍然能独立说明项目是什么、系统怎么分层、路线图是什么
- `DEMANDS.md` 不再大段重复 `EXTRACTION_METHOD.md` 的方法细节
- `DEMANDS.md` 不再大段重复 `GOLDEN_SET.md` 的 truth/eval 细节
- 读者能从 `DEMANDS.md` 顺利跳转到两个主文档，而不会产生角色混淆
- `DEMANDS.md` 的总体信息密度基本不下降，只是边界更清晰
