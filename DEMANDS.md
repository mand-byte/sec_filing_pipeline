## 一、任务总目标

请构建一个 precision-first 的 SEC filing backend。
## 要求
系统必须支持 cold-start 与 incremental ingestion。使用edgartools来作为下载工具。
## 抽取对象的数据来源
数据源来为clickhouse，data_quant.us_stock_universe
其结构为
CREATE TABLE IF NOT EXISTS us_stock_universe
        (
            ticker String,
            composite_figi FixedString(12),
            name                 String,
            cik                  FixedString(10),
            active               UInt8 DEFAULT 0,
            base_currency_name   Nullable(String),
            base_currency_symbol Nullable(FixedString(3)),
            currency_name        Nullable(String),
            currency_symbol      Nullable(FixedString(3)),
            delisted_utc         Nullable(DateTime64(3, 'UTC')),
            last_updated_utc     DateTime64(3, 'UTC'),
            locale               LowCardinality(String),
            market               LowCardinality(String),
            primary_exchange     Nullable(String),
            share_class_figi     Nullable(FixedString(12)),
            type                 Nullable(String),
            update_time DateTime64(3, 'UTC') DEFAULT now64(3)
        ) ENGINE = ReplacingMergeTree(update_time)
        ORDER BY (composite_figi)
上表的数据只有CS和ADR,已排除goog,googl这种多个ticker对应一个figi的情况。figi和cik是一一对应的。对于active=0的个股，sec文档提交时间小于等于delisted_utc，之后的提交时间的文件不用处理。        
本项目不要求一定要使用clickhouse,也可以考虑使用postgresql等关系数据库。
本项目唯一要求是对于量化需要的数据都抓取，并且要保证其真实准确度和最少人工修正。
文件解析过程的日志入库，用于分析解析成功与失败，以及失败的原因。

## 程序入口规划
  配置文件在.env，包含clickhouse，psql的连接信息,以及数据抓取起始时间
  使用同步调度器，每次启动或定时执行3个入口，分别是isser,owner,holding的下载和解析。
  每次调度器执行，都会从us_stock_universe表中获取数据要下载的ticker集合，数据库是唯一的程序的状态存储，程序本身运行无状态。（使用接受文件的时间作为进步）

## 规划
  一期规划，设计数据库，覆盖所有字段和文本片段。
  二期规划，EXTRACTOR_CORRECTNESS.md中的Tier 1 （数值类型全覆盖）。
  三期规划，EXTRACTOR_CORRECTNESS.md中的Tier 2 （正则 ，收口， golden set）
  四期规划，EXTRACTOR_CORRECTNESS.md中的Tier 3 (文字类型全覆盖，正则，收口，golden set ,及审核机制)
  五期规划，所有数据达到最高准确率后，再实现llm的输出。LLM的输出不做审核（在无法保证得到最大化准确率下使用llm输出只是浪费钱,文字截取范围影响评分）。当 tier 3做出人工审核修正后，LLM也会重新读取并输出数据。
## （提取特征时）数据读取读取顺序
  按照时间线，从远到近，按数据深度，从深到浅读（有人工修正读人工修正，没有的读原始值）。/A的数据因为提交时间不同，当作新的一份数据，有值的会在特征提取的逻辑里重新计算，没有值的则不处理。
## 人工审核
  人工审核页面要展示原文和抽取结果，方便比对。否则人工审核的效率会很低。

## 需要抽取的文件类型和字段
  参考EXTRACTION_FILED.md

## 抽取方法
  参考EXTRACTION_METHOD.md
## 如何提高正确率
  参考EXTRACTOR_CORRECTNESS.md