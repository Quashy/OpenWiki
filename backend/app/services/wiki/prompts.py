"""Wiki ingest prompt builders for ``wiki_prompt_v0.2``."""

import json
from dataclasses import dataclass
from typing import Any

PROMPT_FAMILY = "wiki_ingest"
PROMPT_VERSION = "wiki_prompt_v0.2"


@dataclass(frozen=True, slots=True)
class WikiPrompt:
    system: str
    user: str
    metadata: dict[str, str]


def build_extract_prompt(
    *,
    document_id: str,
    existing_slugs: list[str],
    chunks: list[dict[str, Any]],
    extraction_granularity: str = "standard",
    custom_instructions: str = "",
) -> WikiPrompt:
    return WikiPrompt(
        system="你是企业 Wiki 的结构化抽取器。只输出合法 JSON，不要输出解释。\n你的任务是从输入 chunks 中抽取应该创建或更新 Wiki 页的实体和概念候选项。",
        user=f"""<stage>extract</stage>

<document_id>
{document_id}
</document_id>

<existing_slugs_json>
{_json(existing_slugs)}
</existing_slugs_json>

<chunks_json>
{_json(chunks)}
</chunks_json>

<custom_instructions>
{custom_instructions}
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

抽取粒度：{extraction_granularity}
- focused：只抽文档核心主题，总量优先控制在 3-7 个。
- standard：抽核心主题，以及有独立段落、多条 bullet、专门小节或至少 2-3 句上下文的次要实体/概念。
- exhaustive：抽所有具名实体和可识别概念，但仍排除纯泛化词和只出现在 URL/引用中的项。

实体/概念边界：
- 具体命名事物进入 entity，例如人、组织、产品、地点、技术、事件、文档、项目、系统。
- 抽象主题、方法、机制、理论、政策、流程进入 concept。
- 同一对象不得同时输出为 entity 和 concept。
- 具体事项、安排、预订、记录、交易、工单、活动实例优先作为 entity。
- 参数、规则、步骤、方法、评价标准、分类体系优先作为 concept。
- 编号、日期、金额、规格、取件码、预约码等通常是事实属性；只有它们本身被独立解释、追踪或管理时才抽成页面。
- 模板占位字段、示例填充值、说明性占位文本不得抽成页面。

Slug 规则：
- 如果 existing_slugs 中已有同一对象的 slug，必须复用原 slug。
- 如果旧 slug 对应对象未在当前 chunks 中出现，不要输出。
- 新对象才创建新 slug。
- 非拉丁名称可用拼音或稳定英文转写。
- slug 表达对象本身，不表达临时文档角色；优先使用稳定通用名称，而不是过细修饰词或一次性状态。
- 同一候选项的 name、slug、page_type 必须互相一致，不要用 entity slug 搭配 concept 语义。

证据规则：
- 只抽 chunks 中被实质讨论的条目。
- 只有一次顺带提及、列表中无解释的技术名、泛泛背景词，不要抽。
- 不要根据文件名、document_id 或外部知识补充条目。

正反例：
- 正例：输入描述一个具体预约事项，并包含预约编号、时间、地点；输出一个预约事项 entity，编号放入 aliases 或 description。
- 反例：只因为出现预约编号，就把编号、时间、地点分别抽成三个互不相关的核心页面。
- 正例：输入解释一套操作规则或判断标准；输出 concept。
- 反例：把规则示例里的占位值、模板字段名或待填写内容抽成 entity。

空内容规则：
- 如果 chunks 为空或没有实质文本，返回 {{"candidates": []}}。

JSON 格式：
- 只输出 JSON。
- 不要 Markdown code fence。
- 不要在字符串中使用字面换行。
</instructions>

<required_json>
{{
  "candidates": [
    {{
      "name": "条目名称",
      "slug": "entity/name 或 concept/name",
      "page_type": "entity 或 concept",
      "entity_type": "person/org/product/place/tech/event/document/project/system/concept/tech/other",
      "aliases": ["别名"],
      "description": "一句话描述"
    }}
  ]
}}
</required_json>""",
        metadata=_metadata("extract"),
    )


def build_citation_prompt(
    *,
    candidates: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> WikiPrompt:
    return WikiPrompt(
        system="你是 Wiki 引用标注器。只输出合法 JSON，不要输出解释；chunk_id 必须来自输入 chunks。",
        user=f"""<stage>citation</stage>

<candidates_json>
{_json(candidates)}
</candidates_json>

<chunks_json>
{_json(chunks)}
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
- 优先选择包含定义、身份、编号、日期、金额、规格、数量、地点、关系或约束的 chunk。
- 如果 candidate 的 aliases、编号或关键参数来自不同 chunk，应保留多个 chunk_id。
- 只含目录、标题、免责声明、模板占位或示例说明的 chunk 通常不是实质证据。

正反例：
- 正例：chunk 同时给出对象名称、时间和关键编号，可作为该对象引用。
- 正例：chunk 说明 A 使用 B 或 A 位于 B，可同时作为 A、B 以及二者关系的证据。
- 反例：chunk 只在列表中顺带出现对象名，没有任何属性或事实，不要引用。
- 反例：chunk 只是模板占位提示或格式说明，不要作为事实引用。

JSON 格式：
- 只输出 JSON。
- 不要 Markdown code fence。
- 不要解释遗漏原因。
</instructions>

<required_json>
{{
  "citations": [
    {{
      "slug": "entity/name",
      "chunk_ids": ["chunk uuid"]
    }}
  ]
}}
</required_json>""",
        metadata=_metadata("citation"),
    )


def build_dedup_prompt(
    *,
    new_candidates: list[dict[str, Any]],
    existing_pages: list[dict[str, Any]],
) -> WikiPrompt:
    return WikiPrompt(
        system="你是严格的 Wiki 去重判定器。只输出合法 JSON，不要输出解释。\n只在高置信确认两个条目是同一实体或同一概念时合并。",
        user=f"""<stage>dedup</stage>

<new_candidates_json>
{_json(new_candidates)}
</new_candidates_json>

<existing_pages_json>
{_json(existing_pages)}
</existing_pages_json>

<instructions>
输出 JSON 对象，根字段只能包含 "merges"。

"merges" 是 map：
- key 是新 candidate 的 slug。
- value 是应合并到的既有页面或同批候选项 slug。

硬约束：
- 只能合并到 existing_pages_json 或 new_candidates_json 中存在的 slug。
- entity 只能合并 entity，concept 只能合并 concept。
- 不得发明 slug。
- 不得因为相关、同领域、同文件、名称部分重合而合并。
- 不得合并场所与其承载的活动、课程、服务或事件。
- 不得合并计划、安排、项目与其配套模板、记录、清单、工具或执行产物。
- 不得合并产品、服务、政策、流程与其版本、套餐、实例、表单或派生材料。
- 不得合并地点、组织、人员与其运营、参与、负责或举办的事项。

允许合并：
- 官方简称与全称。
- 中英文译名。
- 大小写、空格、连字符等轻微写法差异。
- 同一对象的常见别称。
- 同一生活事项或同一编号对象的不同命名，例如车次名与车次编号。

禁止合并：
- 竞品或同类产品。
- 不同版本。
- 上下位概念。
- 同一领域的不同证件、政策、流程、表单、标准。
- 相关但不同的组织、项目、地点、事件、计划、模板或课程。

核心原则：related != same。不确定时不要合并。

正反例：
- 正例：全称、官方简称、译名、大小写差异指向同一对象，可以合并。
- 正例：同一事项被不同文档称为“申请记录”和“申请单”，且属性、时间、主体完全一致，可以合并。
- 反例：某场所举办某活动，场所和活动不能合并。
- 反例：某计划要求填写某记录模板，计划和模板不能合并。
- 反例：某产品存在不同版本、套餐或实例，除非输入明确说明它们是同一对象，否则不能合并。

JSON 格式：
- 只输出 JSON。
- 无合并时返回 merges 为空对象的 JSON。
</instructions>

<required_json>
{{
  "merges": {{
    "entity/new-slug": "entity/existing-slug"
  }}
}}
</required_json>""",
        metadata=_metadata("dedup"),
    )


def build_taxonomy_prompt(
    *,
    candidates: list[dict[str, Any]],
    existing_taxonomy: list[list[str]] | list[str] | None = None,
) -> WikiPrompt:
    return WikiPrompt(
        system="你是 Wiki 分类规划器。只输出合法 JSON；category_path 最多两级，优先复用已有分类标签。",
        user=f"""<stage>taxonomy</stage>

<existing_taxonomy_json>
{_json(existing_taxonomy or [])}
</existing_taxonomy_json>

<candidates_json>
{_json(candidates)}
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
- 一级分类优先描述稳定领域或对象类型，二级分类描述更具体的稳定子类。
- 不要把来源文件名、临时状态、日期、负责人或动作写成分类。
- 具体事项与其配套规则、模板、记录可以同属一个宽泛领域，但二级分类应区分对象本质。

当前 OpenWiki 默认兜底会使用 "未分类"，但模型应尽量给出有意义分类。

正反例：
- 正例：具体预订、行程、工单可归入 ["事项", "安排"] 或已有同义分类。
- 正例：操作规则、参数说明可归入 ["知识", "规则"] 或已有同义分类。
- 反例：不要用 ["来源文档", "第一篇"]、["待处理", "今天"] 这类临时分类。
- 反例：不要为同义分类重复创建 ["安排"] 和 ["计划安排"]。

JSON 格式：
- 只输出 JSON。
- 不要 Markdown code fence。
</instructions>

<required_json>
{{
  "items": [
    {{
      "slug": "entity/name",
      "category_path": ["一级", "二级"]
    }}
  ]
}}
</required_json>""",
        metadata=_metadata("taxonomy"),
    )


def build_source_summary_prompt(
    *,
    document_id: str,
    allowed_links: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> WikiPrompt:
    return WikiPrompt(
        system="你是 Wiki 来源摘要页编写器。首行必须是 SUMMARY: ...，正文用 Markdown；只能使用白名单中的双链。",
        user=f"""<stage>source_summary</stage>

<document_id>
{document_id}
</document_id>

<allowed_links_json>
{_json(allowed_links)}
</allowed_links_json>

<chunks_json>
{_json(chunks)}
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
- 区分正式事实、示例内容和模板占位；模板占位只能说明为占位，不得当成真实事实。
- 如果原文明确表示某信息未知、待确认或不得推断，摘要必须保留这种不确定性。
- 编号、日期、金额、规格、数量、地点、人员等关键字段必须原样保留，不要改写。
- 如果 chunks 为空或没有实质文本，输出：
  SUMMARY: No textual content was extractable from this document.

  本文档没有可用于摘要的实质文本内容。

正反例：
- 正例：原文写明具体时间、地点、编号时，在摘要中原样保留。
- 正例：原文说明某项信息待确认时，写成待确认，不要补全。
- 反例：不要把“填写你的姓名”“待替换地址”等占位文本写成真实人物或地点。
- 反例：不要根据文档标题猜测原文没有出现的背景。

语言：
- 默认使用中文；专有名词保持原文。
</instructions>

只输出 SUMMARY 行和 Markdown 正文，不要输出其他前言。""",
        metadata=_metadata("source_summary"),
    )


def build_reduce_prompt(
    *,
    candidate: dict[str, Any],
    allowed_links: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    existing_page_markdown: str = "",
) -> WikiPrompt:
    return WikiPrompt(
        system="你是 Wiki 页面归并器。只输出合法 JSON；content 字段首行必须是 SUMMARY: ...；relations 与正文分离。\n你是 compiler，不是创意写作者。新增事实必须由输入 chunks 直接支持。",
        user=f"""<stage>reduce</stage>

<candidate_json>
{_json(candidate)}
</candidate_json>

<allowed_links_json>
{_json(allowed_links)}
</allowed_links_json>

<existing_page_markdown>
{existing_page_markdown}
</existing_page_markdown>

<chunks_json>
{_json(chunks)}
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
- 当 chunks 明确表达当前 candidate 与白名单页面之间的关系时，应输出 relation，不要只写在正文中。
- 常见关系触发包括：位于、属于、包含、使用、依赖、负责、参与、举办、入住、乘坐、关联、替代、更新、约束、适用于。
- 关系必须围绕当前 candidate；不要输出两个第三方页面之间的关系。
- 如果关系只来自推断或常识，不要输出。

正反例：
- 正例：原文说明当前事项使用某工具，且工具在 allowed_links_json 中；输出 target_slug 为该工具的 "使用" 关系。
- 正例：原文说明当前安排发生在某地点，且地点在 allowed_links_json 中；输出 "位于" 或 "发生于" 关系。
- 反例：当前页面是计划，不要把配套记录模板的字段写成计划本身的事实。
- 反例：allowed_links_json 没有目标页面时，不要发明 target_slug。

JSON 格式：
- 只输出 JSON。
- content 字符串内部换行使用 \\n。
- 不要 Markdown code fence。
</instructions>

<required_json>
{{
  "content": "SUMMARY: ...\\n\\n# 页面标题\\n\\n## 概述\\n...",
  "relations": [
    {{
      "target_slug": "entity/name",
      "relation_type": "相关"
    }}
  ]
}}
</required_json>""",
        metadata=_metadata("reduce"),
    )


def build_overview_prompt(
    *,
    allowed_links: list[dict[str, Any]],
    page_summaries: list[dict[str, Any]],
) -> WikiPrompt:
    return WikiPrompt(
        system="你是 Wiki 全局综述编写器。首行必须是 SUMMARY: ...，正文用 Markdown；只能使用白名单双链。",
        user=f"""<stage>overview</stage>

<allowed_links_json>
{_json(allowed_links)}
</allowed_links_json>

<page_summaries_json>
{_json(page_summaries)}
</page_summaries_json>

<instructions>
基于 page_summaries_json 生成全局综述页。

输出格式：
- 第一行必须是 `SUMMARY: ...`，一句话概括当前 Wiki 覆盖范围。
- 正文使用 Markdown。
- 说明主要实体、概念、关键关系和资料覆盖范围。
- 不要生成索引目录清单；索引页由系统生成。
- 不要编造 page_summaries_json 中没有的主题。
- 概括应保持在页面摘要共同支持的范围内，不把局部事实扩展成整体结论。
- 如果资料存在冲突、更新或未知项，只能按 page_summaries_json 中已出现的信息说明。

双链规则：
- 只允许使用 allowed_links_json 中的 slug。
- 提到页面条目时使用 `[[slug|name]]`。
- 不要发明 slug。
- 不要输出自链或坏链。

正反例：
- 正例：多个页面共同指向同一事项、参与者、地点或规则时，可以概述资料覆盖了这些关系。
- 正例：只有单页提到的事实，可描述为局部事实，不要上升为全局结论。
- 反例：不要补充 page_summaries_json 中没有的原因、影响、背景或建议。
- 反例：不要把 overview 写成完整索引列表。

语言：
- 默认使用中文；专有名词保持原文。
</instructions>

只输出 SUMMARY 行和 Markdown 正文，不要输出其他前言。""",
        metadata=_metadata("overview"),
    )


def _metadata(stage: str) -> dict[str, str]:
    return {
        "prompt_family": PROMPT_FAMILY,
        "prompt_stage": stage,
        "prompt_version": PROMPT_VERSION,
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)
