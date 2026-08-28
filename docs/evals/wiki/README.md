# Wiki 质量评估数据集

本目录保存 M4 使用的 Wiki 生成质量评估数据集。数据集采用生活化短文档，目标不是模拟完整业务库，而是构造容易出错、可重复判断的生成质量 case。

## 目录结构

```text
docs/evals/wiki/
  README.md
  cases/
    <case_id>/
      case.yaml
      documents/
        *.md
        *.txt
```

每个 case 必须独立运行，不依赖其他 case 的输入文档或生成结果。后续 eval runner 应以 `case.yaml` 作为唯一入口，读取 `documents` 中列出的文件，创建临时 Source KB / Wiki KB，运行 Wiki ingest，然后执行结构化断言。

## case.yaml 字段

```yaml
id: alias_merge_001
title: 同义实体应合并
purpose: 验证不同叫法指向同一实体时不会生成重复页面
tags:
  - alias
  - dedup

wiki_config:
  auto_ingest: false
  llm_timeout_seconds: 60
  llm_max_retries: 3
  temperature: 0.2

documents:
  - path: documents/example.md
    title: 示例文档

expectations:
  must_have_pages:
    - slug: entity/example
      page_type: entity
      title_contains: 示例
  must_not_have_pages:
    - slug: entity/duplicate-example
  must_have_aliases:
    entity/example:
      - 示例
  must_have_citations:
    entity/example:
      min_count: 1
      required_terms:
        - 示例
  must_have_relations:
    - source_slug: entity/example
      target_slug: concept/example-rule
      relation_type_contains: 相关
  must_not_contain:
    - chunk_
  max_dead_links: 0
  max_self_loops: 0
```

## 断言语义

- `must_have_pages`：生成结果中必须存在指定 slug 与页面类型；`title_contains` 用于允许标题有轻微差异。
- `must_not_have_pages`：生成结果中不得存在这些重复、噪音或无证据页面。
- `must_have_aliases`：指定页面的 aliases 必须包含列出的名称。
- `must_have_citations`：指定页面至少需要引用 `min_count` 个来源；`required_terms` 用于辅助检查引用内容是否覆盖实质证据。
- `must_have_relations`：图谱中必须存在源实体到目标实体的关系；`relation_type_contains` 允许关系名称不同但语义接近。
- `must_not_contain`：任何生成页面正文都不得包含这些内部标记、模板话术或无依据内容。
- `max_dead_links`：Post-process 后允许的最大死链数量，当前所有 case 均为 0。
- `max_self_loops`：图谱允许的最大自链数量，当前所有 case 均为 0。

## 首批覆盖

首批 10 个 case 覆盖同义实体、相似但不同、跨文档关系、冲突事实、编号/参数事实、低价值噪音、引用约束、死链约束、图谱自链、空证据不编造。

这些 case 只定义评估输入和期望，不直接调用真实 LLM。真实 DeepSeek 评估由后续本地 eval runner 执行，不进入 CI 默认路径。
