# Text Span Selection Rules Design

## 目标
在 `EXTRACTION_METHOD.md` 中补上一段**文本段落 span 的定位与大小控制规则**，用于指导片段型字段（snippet fields）的局部文本选择。目标不是把文档变成实现手册，而是让“什么样的 span 算大小合适”从经验口径提升为可执行的方法规范。

## 设计目标
新内容必须满足：
- 放在 `EXTRACTION_METHOD.md`
- 采用“半实现型”表达：原则 + heuristics + pseudo code
- 明确 span 不是按固定长度切，而是按结构锚点 + 最小充分上下文选择
- 解释什么时候 span 太小、什么时候太大
- 给出一套可落地的 candidate generation / scoring / adequacy check 思路
- 不引入完整实现代码或新模块设计

## 推荐位置
建议在 `EXTRACTION_METHOD.md` 中新增一个独立小节：

`## Text span selection rules`

位置建议放在：
- filing-family routing 之后
- runtime flow / QA gate 之前

这样顺序就是：
1. 先讲 extractor 和 routing
2. 再讲文本 span 如何选
3. 再讲 runtime flow / QA gate / cold-start

## 建议内容结构

### 1. 核心原则
明确写出：
- span 不是按固定字符数切
- 应先按结构（item / section / table neighborhood / paragraph blocks）定位
- 目标是选择 **最小充分上下文**
- 默认应做到 **0 次 LLM 预筛 + 1 次主 LLM 抽取**，只在结果显示 span 不合适时才重试

### 2. 结构化切块
增加一个简短说明：
- 文档应先切为 block 单位（heading / paragraph / table / footnote / exhibit block）
- span 是若干 block 的组合，而不是裸字符截断

可加入轻量 pseudo code：

```python
@dataclass
class Block:
    kind: str
    text: str
    heading_path: list[str]
    start_char: int
    end_char: int
```

### 3. SpanPolicy 概念
引入轻量配置概念，而不是完整实现承诺。
说明每类 snippet field 可以定义：
- anchor headers / items
- min / preferred / max token budget
- expand steps
- must_include / avoid patterns
- max_parallel_targets

可加入 pseudo code：

```python
@dataclass
class SpanPolicy:
    field_name: str
    anchor_headers: list[str]
    min_tokens: int
    max_tokens: int
    preferred_tokens: tuple[int, int]
    expand_steps: tuple[int, ...]
```

### 4. 候选 span 生成与打分
说明流程：
- 先找 anchor block
- 再构造多个候选 span
- 对候选 span 打分
- 在合格候选里选最短那个

需要讲清楚评分维度：
- token 长度是否在 preferred range
- 是否命中正确 heading/item
- 是否只包含一个目标对象
- 是否包含关键术语 / 单位 / recommendation / conclusion
- 是否混入多个 proposal / 多个事件 / 多个主体

可加入伪代码，但保持简洁。

### 5. 过小 / 过大的判断信号
必须明确两类信号：

#### 过小
- 主体不清
- 关键信息缺失
- 输出 `unclear`
- confidence 很低
- 单位/币种/否定词缺失

#### 过大
- 出现多个目标对象
- 多个 proposal / event / table 混在一起
- 输出混入无关内容
- rerun 波动大

### 6. Adequacy check 与重试策略
明确写出：
- 不需要默认两次 LLM
- 第一次 LLM 输出即可顺带返回 adequacy signals（例如 `confidence`, `sufficient_context`, `multiple_candidate_targets`）
- 只有在 adequacy 不通过时，才扩窗或缩窗重试

这部分建议明确成一句规则：
> 默认一次主 LLM 调用即可；只有在输出明确显示 span 过小或过大时才触发第二次尝试。

### 7. 边界说明
需要明确：
- 这部分属于 extraction method 规范
- 不属于 `EXTRACTION_FIELDS.md` 的字段定义职责
- 不属于 `GOLDEN_SET.md` 的 truth/evaluation 职责

## 非目标
这次不做：
- 不把完整的 `SpanPolicy` 类和打分器落地成代码
- 不新增新的 YAML 文件
- 不在 `EXTRACTION_METHOD.md` 里写完整实现模块
- 不修改 `EXTRACTION_FIELDS.md` 或 `GOLDEN_SET.md`

## 验收标准
完成后应满足：
- `EXTRACTION_METHOD.md` 明确解释文本 span 如何确定“大小合适”
- 读者能理解最小充分上下文原则
- 读者能理解默认是一轮主 LLM、必要时才重试
- 文档里出现 candidate generation / scoring / adequacy check 的可落地思路
- 新增内容仍然是方法规范，不是实现代码说明
