
**1）先吃结构化数据**
优先用 edgartools 已经给你的 typed object / DataFrame。当前文档里，`filing.obj()` 已能把很多你关心的表单变成结构化对象；通用 `Filing` 还支持 `xbrl()`, `search()`, `sections()`, `parse()`, `text()/markdown()` 这些入口。你列的范围里，官方文档已明确覆盖了 8-K、Form 3/4/5、13D/G、13F、DEF 14A、424B、S-1、144 等典型对象。([EdgarTools][1])

**2）再吃 XBRL / XML schema**
SEC 现在仍然为 Ownership（3/4/5）、13F、Form 144、Schedule 13D & 13G 等 XML 表单公开 technical specifications；Ownership XML 规范还明确要求 primary document 必须符合相应 XML schema。也就是说，这几类表单不该从“全文正则”开始，而该从 **XML path / edgartools 对象属性** 开始。([SEC][2])

所以，落地上我建议你这样选：

**映射关系：要维护，但只维护“字段 registry”**
不是维护一个无限膨胀的 `form x 字段别名 x 正则` 大表，而是维护一个很小的 declarative registry。每个 canonical field 只记录：

* 适用的 `form_family`
* 定位链路 `locators`
* 归一化规则 `normalizer`
* 质检规则 `qa`

像这样：

```yaml
field: total_revenue
form_family: [10-K, 10-Q, 20-F, 6-K-financial]
locators:
  - kind: xbrl_concept
    concepts: [Revenue, Revenues, SalesRevenueNet]
    statement_type: IncomeStatement
    period: current
    unit: USD
  - kind: obj_statement_row
    object_path: financials.income_statement
    row_aliases: ["Revenue", "Net sales", "Sales", "Total revenues"]
  - kind: anchored_table
    section_aliases: ["Consolidated Statements of Operations", "Income Statement"]
    row_aliases: ["Revenue", "Net sales", "Sales"]
normalizer:
  type: currency
qa:
  nonnegative: true
  max_abs: 1e15
```

```yaml
field: beneficial_ownership_pct
form_family: [13D, 13G]
locators:
  - kind: obj_path
    object_path: total_percent
  - kind: obj_iter
    object_path: reporting_persons[*].percent_of_class
normalizer:
  type: percent
qa:
  min: 0
  max: 100
```

**正则：要用，但只做“局部锚定”**
正则最适合两件事：

* section/header 锚点，比如 `Item 2.02`, `Use of Proceeds`, `Summary Compensation Table`
* table row label 匹配，比如 `Revenue|Net sales|Sales`

不要让正则在整份文档里“裸跑”。先缩到 section/table/window，再跑正则；否则维护成本会爆炸。

**spaCy：先不要上**
这个问题的主难点不是 NER，而是**结构定位**。EDGAR 的很多关键字段本来就有 XBRL、XML、item 编号、table row、cover page、fee table 这些半结构化锚点。spaCy 更像是后续做文本分类、角色识别、事件归因时的加分项，不适合做第一层主抽取器。

**LLM：要用，但只能做最后一层**
LLM 不负责“在整份 filing 里找值”；LLM 只负责把你**已经精确切出来的 span** 归一化成 JSON。
也就是：

* 数值字段：`doc -> value` 不走 LLM
* 片段字段：`anchored_span -> json schema` 才走 LLM

这样 LLM 成本低、可解释、也不会漂。

---

## 我建议的 6 个 extractor 类

整个系统最多就这 6 类，别再加了：

1. `ObjPathExtractor`
   直接读 `filing.obj()` 暴露出的属性 / DataFrame

2. `XbrlConceptExtractor`
   用 `filing.xbrl()` + facts query，按 concept / statement / period / dimension 取值

3. `XmlPathExtractor`
   只给 XML 表单：3/4/5、13D/G、13F、144

4. `AnchoredTableExtractor`
   先找 section/table，再按 row alias 取值

5. `AnchoredSpanExtractor`
   先切出 item/section/window，再把原文 span 存下来

6. `LlmSpanNormalizer`
   只对 span 做 schema 化输出

只维护这 6 个 extractor 的代码，字段层只写配置，不写业务逻辑。

---

## 按表单家族怎么落地

### 1. 10-K / 10-Q / 20-F / 部分 6-K

定期财报优先走 `filing.obj()` / `filing.xbrl()`。edgartools 的 10-K / 10-Q 对象已经把 `financials`, `risk_factors`, `mda` 这些高价值入口暴露出来；XBRL facts 还支持按 concept、statement type、period、dimension 查询。([EdgarTools][1])

落地顺序建议是：

* 数值：`XBRLConceptExtractor`
* 文本片段：`obj.section` 或 `filing.sections()/search()`
* 只有在 XBRL 缺失或 extension 太怪时，才退到 `AnchoredTableExtractor`

20-F 和一部分 6-K 不要先假设一定有同级 typed object；先试 `filing.xbrl()`，不行再退回通用 `Filing` 的 `search()/sections()/parse()/text()/markdown()`。

### 2. 8-K / 6-K event 类

8-K 已经很适合“精确定位”：`eight_k.items` 给出 item 列表，可以直接用 `eight_k['2.02']` 取 item 正文；如果是业绩类 8-K，edgartools 还能从 EX-99.1 里解析 earnings tables。([EdgarTools][3])

所以 8-K 的主策略不是正则找“earnings”：

* 先用 item 编号定位
* 再看是否有 press release / earnings tables
* 最后对 item 文本做 span 级抽取

6-K 没有 8-K 那么强的 item 标准化时，就退到 `AnchoredSpanExtractor`，但仍然要先限定在 exhibit / press release / cover summary 的局部范围内。

### 3. DEF 14A

这类表单必须拆成两条线：
一条是**高可靠 XBRL**，一条是**中可靠 HTML**。edgartools 文档现在明确写了：proxy 里 executive compensation / pay-vs-performance 主要来自 XBRL，beneficial ownership / proposals / board info 还是 HTML 解析。([EdgarTools][4])

所以别试图用一个 extractor 吃完整份 DEF 14A：

* `exec_total_comp`, `peo_total_comp`, `tsr`, `net_income` 这类：走 XBRL
* `proposal_*`, `beneficial_ownership_*`, `board_*`：走 anchored HTML/table/span
* proposal 的最终分类、治理影响、pay alignment 这种再交给 LLM

### 4. 3 / 4 / 5

Section 16 这类表单本质上就是 XML 表单。edgartools 已经把 Form 4 的交易、market trades、derivative trades、option exercises 做成结构化对象，而且文档特别提醒：很多价格、股数、10b5-1 信息在 footnotes 里，但 edgartools 会自动解析 footnote 引用。([EdgarTools][5])

所以这里的最佳实践是：

* 主值全部走 `ObjPathExtractor`
* footnote 作为补充 evidence 存起来
* 不要对 Form 4 全文跑 regex

### 5. 13D / 13G

edgartools 文档明确写了 `Schedule13D` / `Schedule13G` 是从 XML 解析出来的结构化对象，并且直接暴露了 `total_shares`, `total_percent`, `items.item4_purpose_of_transaction` 等关键字段。([EdgarTools][6])

所以这类表单非常适合：

* 数值：直接读对象
* 片段：直接读 `items.itemX_*`
* LLM：只对 `item4_purpose_of_transaction` 这种已定位 narrative 做 intent / activism schema

### 6. 144

Form 144 也是 XML-first。edgartools 文档已经把 `units_to_be_sold`, `market_value`, `approx_sale_date`, `securities_to_be_sold`, `securities_sold_past_3_months`, `is_10b5_1_plan` 等做成了对象和 DataFrame。([EdgarTools][7])

所以 Form 144 根本不值得上 spaCy。
直接：

* proposed sale：读 `securities_information`
* acquisition history：读 `securities_to_be_sold`
* past 3 months：读 `securities_sold_past_3_months`
* remarks：切 span 给 LLM

### 7. 13F

13F 用 `report.holdings` 做聚合视图，用 `report.infotable` 做逐 manager/security 的原始明细，这个分层非常适合生产抽取。SEC 还会季度更新 official Section 13(f) list，可拿来做 issuer/title/CUSIP 的校验。([EdgarTools][8])

这里有一个必须注意的坑：
edgartools 当前 13F guide 还写着 `Value` / `total_value` 以 thousands 计；但 SEC FAQ 已明确说明，自 2023-01-03 起，13F 的 value total 和 individual security position value 都按 nearest dollar 报。两边口径现在是冲突的。我的建议不是现在站队，而是工程上先保守处理：存 `raw_value`, `normalized_value_usd`, `value_scale_assumed`，拿近年的样本回归验证后再锁死。([EdgarTools][8])

---

## 运行时流程，建议就这么简单

```python
def extract_field(filing, field_spec):
    for locator in field_spec.locators:
        candidate = locator.try_extract(filing, field_spec)
        if not candidate:
            continue
        value = normalize(candidate, field_spec.normalizer)
        if qa_pass(value, field_spec.qa):
            return {
                "value": value,
                "raw": candidate.raw,
                "locator_kind": locator.kind,
                "lineage": candidate.lineage,
                "confidence": candidate.confidence,
            }
    return None
```

`lineage` 至少存这些：

* accession_no
* form_type
* locator_kind
* object_path / xbrl_concept / xpath / section_name / item_no
* source_span
* raw_value
* normalized_value
* confidence

这样以后错了，你能回放，不会变成黑箱。

---

## 这四个边界，能防止系统膨胀

1. **每个字段最多 3 个 locator**
   超过 3 个，通常说明字段定义太宽了，先拆字段。

2. **每个字段 alias 不超过 10 个**
   超过 10 个，应该升级成上游结构化来源，而不是继续堆别名。

3. **LLM 只吃 1～3 KB 的 span**
   不准喂整份 filing。

4. **新增规则必须来自回归集**
   不因为单个怪样本立刻加一个专用正则。

---


