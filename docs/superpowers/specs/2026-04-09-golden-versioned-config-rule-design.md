# Golden Set Versioned-Config Rule Restoration Design

## 目标
把原始 strict golden-set 计划中“关键领域知识必须沉淀到版本化配置与测试中”的要求，重新以**硬规则**形式恢复到 `GOLDEN_SET.md`。目标不是增加新的实现细节，而是把已经有些隐含、力度变弱的要求重新写成明确规范。

## 背景
当前 `GOLDEN_SET.md` 已经包含：
- concept registry 必须 versioned
- seed ticker rationale 必须保留
- reproducible manifest 要记录 config paths 等元数据

但原计划中的要求更强：
- concrete XBRL concept candidates
- fallback derivation formulas
- executable invariants
- curated seed tickers with rationale
- regression / validation cases

都不应只存在 narrative docs，而必须进入 versioned config and tests。

当前主文档里这层约束已经存在方向感，但还不够像“必须如此”的硬要求。

## 设计目标
这次改动必须满足：
- 只改 `GOLDEN_SET.md`
- 不改变整体结构
- 明确恢复“版本化配置与测试沉淀”这条 hard rule
- 让读者清楚知道：叙述性文档不是权威载体，配置和测试才是可执行规范的落点

## 推荐方案
在 `GOLDEN_SET.md` 的规范性部分新增一条 **Hard Rule**，推荐放在 truth-tier / schema / metric 之前的约束区，或者放在现有 governance rules 前后，作为一条明确要求。

建议规则表达的核心含义是：

- Concrete XBRL concept candidates must live in versioned config.
- Fallback derivations must live in versioned config.
- Executable invariants must live in versioned config.
- Curated seed tickers and their rationale must live in versioned config.
- Key regression / validation cases must live in tests or structured golden fixtures.
- Narrative documentation may explain these, but narrative docs are not the authoritative executable source.

## 建议写法
推荐加成一条或一个短小节，语气要明显是 requirement，不是 suggestion。可以接近下面这种表达：

```markdown
## Versioned rule sources

Narrative documentation is not the authoritative source for executable golden-set rules. The following must live in versioned config and tests:

- XBRL concept candidates and source priorities
- Fallback derivation formulas and required inputs
- Executable invariants and tolerances
- Curated seed-ticker sets and their rationale
- Regression / validation cases used to prevent repeat failures

`GOLDEN_SET.md` explains the model, but the enforceable rule surface must be stored in versioned config and test artifacts.
```

也可以压缩成一条 hard rule，只要保持力度足够。

## 非目标
这次不做：
- 不新增 schema 表
- 不展开具体 YAML 路径
- 不展开具体测试文件路径
- 不同时修改 `DEMANDS.md`
- 不补其他问题（如 subject mapping / 6-K）

## 验收标准
完成后应满足：
- `GOLDEN_SET.md` 明确写出：concepts / derivations / invariants / seeds / regression cases 必须进入 versioned config/tests
- 读者不会再把 narrative docs 误解为唯一权威载体
- 文档结构变化最小，不引入新的重复
