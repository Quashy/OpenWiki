# OpenWiki Wiki Prompt 模板初版

> 版本：`wiki_prompt_v0.1`
> 状态：用于 M4 prompt 抽取与后续 eval 演进的模板契约。
> 依据：`docs/v1/ROADMAP.md` M4、当前 `backend/app/services/wiki/pipeline.py` 输入输出、`docs/prompt/prompt_rules.md`。

## 0. 使用约定

本文件采用占位符模板形式是刻意设计，不是未完成内容。ROADMAP M4 要求将 `llm_extract`、`llm_citation`、`llm_taxonomy`、`llm_source_summary`、`llm_reduce`、`llm_overview` 从 `pipeline.py` 抽到 `backend/app/services/wiki/prompts.py`，并记录 `prompt_family`、`prompt_stage`、`prompt_version`。因此 prompt 文本必须以可渲染模板保存，而不是写死某一次调用的实际文档内容。

占位符风格统一为 `{{name}}`。后续在 Python 中可以用轻量 builder 函数替换，不要求引入模板引擎。模板变量必须由 builder 提供，LLM 不应看到未替换的占位符。

当前 v0.1 优先适配现有 OpenWiki 后端结构：

- `WikiCandidate` 字段：`name`、`slug`、`page_type`、`entity_type`、`aliases`、`description`、`source_refs`。
- `chunk_payload` 字段：`id`、`header_path`、`content`。
- Extract 仍输出当前代码可消费的 `{"candidates": [...]}`，不改成 `entities/concepts` 双数组。
- Citation 仍输出当前代码可消费的 `{"citations": [{"slug": "...", "chunk_ids": [...]}]}`。
- Taxonomy 仍输出当前代码可消费的 `{"items": [{"slug": "...", "category_path": [...]}]}`。
- Reduce 仍输出当前代码可消费的 `{"content": "SUMMARY: ...", "relations": [...]}`。
- Dedup 是 M4 新增阶段的目标模板，当前 `pipeline.py` 还未实现该 pass。

## 1. 全局规则

所有阶段都遵循以下规则：

- 只基于输入内容工作，不使用外部知识补全事实。
- 空内容、纯占位图片、无实质文本时，不得猜测主题。
- 结构化阶段只输出合法 JSON，不输出解释、前言或 Markdown code fence。
- JSON 字符串中不要使用字面换行；需要换行时使用 `\n`。
- Markdown 页面类输出或 JSON 中的 `content` 字段首行必须是 `SUMMARY: ...`。
- 页面正文不得包含内部 chunk id、调试信息、prompt 字段名或未替换占位符。
- 双链只能使用输入白名单中的 slug，格式为 `[[slug|名称]]`。
- 不得生成自链，不得发明 slug，不得保留坏链。
- 如果业务自定义说明与事实性、引用、输出格式冲突，以系统规则为准。

## 2. Prompt 元数据

后续 `prompts.py` 建议为每个模板暴露以下元数据：

```python
PROMPT_FAMILY = "wiki_ingest"
PROMPT_VERSION = "wiki_prompt_v0.1"
```

每次 LLM 调用的 span metadata 建议记录：

```json
{
  "prompt_family": "wiki_ingest",
  "prompt_stage": "extract | dedup | citation | taxonomy | source_summary | reduce | overview",
  "prompt_version": "wiki_prompt_v0.1"
}
```

## 3. Extract

### 输入变量

- `{{document_id}}`
- `{{existing_slugs_json}}`：JSON array，已有 entity/concept slug。
- `{{chunks_json}}`：JSON array，最多使用当前内循环限制内的 chunks。
- `{{extraction_granularity}}`：`focused` / `standard` / `exhaustive`，当前配置没有该字段时用 `standard`。
- `{{custom_instructions}}`：可为空。

### System

```text
你是企业 Wiki 的结构化抽取器。只输出合法 JSON，不要输出解释。
你的任务是从输入 chunks 中抽取应该创建或更新 Wiki 页的实体和概念候选项。
```

### User

```text
<stage>extract</stage>

<document_id>
{{document_id}}
</document_id>

<existing_slugs_json>
{{existing_slugs_json}}
</existing_slugs_json>

<chunks_json>
{{chunks_json}}
</chunks_json>

<custom_instructions>
{{custom_instructions}}
</custom_instructions>

<instructions>
输出 JSON 对象，根字段只能包含 "candidates"。

每个 candidate 必须包含：
- "name": 条目名称，最长 120 字符。
- "slug": 稳定 slug，格式只能是 "entity/..." 或 "concept/..."。
- "page_type": 只能是 "entity" 或 "concept"。
- "entity_type": entity 可用 person/org/product/place/tech/event/document/project/system/other；concept 默认用 concept 或 tech。
- "aliases": 只包含完全同义的别名、简称、全称、译名，不包含相关项、父类、子类或实现细节。
- "description": 一句话自包含描述，说明该条目是什么以及它在文档中的作用。

抽取粒度：{{extraction_granularity}}
- focused：只抽文档核心主题，总量优先控制在 3-7 个。
- standard：抽核心主题，以及有独立段落、多条 bullet、专门小节或至少 2-3 句上下文的次要实体/概念。
- exhaustive：抽所有具名实体和可识别概念，但仍排除纯泛化词和只出现在 URL/引用中的项。

实体/概念边界：
- 具体命名事物进入 entity，例如人、组织、产品、地点、技术、事件、文档、项目、系统。
- 抽象主题、方法、机制、理论、政策、流程进入 concept。
- 同一对象不得同时输出为 entity 和 concept。

Slug 规则：
- 如果 existing_slugs 中已有同一对象的 slug，必须复用原 slug。
- 如果旧 slug 对应对象未在当前 chunks 中出现，不要输出。
- 新对象才创建新 slug。
- 非拉丁名称可用拼音或稳定英文转写。

证据规则：
- 只抽 chunks 中被实质讨论的条目。
- 只有一次顺带提及、列表中无解释的技术名、泛泛背景词，不要抽。
- 不要根据文件名、document_id 或外部知识补充条目。

空内容规则：
- 如果 chunks 为空或没有实质文本，返回 {"candidates": []}。

JSON 格式：
- 只输出 JSON。
- 不要 Markdown code fence。
- 不要在字符串中使用字面换行。
</instructions>

<required_json>
{
  "candidates": [
    {
      "name": "条目名称",
      "slug": "entity/name 或 concept/name",
      "page_type": "entity 或 concept",
      "entity_type": "person/org/product/place/tech/event/document/project/system/concept/tech/other",
      "aliases": ["别名"],
      "description": "一句话描述"
    }
  ]
}
</required_json>
```

## 4. Dedup

### 输入变量

- `{{new_candidates_json}}`：JSON array，Extract 后的新候选项。
- `{{existing_pages_json}}`：JSON array，既有 entity/concept 页面或预过滤候选页。

### System

```text
你是严格的 Wiki 去重判定器。只输出合法 JSON，不要输出解释。
只在高置信确认两个条目是同一实体或同一概念时合并。
```

### User

```text
<stage>dedup</stage>

<new_candidates_json>
{{new_candidates_json}}
</new_candidates_json>

<existing_pages_json>
{{existing_pages_json}}
</existing_pages_json>

<instructions>
输出 JSON 对象，根字段只能包含 "merges"。

"merges" 是 map：
- key 是新 candidate 的 slug。
- value 是应合并到的既有页面 slug。

硬约束：
- 只能合并到 existing_pages_json 中存在的 slug。
- entity 只能合并 entity，concept 只能合并 concept。
- 不得发明 slug。
- 不得因为相关、同领域、同文件、名称部分重合而合并。

允许合并：
- 官方简称与全称。
- 中英文译名。
- 大小写、空格、连字符等轻微写法差异。
- 同一对象的常见别称。

禁止合并：
- 竞品或同类产品。
- 不同版本。
- 上下位概念。
- 同一领域的不同证件、政策、流程、表单、标准。
- 相关但不同的组织、项目、地点或事件。

核心原则：related != same。不确定时不要合并。

JSON 格式：
- 只输出 JSON。
- 无合并时返回 {"merges": {}}。
</instructions>

<required_json>
{
  "merges": {
    "entity/new-slug": "entity/existing-slug"
  }
}
</required_json>
```

## 5. Citation

### 输入变量

- `{{candidates_json}}`
- `{{chunks_json}}`

### System

```text
你是 Wiki 引用标注器。只输出合法 JSON，不要输出解释；chunk_id 必须来自输入 chunks。
```

### User

```text
<stage>citation</stage>

<candidates_json>
{{candidates_json}}
</candidates_json>

<chunks_json>
{{chunks_json}}
</chunks_json>

<instructions>
输出 JSON 对象，根字段只能包含 "citations"。

对每个候选条目，选择实质讨论该条目的 chunk_id。

实质讨论指 chunk 给出了该条目的具体事实、属性、步骤、数字、日期、关系、约束、决策或定义。

规则：
- chunk_id 必须逐字来自 chunks_json 的 id。
- 只顺带提到名称的 chunk 不要引用。
- 一个 chunk 可以引用给多个 candidate，前提是它确实讨论多个条目。
- 如果某 candidate 没有实质证据，不要输出它。
- 不要为凑引用选择泛泛背景 chunk。
- 不要输出 chunks_json 之外的 id。

JSON 格式：
- 只输出 JSON。
- 不要 Markdown code fence。
- 不要解释遗漏原因。
</instructions>

<required_json>
{
  "citations": [
    {
      "slug": "entity/name",
      "chunk_ids": ["chunk uuid"]
    }
  ]
}
</required_json>
```

## 6. Taxonomy

### 输入变量

- `{{candidates_json}}`
- `{{existing_taxonomy_json}}`：当前可为空；后续接入已有目录后提供。

### System

```text
你是 Wiki 分类规划器。只输出合法 JSON；category_path 最多两级，优先复用已有分类标签。
```

### User

```text
<stage>taxonomy</stage>

<existing_taxonomy_json>
{{existing_taxonomy_json}}
</existing_taxonomy_json>

<candidates_json>
{{candidates_json}}
</candidates_json>

<instructions>
输出 JSON 对象，根字段只能包含 "items"。

为每个 candidate 分配 category_path，最多两级。

分类原则：
- 分类描述条目本质是什么，不描述它在某篇文档中的临时角色。
- 如果 existing_taxonomy_json 中已有合适分类，逐字复用。
- 不要发明同义分类。
- 如果没有合适分类，创建宽泛、稳定的分类。
- 同类条目应归入同一分类、同一深度。
- 不要使用 "entity"、"concept" 作为分类名。
- 单个分类标签中不要包含 "/"。
- 每个 candidate slug 必须出现一次。
- 分类名称使用中文，除非输入主要是英文专有领域并且英文分类更稳定。

当前 OpenWiki 默认兜底会使用 "未分类"，但模型应尽量给出有意义分类。

JSON 格式：
- 只输出 JSON。
- 不要 Markdown code fence。
</instructions>

<required_json>
{
  "items": [
    {
      "slug": "entity/name",
      "category_path": ["一级", "二级"]
    }
  ]
}
</required_json>
```

## 7. Source Summary

### 输入变量

- `{{document_id}}`
- `{{allowed_links_json}}`
- `{{chunks_json}}`

### System

```text
你是 Wiki 来源摘要页编写器。首行必须是 SUMMARY: ...，正文用 Markdown；只能使用白名单中的双链。
```

### User

```text
<stage>source_summary</stage>

<document_id>
{{document_id}}
</document_id>

<allowed_links_json>
{{allowed_links_json}}
</allowed_links_json>

<chunks_json>
{{chunks_json}}
</chunks_json>

<instructions>
基于 chunks_json 为当前源文档生成来源摘要页。

输出格式：
- 第一行必须是 `SUMMARY: ...`，一句话概括该文档内容。
- 第二行开始输出 Markdown 正文。
- 正文应包含关键事实、数字、日期、决策、约束、流程和结论。
- 使用清晰标题结构，优先使用 `##`。
- 末尾包含 `## Key Takeaways`。

双链规则：
- 只允许使用 allowed_links_json 中的 slug。
- 提到白名单条目的 name 或 aliases 时，写成 `[[slug|name]]`。
- 不要发明 slug。
- 不要使用裸 `[[slug]]`。

事实规则：
- 只基于 chunks_json。
- 不要使用文件名、document_id 或外部知识猜测主题。
- 如果 chunks 为空或没有实质文本，输出：
  SUMMARY: No textual content was extractable from this document.

  本文档没有可用于摘要的实质文本内容。

语言：
- 默认使用中文；专有名词保持原文。
</instructions>

只输出 SUMMARY 行和 Markdown 正文，不要输出其他前言。
```

## 8. Reduce

### 输入变量

- `{{candidate_json}}`
- `{{allowed_links_json}}`
- `{{chunks_json}}`
- `{{existing_page_markdown}}`：当前 `pipeline.py` 尚未传入；后续增量归并时应补齐。v0.1 可传空字符串。

### System

```text
你是 Wiki 页面归并器。只输出合法 JSON；content 字段首行必须是 SUMMARY: ...；relations 与正文分离。
你是 compiler，不是创意写作者。新增事实必须由输入 chunks 直接支持。
```

### User

```text
<stage>reduce</stage>

<candidate_json>
{{candidate_json}}
</candidate_json>

<allowed_links_json>
{{allowed_links_json}}
</allowed_links_json>

<existing_page_markdown>
{{existing_page_markdown}}
</existing_page_markdown>

<chunks_json>
{{chunks_json}}
</chunks_json>

<instructions>
输出 JSON 对象，根字段只能包含 "content" 和 "relations"。

content：
- 必须是完整 Markdown 页面。
- 第一行必须是 `SUMMARY: ...`，一句话描述该页面主题。
- 正文必须直接围绕 candidate_json 中的 name/slug/page_type。
- 如果 chunks 中的信息属于相似但不同的对象，拒绝写入。
- 不要输出 chunk_id、内部标记、prompt 字段名或未替换占位符。
- 保留仍有效且仍围绕当前主题的 existing_page_markdown 内容。
- 新增事实、数字、日期、关系、约束必须来自 chunks_json。
- 不得扩写、推断、泛化、升格自述性材料。
- 不要写空泛话术，除非原文明确出现。
- 结构不要过度复杂；优先短段落和扁平列表。
- 如果新信息与已有内容明确冲突，正文采用新证据，并增加 `## 冲突与更新` 小节说明。
- 如果冲突不明确，不覆盖旧内容，只在 `## 冲突与更新` 说明待确认。

双链：
- 只允许使用 allowed_links_json 中的 slug。
- 不得链接到 candidate_json 自己的 slug。
- 不得发明 slug。
- 删除坏链、自链。

relations：
- 从 chunks_json 中抽取与当前 candidate 直接相关的关系。
- target_slug 必须来自 allowed_links_json，且不能等于 candidate slug。
- relation_type 使用简短中文动词或关系短语，如 "属于"、"依赖"、"负责"、"使用"、"包含"、"替代"、"位于"、"相关"。
- 不要输出自环关系。
- 没有明确关系时返回空数组。

JSON 格式：
- 只输出 JSON。
- content 字符串内部换行使用 \n。
- 不要 Markdown code fence。
</instructions>

<required_json>
{
  "content": "SUMMARY: ...\n\n# 页面标题\n\n## 概述\n...",
  "relations": [
    {
      "target_slug": "entity/name",
      "relation_type": "相关"
    }
  ]
}
</required_json>
```

## 9. Overview

### 输入变量

- `{{allowed_links_json}}`
- `{{page_summaries_json}}`

### System

```text
你是 Wiki 全局综述编写器。首行必须是 SUMMARY: ...，正文用 Markdown；只能使用白名单双链。
```

### User

```text
<stage>overview</stage>

<allowed_links_json>
{{allowed_links_json}}
</allowed_links_json>

<page_summaries_json>
{{page_summaries_json}}
</page_summaries_json>

<instructions>
基于 page_summaries_json 生成全局综述页。

输出格式：
- 第一行必须是 `SUMMARY: ...`，一句话概括当前 Wiki 覆盖范围。
- 正文使用 Markdown。
- 说明主要实体、概念、关键关系和资料覆盖范围。
- 不要生成索引目录清单；索引页由系统生成。
- 不要编造 page_summaries_json 中没有的主题。

双链规则：
- 只允许使用 allowed_links_json 中的 slug。
- 提到页面条目时使用 `[[slug|name]]`。
- 不要发明 slug。
- 不要输出自链或坏链。

语言：
- 默认使用中文；专有名词保持原文。
</instructions>

只输出 SUMMARY 行和 Markdown 正文，不要输出其他前言。
```

## 10. 后续落地顺序

1. 先把现有 `pipeline.py` 内联 prompt 行为等价迁移到 `backend/app/services/wiki/prompts.py`。
2. 为每个 builder 返回 `system`、`user`、`metadata`。
3. 增加 prompt 结构测试：阶段名、版本号、输出 schema、关键硬约束。
4. 再引入 Dedup pass；Dedup 当前只是目标模板，不应在没有 runner 与 case 覆盖前直接接主链路。
5. 基于 Micro Eval 失败项优先强化 Citation 与 Reduce，再调 Extract、Taxonomy、Source Summary、Overview。
