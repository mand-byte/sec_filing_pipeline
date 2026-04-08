# EXTRACTION_FIELDS.md Field-Dictionary Design

## 目标
将 `EXTRACTION_FIELDS.md` 明确收敛为**字段字典主文档**。它的职责是定义字段清单、粒度、适用表单、字段语义和必要的 schema 约定，而不是承载抽取方法、extractor 选择、truth/source ranking、cold-start、review gate 或 strict golden-set 评估规则。

## 背景问题
当前仓库已经逐步形成三类更清晰的主文档：

- `DEMANDS.md`：项目总目标、总架构、系统边界、roadmap
- `EXTRACTION_METHOD.md`：抽取方法、routing、正确性工程、冷启动与 review
- `GOLDEN_SET.md`：truth tiers、strict schema、evaluation、artifact、phase gates

在这个前提下，`EXTRACTION_FIELDS.md` 最适合承担”字段字典”的角色。但它当前与其他文档之间仍然存在边界风险：
- 容易混入 extraction routing 说明
- 容易混入 truth / validation / golden-set 的细节
- 容易从“字段定义”膨胀成“字段定义 + 实现方法 + 评估方法”的混合文档

## 设计目标
新的 `EXTRACTION_FIELDS.md` 必须满足：

- 成为字段字典主文档。
- 保留字段级信息：
  - canonical field name
  - 粒度
  - 适用表单
  - 语义说明 / 文档中可能出现的对应字段
  - 对片段型字段的输出 schema
- 不负责解释怎么抽，也不负责解释 truth 和评估。
- 让读者回答“要抽哪些字段、字段是什么意思、落在哪个粒度上”。

## 非目标
`EXTRACTION_FIELDS.md` 不再承担这些职责：

- 不解释 extractor 选择与 routing 规则
- 不解释 `ObjPathExtractor` / `XbrlConceptExtractor` / `AnchoredSpanExtractor` 等
- 不解释 Gold / Silver / Invariant truth tiers
- 不解释 strict metrics、artifact、phase gate
- 不解释 cold-start、review queue、error loop

这些职责分别属于：
- `EXTRACTION_METHOD.md`
- `GOLDEN_SET.md`

## 推荐方案
采用“字段字典主文档”方案：

- 保留 `EXTRACTION_FIELDS.md` 这个文件。
- 以字段字典视角重写或整理内容。
- 保留数值字段和片段字段两大部分。
- 如有边界模糊的内容，只保留字段定义，不保留实现与评估方法。

## 新 `EXTRACTION_FIELDS.md` 的目标结构

### 1. 文档定位
开头明确说明：
- 本文档是字段字典主文档。
- 定义“抽什么”，不定义“怎么抽”或“怎么评估”。
- 抽取方法见 `EXTRACTION_METHOD.md`；truth/evaluation 见 `GOLDEN_SET.md`。

### 2. 公共约定
保留适合字段字典的公共约定，例如：
- 公共 metadata 单独维护，不在字段字典里逐行重复
- 数值字段只列能直接入仓、能做因子/监控的字段
- schema 记法说明（如 `number`、`enum[...]`、`boolean` 等）

但不要扩展到方法论。

### 3. issuer / owner / holding 三条 route 的字段字典
保留并整理：
- `issuer route` 数值字段字典
- `issuer route` 片段字段字典
- `owner route` 数值字段字典
- `owner route` 片段字段字典
- `holdings route` 数值字段字典
- `holdings route` 片段字段字典

要求：
- 主要回答字段定义问题。
- 表中保留：统一列名、粒度、适用表单、文档中可能出现的对应字段。
- 对片段型字段保留 JSON schema。

### 4. 字段粒度与 row-type 说明
可以保留字段字典必要的粒度说明，例如：
- `document`
- `security_line`
- `proposal_line`
- `exec_line`
- `holder_line`
- `transaction_line`
- `position_line`

但只从“字段字典”的角度解释，不扩展到 golden-set subject identity 或 schema uniqueness。

### 5. Amendment 公共字段
如果 `/A` overlay 的 4 个公共字段仍有必要保留，可以保留为字段字典附录，因为它仍然是字段层面的定义；但不要把它扩展成评估策略说明。

## 必须删除或压缩的内容类型
从 `EXTRACTION_FIELDS.md` 中删除或压缩这些内容：

- extractor 选择建议
- routing / fallback / QA gate 逻辑
- truth source ranking
- Gold / Silver / Invariant 描述
- strict golden-set schema / metrics / phase gate
- 冷启动与 review queue 逻辑

如果某些句子只是为了说明字段含义而顺带提到这些内容，可以保留最小必要信息，但不能让它再次变成方法文档。

## 与其他文档的边界
清理后四个文档的角色应为：

- `DEMANDS.md` — 总架构 / 总需求文档
- `EXTRACTION_METHOD.md` — 抽取方法主文档
- `EXTRACTION_FIELDS.md` — 字段字典主文档
- `GOLDEN_SET.md` — truth / evaluation 主文档

## 实施验收标准
完成后应满足：
- `EXTRACTION_FIELDS.md` 能独立回答”有哪些字段、字段是什么意思、字段落在哪个粒度上”
- `EXTRACTION_FIELDS.md` 不再承担”怎么抽”与”怎么评估”的职责
- `EXTRACTION_FIELDS.md` 与 `EXTRACTION_METHOD.md` 的边界清楚
- `EXTRACTION_FIELDS.md` 与 `GOLDEN_SET.md` 的边界清楚
- 读者可以从字段字典自然跳转到方法文档或 golden-set 文档，而不会产生角色混淆
