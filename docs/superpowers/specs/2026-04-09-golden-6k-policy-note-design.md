# Golden Set 6-K Policy Note Design

## 目标
在 `GOLDEN_SET.md` 中补上一段简短但明确的 6-K policy note，解释 `6-K` 与 `6-K-financial` 在 strict numeric golden set 中的不同定位，消除当前 method doc / field dictionary 已经区分了 6-K，但 truth/evaluation 主文档还没有显式说明的缺口。

## 背景
当前文档状态：

- `EXTRACTION_METHOD.md` 已明确：
  - `6-K-financial` 是 canonical `form_family`
  - statement-style 6-K 走 object/XBRL-first
  - event-style 6-K 走 anchored span/table

- `EXTRACTION_FIELDS.md` 已经把部分字段和 snippet schema 标注到：
  - `6-K-financial`
  - `6-K`

- `GOLDEN_SET.md` 目前没有明确写：
  - 哪些 6-K 进入 strict numeric truth/evaluation path
  - 哪些 6-K 仍只是 event-style current disclosure

## 设计目标
这次补充必须满足：
- 只改 `GOLDEN_SET.md`
- 只补一个短 policy note
- 不重写 channel-type 大表
- 不引入新的 6-K taxonomy 讨论
- 不扩展到实现细节

## 推荐方案
在 `GOLDEN_SET.md` 的 filing-family / source-policy 相关位置，加一段 6-K policy note。推荐放在：
- `Channel types by filing family` 后面的 routing notes 附近，或者
- `Truth source reliability ranking` 前后

## 建议写法
推荐表达核心含义如下：

```markdown
**6-K policy note:** `6-K` is not treated as a default periodic numeric-truth filing family. Only `6-K-financial` cases with explicit financial statements or financial exhibits enter the statement-style numeric truth and evaluation path. Event-style `6-K` disclosures remain current-report / narrative cases unless a field is explicitly modeled otherwise.
```

这段话要达成三件事：
1. 把普通 `6-K` 和 `6-K-financial` 区分开
2. 明确 `6-K-financial` 可以进入 strict numeric truth/evaluation path
3. 明确 event-style `6-K` 不自动进入这条路径

## 非目标
这次不做：
- 不在 `GOLDEN_SET.md` 中大改 filing-family 表
- 不补 subject mapping 以外的新 schema 规则
- 不展开 6-K 的抽取方法细节
- 不修改 `EXTRACTION_METHOD.md` 或 `EXTRACTION_FIELDS.md`

## 验收标准
完成后应满足：
- `GOLDEN_SET.md` 明确写出普通 `6-K` 和 `6-K-financial` 的区分
- 读者能知道只有 `6-K-financial` 默认进入 statement-style numeric truth/evaluation path
- event-style `6-K` 不会再被误读为自动进入 strict numeric truth path
- 改动足够小，不破坏现有结构
