# Wiki 质量评估数据集

本目录保存 M4 使用的 Wiki 生成质量评估数据集。数据集采用生活化短文档，目标不是模拟完整业务库，而是构造容易出错、可重复判断的生成质量 case。

## 目录结构

```text
docs/evals/wiki/
  README.md
  cases/                  # Micro Eval
    <case_id>/
      case.yaml
      documents/
        *.md
        *.txt
  scenarios/              # Scenario Eval
    <scenario_id>/
      scenario.yaml
      documents/
        *.md
        *.txt
```

每个 case 或 scenario 必须独立运行，不依赖其他输入包的文档或生成结果。后续 eval runner 应以 `case.yaml` 或 `scenario.yaml` 作为唯一入口，读取 `documents` 中列出的文件，创建临时 Source KB / Wiki KB，运行 Wiki ingest，然后执行结构化断言。

## Micro Eval 与 Scenario Eval

| 类型 | 目录 | 规模 | 目标 |
|---|---|---|---|
| Micro Eval | `cases/` | 每个 case 1-3 个短文档、1-2 个问题 | 快速回归尖锐边界：同义实体、相似但不同、冲突事实、引用约束、死链、自链、空证据不编造 |
| Scenario Eval | `scenarios/` | 每个 scenario 5-10 个文档、5-8 个问题 | 验证更真实复杂度：多文档聚合、多实体关系、变更通知、参数保真和后续 QA 召回稳定性 |

M4 只验证两类数据集字段可解析和结构化断言可执行；M5 QA eval 复用同一批 `questions` 执行问答断言。

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

questions:
  - id: q_example_fact
    question: 示例文档里确认了什么？
    expected_behavior: answer
    expected_answer_contains:
      - 示例
    expected_citation_terms:
      - 示例
    expected_sources:
      min_count: 1
      allowed_types:
        - document
        - wiki_page
    must_not_contain:
      - 无法确认

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

## scenario.yaml 字段

`scenario.yaml` 与 `case.yaml` 使用同一套顶层字段和断言语义，但场景包规模更大，问题固定覆盖事实、参数、跨文档综合、关系、冲突或变更、无答案六类。

```yaml
id: family_trip_001
title: 家庭旅行资料包
purpose: 验证中等规模生活资料下的多文档聚合、关系图谱和后续 QA 召回稳定性
tags:
  - scenario
  - travel
  - cross-document
  - qa

wiki_config:
  auto_ingest: false
  llm_timeout_seconds: 90
  llm_max_retries: 3
  temperature: 0.2

documents:
  - path: documents/hotel-booking.md
    title: 酒店预订
  - path: documents/train-ticket.md
    title: 火车票信息

questions:
  - id: q_trip_summary
    question: 这次旅行的住宿、去程交通和主要行程是什么？
    expected_behavior: answer
    expected_answer_contains: []
    expected_citation_terms: []
    expected_sources:
      min_count: 2
      allowed_types:
        - document
        - wiki_page
    must_not_contain: []

expectations:
  must_have_pages: []
  must_not_have_pages: []
  must_have_aliases: {}
  must_have_citations: {}
  must_have_relations: []
  must_not_contain: []
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

## questions 语义

`questions` 供 M5 QA eval 复用同一批输入文档。M4 只要求字段可解析，不执行问答。

- `id`：case 内唯一的问题 ID。
- `question`：面向最终用户的自然语言问题。
- `expected_behavior`：`answer` 表示应基于知识库回答，`no_answer` 表示应拒绝编造。
- `expected_answer_contains`：答案中应包含的关键短语，不要求整句完全匹配。
- `expected_citation_terms`：引用内容中应命中的关键证据词。
- `expected_sources.min_count`：最少引用数量。
- `expected_sources.allowed_types`：允许的引用来源类型，当前建议使用 `document` 和 `wiki_page`。
- `must_not_contain`：答案中不得出现的内容。

## 首批覆盖

首批 10 个 case 覆盖同义实体、相似但不同、跨文档关系、冲突事实、编号/参数事实、低价值噪音、引用约束、死链约束、图谱自链、空证据不编造。

首批 3 个 scenario 覆盖家庭旅行、小区物业和家庭装修，补足 Micro Eval 覆盖不到的多文档聚合、多实体关系、冲突/变更事实、参数保真和 QA 召回稳定性。

这些 case 和 scenario 只定义评估输入和期望，不直接调用真实 LLM。真实 DeepSeek 评估由后续本地 eval runner 执行，不进入 CI 默认路径。

## 本地评估命令

先只校验数据集结构：

```powershell
$env:PYTHONPATH="backend"; python -m app.tools.eval_wiki_quality --dry-run
```

校验 Scenario Eval 结构：

```powershell
$script = @'
from pathlib import Path
import yaml

root = Path("docs/evals/wiki/scenarios")
scenarios = sorted(path for path in root.iterdir() if path.is_dir())
required = {"id", "title", "purpose", "tags", "wiki_config", "documents", "questions", "expectations"}
expectation_fields = {
    "must_have_pages",
    "must_not_have_pages",
    "must_have_aliases",
    "must_have_citations",
    "must_have_relations",
    "must_not_contain",
    "max_dead_links",
    "max_self_loops",
}
document_count = 0
question_count = 0

for s in scenarios:
    scenario_path = s / "scenario.yaml"
    assert scenario_path.exists(), f"{scenario_path} not found"
    data = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    missing = required - set(data)
    assert not missing, (s, missing)
    assert data["id"] == s.name, s
    assert 5 <= len(data["documents"]) <= 10, s
    assert 5 <= len(data["questions"]) <= 8, s
    missing_expectations = expectation_fields - set(data["expectations"])
    assert not missing_expectations, (s, missing_expectations)
    for item in data["documents"]:
        assert (s / item["path"]).exists(), (s, item["path"])
    document_count += len(data["documents"])
    question_count += len(data["questions"])

print(f"validated {len(scenarios)} scenarios, {document_count} documents, {question_count} questions")
'@
$script | python -
```

运行全部 case，会调用真实 DeepSeek、Ollama embedding 和当前数据库：

```powershell
$env:PYTHONPATH="backend"; python -m app.tools.eval_wiki_quality
```

运行前需确保当前环境能读取 `DEEPSEEK_API_KEY`，并能访问 `DATABASE_URL` 与 `OLLAMA_BASE_URL`。宿主机运行通常需要把数据库和 Ollama 地址配置为宿主机可访问地址；容器内运行则使用 docker compose 注入的服务地址。

宿主机运行时，如果 `.env` 中的 `OLLAMA_BASE_URL` 面向容器网络，可显式指定本机可访问地址和 1024 维 embedding 模型：

```powershell
$env:PYTHONPATH="backend"; python -m app.tools.eval_wiki_quality --run-id "wiki_prompt_v0_1_baseline_20260828" --ollama-base-url "http://localhost:11434" --embedding-model "bge-m3:latest"
```

只运行单个 case，适合调 prompt 时快速复现：

```powershell
$env:PYTHONPATH="backend"; python -m app.tools.eval_wiki_quality --case alias_merge_001
```

评估报告默认写入 `reports/wiki-evals/`，包含同名 JSON 和 Markdown。报告记录 `pass_rate`、`must_have_page_hit_rate`、`forbidden_page_violation_count`、`alias_hit_rate`、`citation_requirement_pass_rate`、`relation_hit_rate`、`dead_link_count`、`self_loop_count`、`forbidden_content_count`、`required_term_hit_rate`、每个 case 的任务信息、trace_id、失败断言和关键页面摘要。

报告还记录 `prompt_family`、`prompt_version`、LLM provider/model、embedding provider/model，方便后续 Dedup 或 prompt 调整后做同口径对比。

## `wiki_prompt_v0.1` Micro Eval 基准

2026-08-28 已用真实 DeepSeek `deepseek-chat`、Ollama `bge-m3:latest` 跑完 10 个 Micro case，run id 为 `wiki_prompt_v0_1_baseline_20260828`。

报告文件：

- `reports/wiki-evals/wiki-eval-wiki_prompt_v0_1_baseline_20260828.json`
- `reports/wiki-evals/wiki-eval-wiki_prompt_v0_1_baseline_20260828.md`

本次 10 个 case 均执行完成并生成 trace_id，无 case execution error。当前基准质量结果如下：

| 指标 | 值 |
|---|---:|
| `pass_rate` | 0.0 |
| `must_have_page_hit_rate` | 0.3333 |
| `forbidden_page_violation_count` | 1 |
| `alias_hit_rate` | 0.4138 |
| `citation_requirement_pass_rate` | 0.3571 |
| `relation_hit_rate` | 0.0 |
| `dead_link_count` | 0 |
| `self_loop_count` | 0 |
| `forbidden_content_count` | 7 |
| `required_term_hit_rate` | 0.1364 |

该结果是首个可比较 prompt 质量基线，不代表 M4 质量门禁通过。后续应先推进 Dedup pass，再用同一批 Micro case 与本基线对比。
