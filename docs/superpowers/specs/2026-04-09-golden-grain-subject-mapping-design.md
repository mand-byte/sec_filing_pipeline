# Golden Set Grain-to-Subject Mapping Design

## 目标
在 `GOLDEN_SET.md` 中补上一段明确的 **field-dictionary granularity → golden subject type** 映射说明，解决当前字段字典粒度与 strict golden-set subject identity 之间的隐含关系没有被显式写出的缺口。

## 背景
当前文档体系里存在两套合理但未桥接的概念：

### 字段字典粒度（`EXTRACTION_FIELDS.md`）
- `document`
- `security_line`
- `proposal_line`
- `exec_line`
- `holder_line`
- `transaction_line`
- `position_line`
- `derivative_line`
- `filer_line`
- `sale_notice`

### golden-set subject types（`GOLDEN_SET.md`）
- `filing`
- `proposal`
- `executive`
- `holder_row`
- `transaction_row`
- `reporting_person`
- `form144_notice`
- `holding_position`

读者现在能分别看懂两边，但不容易直接知道这两套概念如何对应。

## 设计目标
这次补充必须满足：
- 只改 `GOLDEN_SET.md`
- 以映射说明的形式补桥接规则
- 不重写 `EXTRACTION_FIELDS.md`
- 不新增新的 subject type
- 不把 extraction grain 和 evaluation subject 混成同一概念

## 推荐方案
在 `GOLDEN_SET.md` 中新增一个很短的小节，例如：

- 放在 “Canonical 53-field freeze and subject-type distribution” 之后，或
- 放在 “Strict case/subject schema concepts” 之前/之后

内容用一个小表表达：

| Field dictionary grain | Golden subject type |
|---|---|
| `document` | `filing` |
| `proposal_line` | `proposal` |
| `exec_line` | `executive` |
| `holder_line` | `holder_row` |
| `transaction_line` | `transaction_row` |
| `filer_line` | `reporting_person` |
| `sale_notice` | `form144_notice` |
| `position_line` | `holding_position` |

并补一句约束说明：
- `security_line` 和 `derivative_line` 是字段字典中的 extraction granularity labels, not standalone golden subject types.
- 在 strict golden set 中，它们必须映射到具体的 filing- or row-level subject identity，而不是自动引入新的 subject type.

## 为什么这样补
- 这能直接消除当前最主要的跨文档语义缺口。
- 这条映射本身属于 strict evaluation / row identity 的规则，因此应归属 `GOLDEN_SET.md`，而不是 `EXTRACTION_FIELDS.md`。
- 通过只补一个短表，不会重新把文档结构复杂化。

## 非目标
这次不做：
- 不修改 `EXTRACTION_FIELDS.md`
- 不新增 `security_line_subject` 或 `derivative_subject` 一类新类型
- 不补 `6-K` 问题
- 不展开 subject_id 生成规则的实现细节

## 验收标准
完成后应满足：
- `GOLDEN_SET.md` 明确写出字段粒度到 golden subject type 的映射
- 读者能直接知道 `proposal_line` 对应 `proposal`、`filer_line` 对应 `reporting_person` 等关系
- `security_line` / `derivative_line` 不会再被误读为需要新增 golden subject type
- 结构变化最小，不引入新的重复
