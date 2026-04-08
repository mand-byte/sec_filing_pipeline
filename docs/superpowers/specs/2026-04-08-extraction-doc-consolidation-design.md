# Extraction Documentation Consolidation Design

## 目标
将 `EXTRACTION_METHOD.md` 与 `EXTRACTOR_CORRECTNESS.md` 收敛为一个唯一的抽取方法主文档，最终保留 `EXTRACTION_METHOD.md` 作为 extraction 功能的唯一权威说明。新文档需要保留抽取架构、通道边界、正确性保障、冷启动策略、review gate 与错误闭环，同时删除重复叙述，避免与 `DEMANDS.md` 和 `GOLDEN_SET.md` 边界重叠。

## 背景问题
当前 extraction 相关知识被拆成两份文档：

- `EXTRACTION_METHOD.md`：偏方法设计、registry、extractor 类型、按文档类型落地。
- `EXTRACTOR_CORRECTNESS.md`：偏正确性分层、冷启动、review gate、错误闭环。

两者有明显重复：
- 都在表达 `edgartools > XML/xpath > anchored regex > LLM` 的优先级。
- 都在讲 6 个 extractor / tier 分层。
- 都在解释为什么不用 spaCy。
- 都在讨论 QA / review / 冷启动思路。

结果是抽取方法的核心规则被重复维护，未来很容易再次漂移。

## 设计目标
新的 `EXTRACTION_METHOD.md` 必须满足：

- 成为 extraction 功能的唯一主文档。
- 保留抽取系统的核心实现边界：registry、6 个 extractor、routing、runtime flow。
- 吸收 `EXTRACTOR_CORRECTNESS.md` 中真正独特且长期有效的内容：正确性边界、冷启动策略、review gate、错误闭环。
- 不与 `GOLDEN_SET.md` 重复 truth-tier、strict evaluation、schema/metrics/phase-gate 规则。
- 不与 `DEMANDS.md` 重复项目级目标与 roadmap，只保留 extraction 直接相关的方法论。

## 非目标
新文档不承担以下职责：

- 不重复 `GOLDEN_SET.md` 中的 Gold / Silver / Invariant 定义与 strict denominator 指标。
- 不重复 `DEMANDS.md` 的项目目标、全局 roadmap、产品/UI 需求。
- 不保留重复版的“edgartools 优先”总结段落超过一次。
- 不保留两个文档并行存在。

## 推荐方案
采用“单主文档合并”方案：

- 以 `EXTRACTION_METHOD.md` 为保留文件。
- 将 `EXTRACTOR_CORRECTNESS.md` 中有价值但未在 `EXTRACTION_METHOD.md` 中表达完整的内容并入。
- 删除 `EXTRACTOR_CORRECTNESS.md`。
- 如有必要，只更新少量引用，让仓库里关于 extraction method 的正式文档只剩一个。

## 新 `EXTRACTION_METHOD.md` 的目标结构

### 1. 文档定位
开头明确说明：
- 本文档是 extraction method 的唯一权威说明。
- 关注抽取架构、通道选择、正确性保障与冷启动策略。
- Golden truth / strict evaluation 细则见 `GOLDEN_SET.md`。

### 2. 核心技术结论
保留一次且只保留一次：
- `edgartools (obj/xbrl) > XML/xpath > anchored regex > LLM normalization`
- `spaCy` 不进入当前方案
- 核心组合是 `edgartools + declarative registry + QA/review gate`

### 3. Field registry 与 6 个 extractor
保留并整理：
- field registry 的 declarative schema
- `ObjPathExtractor`
- `XbrlConceptExtractor`
- `XmlPathExtractor`
- `AnchoredTableExtractor`
- `AnchoredSpanExtractor`
- `LlmSpanNormalizer`

要求：
- 这部分主要回答“系统怎么抽”。
- 不重复 golden set truth 定义。

### 4. 文档类型 / 通道映射
保留按 filing family 的落地策略：
- `10-K / 10-Q / 20-F / 部分 6-K` → XBRL-first / obj-first
- `8-K / 6-K event` → item-aware / anchored span
- `DEF 14A` → HTML/table-first + 局部结构化
- `3 / 4 / 5` → XML/object-first
- `13D / 13G` → object/XML-first
- `144` → object/XML-first
- `13F` → holdings/info table-first

要求：
- 这里只解释 extraction routing。
- 若和 `GOLDEN_SET.md` 有相似点，以“抽取执行策略”角度写，不重复 truth ranking 全文。

### 5. 正确性边界与 tier 分层
将 `EXTRACTOR_CORRECTNESS.md` 的强项并进来：
- Tier 1 / Tier 2 / Tier 3 的正确性边界
- 每层为什么可靠或不可靠
- 每层常见失败模式
- 每层的保障手段

要求：
- 这一节保留“正确性工程”视角。
- 避免和 `GOLDEN_SET.md` 的 invariant / strict metrics 章节混淆。

### 6. Runtime flow 与 QA gate
保留：
- `extract_field()` 伪代码
- `locator_kind` / `lineage` / evidence 存储要求
- QA gate 的作用和基本规则
- 防膨胀规则（最多 3 个 locator / alias 上限 / LLM span 大小 / 新规则必须来自回归）

### 7. 冷启动与 review gate
从 `EXTRACTOR_CORRECTNESS.md` 合并：
- Phase 0 / 1 / 2 / 3 的冷启动策略
- Tier 1 only → 再开放 Tier 2 → 再开放 LLM 的递进策略
- `cold_start_review_gate()` 这类代表性规则
- 首次 issuer / 首次模板 / 历史异常偏差进入 review 的原则

### 8. 错误闭环
保留并强化：
- `error_code`
- `golden_case`
- `patch`
- 人工修正后如何进入回归集
- 什么情况只做 one-off override，不上升为通用规则

这一节是 `EXTRACTOR_CORRECTNESS.md` 最值得保留的独特内容之一，应该成为新主文档的一部分。

### 9. 与其他文档的边界
新增一个明确章节：

- `DEMANDS.md`：项目目标、总原则、roadmap
- `EXTRACTION_METHOD.md`：抽取方法、routing、正确性工程、冷启动与 review
- `GOLDEN_SET.md`：truth tiers、golden schema、strict evaluation、artifact、phase gates

这样能减少将来再次重复。

## 内容迁移规则

### 从 `EXTRACTION_METHOD.md` 保留
- field registry 设计
- 6 个 extractor 设计
- filing family routing
- runtime flow
- 防膨胀规则

### 从 `EXTRACTOR_CORRECTNESS.md` 保留
- Tier 1/2/3 正确性边界
- 冷启动 phase 策略
- `cold_start_review_gate()` 示例
- 错误闭环（`error_code + golden_case + patch`）
- 为什么不用 spaCy 的完整论证

### 必须删除或改写
- 两份文档里重复表达的优先级总结，只保留一次
- 重复的 extractor 列表说明，只保留一次
- 与 `GOLDEN_SET.md` 重叠的 truth-tier / strict evaluation 叙述
- 与 `DEMANDS.md` 重叠的 roadmap / 总目标段落

## 最终文档状态
合并完成后：
- `EXTRACTION_METHOD.md` — extraction 功能唯一主文档
- `EXTRACTOR_CORRECTNESS.md` — 删除

## 风险与防漂移策略
- 如果继续保留 `EXTRACTOR_CORRECTNESS.md`，抽取方法与正确性规则会继续双份维护。
- 如果把 golden-set 评估逻辑也并进 `EXTRACTION_METHOD.md`，会再次与 `GOLDEN_SET.md` 边界混乱。
- 因此新主文档必须只覆盖 extraction method 和 correctness engineering，不覆盖 strict truth modeling。

## 实施验收标准
合并完成后，应满足：
- extraction 相关正式文档只剩一个主文档：`EXTRACTION_METHOD.md`
- `EXTRACTION_METHOD.md` 仍能回答“怎么抽”与“怎么防错”两个问题
- `EXTRACTOR_CORRECTNESS.md` 的独特内容已被保留，不是简单删除
- `EXTRACTION_METHOD.md` 不再与 `GOLDEN_SET.md` 大段重复
- `EXTRACTION_METHOD.md` 不再与 `DEMANDS.md` 大段重复
- 仓库中无正式引用继续指向 `EXTRACTOR_CORRECTNESS.md`（如存在则更新）
