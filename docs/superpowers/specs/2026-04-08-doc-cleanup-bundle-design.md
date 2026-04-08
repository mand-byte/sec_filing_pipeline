# Documentation Cleanup Bundle Design

## 目标
将以下三个收尾动作打包为一次组合清理：

1. 将 `EXTRACTION_FIELDS.md` 重命名为更合理的字段字典文件名
2. 清理 `.claude/worktrees` 等搜索噪声来源
3. 微调 `EXTRACTION_FIELDS.md` 中少量仍带 normalization/implementation 味道的字段定义

目标是一次性解决当前文档体系里最后几处“看上去还没完全收口”的问题，同时不重新打开已经稳定的主文档边界。

## 背景
当前主文档体系已经基本收敛为：

- `DEMANDS.md` — 总架构 / 总需求文档
- `EXTRACTION_METHOD.md` — 抽取方法主文档
- `EXTRACTION_FIELDS.md` — 字段字典主文档
- `GOLDEN_SET.md` — truth / evaluation 主文档

但 repo-wide 审计里仍识别出三类残余问题：

- `EXTRACTION_FIELDS.md` 这个文件名像历史 typo，削弱了字段字典主文档的稳定感。
- `.claude/worktrees/**` 中保留了旧版本文档，污染 grep / glob / 人工巡检结果。
- `EXTRACTION_FIELDS.md` 个别字段定义仍带少量 normalization/semantic-processing 色彩，而不是纯字段字典表达。

## 设计目标
这次组合清理必须满足：

- 一次性完成命名统一、噪声清理、字段字典小修。
- 不重新设计主文档体系。
- 不把 `EXTRACTION_FIELDS.md` 再次改成方法文档或评估文档。
- 不影响 `DEMANDS.md` / `EXTRACTION_METHOD.md` / `GOLDEN_SET.md` 的既有角色。

## 非目标
本次不做：

- 不重写 `EXTRACTION_METHOD.md`
- 不重写 `GOLDEN_SET.md`
- 不再次大改 `DEMANDS.md`
- 不处理 spec/plan 历史文档中的旧引用内容

## 推荐方案：一次性组合清理
采用一次性组合清理，分三部分完成：

### Part 1: 文件名统一
将 `EXTRACTION_FIELDS.md` 重命名为更合理的字段字典文件名。

推荐命名优先级：
1. `EXTRACTION_FIELDS.md`（推荐）
2. `EXTRACTION_FIELD_DICTIONARY.md`

推荐 `EXTRACTION_FIELDS.md` 的原因：
- 简洁
- 可读性好
- 不像 typo
- 仍然清楚表达这是字段清单/字段字典文档

重命名后需要同步更新：
- `DEMANDS.md`
- 文档内部边界表/自指
- 其他仍在正式文档中的引用

### Part 2: worktree 噪声清理
清理 `.claude/worktrees/**` 中已经过期、且主要用于此前文档重构的本地 worktree 快照。

目标不是清理一切 Claude 运行痕迹，而是减少：
- 已删除文档继续在搜索结果中出现
- 旧版 `DEMANDS.md` / `GOLDEN_SET_PLAN.md` / `EXTRACTOR_CORRECTNESS.md` 继续污染审计

要求：
- 只删除本次会话内创建且确认已无后续用途的 worktree 目录
- 不动当前主工作区
- 如果某个 worktree 仍承载未同步内容，则不能删除

### Part 3: 字段字典语义精修
只修少数字段定义，不大改结构。重点是把仍带 processing / normalization 味道的表达收成更纯的字段语义。

优先清理对象：
- `filing_delay_days`
- `proposal_votes_against`
- 任何仍像“派生规则”而不是“字段定义”的单元格

要求：
- 保留字段字典可读性
- 保留必要的语义解释
- 不把字段定义写成实现逻辑

## 建议后的文档边界
清理完成后，主文档体系应为：

- `DEMANDS.md` — 总架构 / 总需求文档
- `EXTRACTION_METHOD.md` — 抽取方法主文档
- `EXTRACTION_FIELDS.md` — 字段字典主文档
- `GOLDEN_SET.md` — truth / evaluation 主文档

## 风险点

### 1. 文件重命名带来的引用遗漏
风险：正式文档或脚本仍引用旧文件名。
应对：在变更后用 grep 对正式文档和常见路径做完整检查。

### 2. 删除 worktree 时误删仍有用的工作副本
风险：删掉仍承载未同步内容的 worktree。
应对：先核对当前需要保留的内容是否都已在主工作区，再删除。

### 3. 语义精修过度，反而损失字段解释性
风险：把字段定义收得太薄，读者反而不理解字段含义。
应对：只改“明显像实现逻辑”的表述，不动大多数行。

## 实施验收标准
完成后应满足：
- 不再存在 `EXTRACTION_FIELDS.md` 这个易混淆文件名（已更名为 `EXTRACTION_FIELDS.md`）
- 正式文档引用全部改到新字段字典文件名
- `.claude/worktrees` 中的旧文档快照不再持续污染搜索结果
- 新字段字典文件仍能独立回答“有哪些字段、字段是什么意思、字段在哪个粒度上”
- 少数问题字段的定义语义更纯净，但整体结构不变
- 四个主文档的角色仍然清晰、稳定
