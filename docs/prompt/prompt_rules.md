# Wiki Prompt 规则梳理

> 来源：2026-08-28 基于本地产品/技术文档、评估集和 M4 质量目标整理。
> 本文件记录 Wiki 生成提示词与配套工程约束，作为 OpenWiki M4 prompt 抽取与质量演进的规则基线。

## 1. Wiki 生成阶段

Wiki 生成可采用 Map-Reduce 结构，核心阶段如下：

1. `Pass 0: Candidate Extraction`
   - 对应候选抽取 prompt。
   - 从整篇文档抽取轻量候选 slug 骨架，输出 entities + concepts JSON。
   - 只抽 `name`、`slug`、`aliases`、`description`、`details`，不在此阶段写完整事实。
   - 下游 Citation 阶段再绑定具体 chunk 证据。

2. `Pass 1..N: Chunk Citation`
   - 对应引用标注 prompt。
   - 将文档 chunks 分批输入。
   - 对每个候选 slug 标注哪些 chunk 在实质讨论它。
   - 输出 `citations` 与 `new_slugs`。
   - 为了 prompt cache，静态规则和候选 slug 放在 chunks 之前，批次之间只改变 chunks 块。

3. `Taxonomy Plan`
   - 对应分类规划 prompt。
   - 对同一批 entities/concepts 统一规划目录路径。
   - 目标是让整个批次落在一个连贯目录树中，避免并发逐页分类各自发明目录。
   - Reduce 只把规划结果应用到还没有分类的页面，避免扰动已有用户调整。

4. `Deduplication`
   - 对应去重判定 prompt。
   - 判断新抽取项是否应合并到已有页面。
   - 核心原则是 `related != same`。
   - 只允许高置信同义、缩写、翻译、拼写差异合并。

5. `Reduce: Page Modify`
   - 对应页面归并 prompt，通常拆成共享规则和页面输入两部分。
   - 按 slug 聚合引用 chunk，增量创建或更新实体/概念页。
   - 模型角色是 compiler，不是 creative writer。
   - 输出首行必须是 `SUMMARY: ...`，后面是干净 Markdown 页面正文。

6. `Source Summary`
   - 对应来源摘要 prompt。
   - 为单篇源文档生成 `summary/<knowledge-id>` 摘要页。
   - 输出首行必须是 `SUMMARY: ...`，正文包含结构化摘要与 `Key Takeaways`。
   - 不把文件名传给模型，避免扫描件、无意义文件名导致幻觉。

7. `Index Intro / Overview`
   - 对应全局综述或索引导言 prompt。
   - 首次创建 index 页时生成标题和 2-3 句介绍。
   - 已有 index 页更新时，只更新 introduction，以反映近期新增或删除的文档。
   - 不生成目录列表或页面链接，这部分由系统追加。

8. `Finalize`
   - 可设置独立 `wiki:finalize` 阶段。
   - Finalize 负责重建索引、清理死链、补交叉链接、目录修剪。
   - 该阶段主要由 SQL 与图算法完成，不调用 LLM。
   - 因此本项目如果做七个 LLM prompt，`Overview` 对应 Index Intro 类 LLM 写作任务，而不是完整 Finalize。

## 2. 通用输出规则

- 所有 prompt 都要求输出语言为配置的 `Language`。
- 需要结构化结果的阶段只输出合法 JSON，不要前言、解释或 Markdown code fence。
- JSON 字符串中禁止直接出现字面换行；需要换行时使用转义 `\n`。
- Markdown 页面类输出必须首行输出 `SUMMARY: {15-40 words one sentence}`。
- `SUMMARY:` 后才输出 Markdown 正文。
- 不要输出额外 preamble。
- 空内容、纯图片占位、没有可抽取文本时必须走空结果或空摘要，不得根据文件名、标题或外部知识猜测主题。
- Markdown 图片 URL 是 opaque token，必须逐字保留，不得改写、缩短、规范化。
- 内部 chunk id 或 chunk handle 不能出现在最终页面正文或 summary 中。

## 3. Slug 规则

- slug 格式为 `<type>/<name>`。
- entity slug 使用 `entity/<lowercase-hyphenated-name>`。
- concept slug 使用 `concept/<lowercase-hyphenated-name>`。
- 非拉丁名称使用罗马化或拼音形式。
- 优先使用输入中已有的稳定英文专名、官方代码或可直译的对象语义；没有稳定英文时再使用拼音或罗马化。
- slug 表达对象本身，不表达来源文件名、临时文档角色、当前状态、一次性修饰词或过细属性。
- 同一对象有多个名称时，slug 选择最稳定、最通用、最能代表对象身份的名称，不随不同文档的标题、别称或语言变化而漂移。
- 具体事项类对象的 slug 应表达“事项类型 + 核心对象”，避免只使用 record、note、template、plan 这类泛词，也避免把编号、日期、数量、颜色、尺寸等属性放进 slug，除非该编号本身是对象的主要名称。
- slug 在单个知识库内唯一，跨知识库可重复。
- 对同一文档重新抽取时，如果旧 slug 对应的实体/概念仍存在，必须复用原 slug。
- 如果旧实体/概念已不在当前文档中，不再输出它。
- 只有真正新增的实体/概念才创建新 slug。
- summary 页 slug 形如 `summary/<knowledge-uuid>`。
- LLM 调用里高熵 slug 可由短 handle 代理，输出后由后端还原，避免模型抄错 UUID。

## 4. Entity / Concept 边界

- Entity 包括人物、组织、产品、地点、技术、事件等具体命名事物。
- Concept 包括主题、方法论、理论、抽象机制、领域概念等。
- 具体命名事物只进入 `entities`。
- 抽象方法、理论、主题只进入 `concepts`。
- 同一项不得同时出现在两个数组里。
- 不抽取泛泛术语、父类别、相关产品、泛化概念作为别名。
- 不把只是顺带提到的名称提升为页面。
- 具体事项、安排、预订、记录、交易、工单、活动实例优先作为 entity；若它们带有编号、时间、地点、参与方或状态，更应作为一个整体对象抽取。
- 模板、清单、表单、记录格式、说明书等文档型产物如果被作为独立对象讨论，可以抽成 entity 或 concept；其中的占位字段、示例填充值、待填写说明不得抽成页面，也不得当作真实事实。
- 明确标注为示例、占位、待填写、可替换、未确认的信息，只能作为“非事实状态”描述，不得提升为真实实体属性。

## 5. Alias 规则

- alias 只能表示完全相同的实体或概念。
- 允许的 alias：
  - 官方简称与全称。
  - 长短名称变体。
  - 翻译名。
  - 领域内可互换使用的同义名。
  - 广为人知的 alternate name。
  - 输入中明确指向同一对象的中文名、英文名、口语称呼、大小写/空格/连字符变体。
  - 能唯一识别该对象的编号、订单号、预约号、取件码、车次号、合同号或工单号。
- 不允许的 alias：
  - 父类别。
  - 子主题。
  - 相关技术。
  - 相关产品。
  - 泛化概念。
  - 实现细节。
  - 仅属于同一领域但不是同一对象的名称。
  - 相关对象、地点、承载活动、参与人、材料、字段名、类别名或模板占位值。

## 6. 抽取粒度规则

抽取粒度可分为 `focused`、`standard`、`exhaustive` 三档。

### focused

- 只抽文档的主要主题。
- 目标是激进剪枝。
- 总量通常控制在 3-7 个 entities + concepts。
- 包含：
  - 文档真正围绕讨论的核心人物、组织、产品、项目、事件或概念。
  - 简历中的本人和命名项目。
  - 公告中的发布组织和被公告的事件或产品。
  - 产品页中的产品与制造方。
- 排除：
  - 仅在技术栈列表中出现的库、框架、数据库。
  - 仅作为实现细节提到的方法论或基础设施词。
  - 背景性地点、学校、组织。
  - 只能写一句话描述的边缘项。
- 不确定时排除，优先保持索引干净。

### standard

- 默认平衡模式。
- 抽取文档主要主题，以及被实质讨论的次要实体/概念。
- “实质讨论”指有独立段落、多条 bullet、专门小节，或至少 2-3 句上下文。
- 包含：
  - 文档主要主题。
  - 得到具体内容块描述的次要实体/概念。
  - 文档解释“如何使用”的命名方法、架构或技术。
- 排除：
  - 只在逗号分隔技术栈中出现、没有进一步解释的项。
  - 一次性提及、括号补充、泛化基础设施名词。
  - 全部贡献只够一句短句的项。
- 边缘项优先排除。

### exhaustive

- 最大召回模式。
- 抽取每个命名实体和可识别概念。
- 包含：
  - 主体与次要主题。
  - 所有具名技术、库、框架、数据库、服务、协议、标准。
  - 有广泛名称的概念和方法论。
- 只排除：
  - 纯泛化词，如 server、function、data。
  - 只出现在 URL path 或引用列表里的项。
- 适合技术 glossary 型知识库。

## 7. Candidate Extraction 规则

- 输入整篇文档内容、previous slugs、语言、抽取粒度、可选自定义 extraction instructions。
- 输出 JSON：`entities` 与 `concepts`。
- 每个 item 包含：
  - `name`：人类可读名称。
  - `slug`：符合类型前缀的稳定 slug。
  - `aliases`：完全同义名称数组。
  - `description`：15-40 words 的 index listing summary，自包含。
  - `details`：1-3 句 fallback 摘要，少于 300 字符。
- 该阶段不要求完整事实归纳，只给下游引用失败时的轻量兜底。
- 文档空或没有实质文本时返回空数组。
- 对图片内容，如果文档包含已提取 OCR/caption，可在 details 中包含相关 Markdown 图片，并保留 URL token。

## 8. Chunk Citation 规则

- 输入候选 slug 列表和当前批次 chunks。
- chunks 使用短 id handle，如 `c000`、`c001`，而不直接暴露真实 UUID。
- 每个 chunk 以 `<c id="..." index="...">...</c>` 包裹。
- 只引用当前 `<chunks>` 中出现的 chunk id。
- 实质讨论标准：chunk 对候选项给出具体事实、属性、步骤、日期、数字、关系或其他有用信息。
- 判断证据时要同时匹配候选项的 name、slug 末尾语义、aliases、编号和唯一标识符；不要只看 canonical name。
- 优先选择包含定义、身份、编号、日期、时间、金额、规格、尺寸、数量、地点、参与方、状态、关系、约束、决策或更新的 chunk。
- 如果候选项的名称、aliases、编号、关键参数、冲突事实或关系来自不同 chunk，应保留多个 chunk 引用。
- passing mention 不可引用。
- 如果候选项在当前批次没有实质讨论，不输出空数组，直接省略该候选项。
- 一个 chunk 可以同时引用给多个候选项，前提是它确实讨论多个候选项。
- 如果 chunk 很长且混合多个主题，仍按其中实质讨论的候选项分别引用。
- 如果 chunk 说明一个模板、清单、表单或记录格式本身的用途和字段，它可以作为该模板/清单/表单/记录的证据；但字段占位值和示例值不能当作真实事实。
- 可发现 `new_slugs`，但只能加入当前批次实质讨论且候选列表中没有的真正新项。
- `new_slugs` 每项必须包含 `type`、`name`、`slug`、`aliases`、`description`、`details`、`source_chunks`。
- 如果没有任何可引用内容，返回 `{"citations": {}, "new_slugs": []}`。
- 后端会把 handle 解析回真实 chunk ID，未知 handle 被丢弃并记录 warning。
- citation 批次按 rune 规模切分，保持文档顺序，长 chunk 单独成批。

## 9. Dedup 规则

- Dedup 输入是新抽取 items，每个 item 内嵌自己的 existing page candidates。
- 每个 item 的 candidates 是唯一可合并目标。
- 不得合并到其他 item 的 candidate。
- 不得发明目标 slug。
- entity 只能合并到 entity，concept 只能合并到 concept。
- 合并必须同时满足：
  - 新 item 与候选页面指向同一现实世界实体或同一具体概念。
  - 匹配属于名称变体，如简称/全称、翻译、轻微拼写差异。
- 不合并：
  - 同类竞品。
  - 不同版本产品。
  - 相关但不同的主题。
  - 上下位概念。
  - 同一领域的不同证件、制度、流程、标准。
  - 名称有少量字符重合但语义不同的项。
- 不确定时不合并。
- 重复页面比错误合并两个不同对象更可接受。
- 输出 JSON：`{"merges": {"entity/new": "entity/existing"}}`。
- 无合并时返回 `{"merges": {}}`。

## 10. Dedup 工程保护规则

- 大知识库不把所有 existing pages 都塞进 Dedup prompt。
- 只保留 entity/concept 页面作为候选。
- 小语料库可绕过预过滤。
- 大语料库使用廉价表面相似度预过滤：
  - slug base 的 kebab tokens。
  - name 与 aliases 的字符 bigram。
  - 取 max-over-surfaces Jaccard 相似度。
  - 每个新 item 只保留 topK 近邻和超过分数下限的候选。
- LLM 合并结果还要经过 deterministic validation：
  - 目标必须属于该 item 自己的候选集合。
  - source/target slug 都必须有合法类型前缀。
  - 类型前缀必须一致。
- 同 normalized display title 的同类型页面走确定性 exact identity 绑定。
- title identity 只去除空白并折叠大小写，保留标点，避免把书名号、章节名等误并。
- 并发批次用 Redis identity claim 收敛同一 identity 的 slug；Lite 模式用 batch-local map。
- 合并 identity 时保留所有 alias、source chunk，description/details 取更丰富的一侧。

## 11. Taxonomy 规则

- 目录分类描述 item “本质是什么”，不是它在某篇文档中的角色。
- 每个 item 必须输出一个 category path，最多 2 级。
- 如果已有目录合适，必须逐字复用已有 label。
- 不得发明同义目录。
- 如果没有已有目录合适，应创建新的宽泛、持久目录。
- 同类 item 使用同一目录、同一深度，避免兄弟项一深一浅。
- 缺少匹配目录不是返回空 path 的理由。
- 只有 item 确实没有持久主题归属时才返回 `[]`，这种情况应很少。
- 顶层目录优先宽泛，第二级只用于多个 item 共享的稳定子域。
- 不得把 `entity` / `concept` 当作目录名。
- 单个 label 内不得包含 slash。
- `<items>` 中每个 slug 必须在输出中出现且只出现一次。
- 输出 JSON：`{"assignments": [{"slug": "...", "path": ["..."]}]}`。

## 12. Taxonomy 工程保护规则

- 同一批次统一规划，而不是每页并发发明分类。
- 目录创建在 Reduce 并发前顺序完成，避免并发创建同一目录。
- 已有页面如果已有分类，Reduce 不覆盖。
- 目录池较小时完整输入给模型。
- 目录池较大时：
  - 一级目录全部保留作为 anchor。
  - 更深目录可用 embedding 相似度选取相关 topK。
  - 没有 embedding 模型或 embedding 失败时回退到 capped feed-all。
- 解析 LLM 输出后执行 category path 清洗。

## 13. Source Summary 规则

- 输入只给文档内容和可用 wiki pages，不给文件名或标题。
- 首行必须是 `SUMMARY: ...`，用于 index listing。
- 摘要正文使用 Markdown。
- 包含关键事实、论点和结论。
- 使用 `##`、`###` 等合理 heading 层级。
- 末尾包含 `## Key Takeaways` bullet 列表。
- 内容长度按文档长度控制，建议在 500-1500 words 范围内弹性收敛。
- wiki-link 只允许使用 available wiki pages 中提供的 slug。
- 提到可用页面的名称或 alias 时，必须写成 `[[slug|display name]]`。
- 不用裸 `[[slug]]`，不用 bold 代替链接。
- 不得发明 slug。
- 图片按上下文放入摘要，并逐字保留 URL token。
- 空内容时输出固定空摘要语义，不猜测主题。

## 14. Reduce / Page Modify 规则

- System prompt 只放共享规则，User prompt 放页面身份、已有正文、新信息、删除文档、剩余来源、合法链接。
- 共享 source context 放在 page metadata 前，以最大化同源多页更新时的 prompt cache 前缀。
- 页面身份规则：页面只讨论 `PageTitle` 对应的准确实体/概念，不写相关、相邻或名称相似但不同的对象。
- 新信息来自已被 citation 阶段判定直接支持该页面的 verbatim source chunks。
- shared source context 只用于校准范围、归因和语气，不是事实证据，不得复制成页面事实。
- 每个新增事实、实体、数字都必须由 new source chunks 直接支持。
- 必须原样保留 chunks 明确给出的关键事实：编号、订单号、预约号、取件码、车次号、日期、时间、金额、尺寸、规格、数量、地点、人员、组织、状态、限制条件、替代方案和更新说明。
- 如果页面对象的 aliases 或唯一标识符出现在 chunks 中，正文应在概述或事实列表中自然保留这些名称或标识符，避免只写抽象描述。
- 不得发明、综合推断或使用未显式出现的信息。
- 模型是 compiler，不是创意写作者：
  - 尽量贴近原文措辞。
  - 只做轻量重排、去重、合并相关句子。
  - 不为风格扩写。
  - 不发明过渡句。
- 不过度结构化：
  - 只有来源或已有页面支持时才引入 heading。
  - 优先单个顶级标题、短段落、扁平事实列表。
- 禁止空泛话术，除非证据 chunk 原文包含。
- 自述性内容要归因，不把简历、产品页、公告、一人称叙述升级成行业事实。
- 保留仍然有效且仍然讨论该页面主题的已有信息。
- 尽量维持既有页面结构和格式风格。
- 如果新 chunks 清楚直接地取代或矛盾于已有内容：
  - 更新正文为更新且有证据的信息。
  - 增加简短 `Contradictions / Updates` 段落说明变化。
- 如果冲突含糊、未解决或没有直接证据：
  - 不覆盖已有正文。
  - 只增加 `Contradictions / Updates` 描述冲突。
- 若新信息实际属于不同但相关对象，必须拒绝添加该部分。
- 对明确标注为示例、占位、待填写、可替换或未确认的内容，只能写明其状态，不能把占位值当成真实人物、地点、金额或结论。
- 当 chunks 明确表达当前页面对象与白名单页面之间的关系时，应输出结构化关系，不要只写在正文中。
- 关系可以由当前页面对象的 name、alias、编号或明确上下文触发；事项与地点、人员/组织、物品/材料、交通/住宿/预约，计划与配套模板/记录，规则与适用对象之间的显式关系应优先结构化。
- 删除文档时：
  - 移除只由 deleted documents 支持、且不在 remaining source documents 或 new information 中出现的事实。
  - 如果删除后页面几乎为空且没有新信息，输出空页面固定结构。
- wiki-link 只保留 valid links 列表中存在的 slug。
- 不得发明 wiki-link slug。
- 不得链接到页面自身。
- 清除坏链、自链和旧的内部 chunk handle。
- 图片只能来自 supplied new information，URL token 必须逐字保留。

## 15. Index Intro / Overview 规则

- 新 index intro：
  - 输入 document summaries。
  - 输出 `# ` 开头标题，反映知识域。
  - 后接 2-3 句说明该 wiki 覆盖什么。
  - 保持简洁，不生成目录列表或页面链接。
- 更新 index intro：
  - 输入现有 introduction、changes、document summaries。
  - 准确反映当前 wiki 状态。
  - 新增文档显著改变范围时提及新主题。
  - 删除文档后移除不再适用的主题描述。
  - 保持原有语气、风格和标题格式。
  - 输出仍是标题行 + 2-3 句介绍。

## 16. Finalize 规则

- Finalize 是 debounced per-KB 收尾任务。
- ingest 批次只记录变更，最终由 `wiki:finalize` 合并处理。
- 同一 KB 的 finalize 使用 TaskID 去重。
- Finalize 处理：
  - index intro rebuild / update。
  - dead-link cleanup。
  - cross-link injection。
  - folder prune。
- 死链清理、交叉链接注入、目录修剪应优先作为确定性系统逻辑，而不是 LLM 输出规则。

## 17. 并发、批处理与恢复规则

- Wiki ingest 由 `wiki:ingest` 任务触发。
- `task_pending_ops` 持久化 per-document op。
- 单批默认最多处理 5 个文档。
- 标准 Redis 模式允许同一 KB 多批并发，通过 row claiming 与 per-slug lock 保证正确性。
- Lite 模式同一 KB 进程内串行。
- 同一 KB 默认最大 in-flight 批次为 4，避免一个 KB 占满 wiki worker pool。
- Map 阶段可并发处理文档。
- Reduce 阶段按 slug 并发，但每个 slug 使用 Redis lock 防止 lost update。
- claimed 但超时未完成的 pending op 可在 stale 后被恢复。
- 失败文档可以重试，超过最大次数进入 dead letter。
- 删除中的 knowledge 通过 tombstone 跳过仍在队列中的 ingest。
- 部分成功可接受；已生成页面保留，失败文档可单独重试。

## 18. LLM 调用规则

- 每次 LLM 调用经统一模板渲染。
- Wiki LLM 默认最多 3 次尝试。
- completion token budget 提高到 32768，避免大 JSON 被默认 8192 token 截断。
- transient 错误重试：
  - HTTP 408、429、5xx、520-524。
  - timeout、connection reset/refused、broken pipe、DNS、I/O timeout、unexpected EOF、TLS handshake、nested deadline exceeded 等传输类错误。
- 父 context 已取消或超时时不再重试。
- 对字节相同的并发 prompt 进行 singleflight 合并。
- 对可复用 Wiki prompt 前缀做 warmup，提升 provider prompt cache 命中。
- LLM-bound 图片 URL 会被替换为低熵 placeholder，模型输出后再还原，未知或损坏 placeholder 会被移除。
- LLM JSON 输出会清理 code fence、trim 空白、转义 JSON 字符串内的控制字符后再解析。

## 19. 页面与图结构规则

- 页面类型包括 `summary`、`entity`、`concept`、`index`、`synthesis`、`comparison`。
- `synthesis` 与 `comparison` 只由 Agent 写页工具创建，不属于 ingest 自动生成主体。
- 页面默认状态为 `published`。
- `SourceRefs` 存源文档引用。
- `ChunkRefs` 存分块级证据引用。
- `InLinks` / `OutLinks` 维护页面图。
- 页面可人工编辑，每次覆盖前保存 revision。
- 当前版本记录 `last_edit_source`：pipeline、agent、user、revert。
- 回滚生成新版本，不回退版本号。
- pipeline 快照有软上限，全部作者快照有硬上限，避免热点页无限增长。

## 20. Agent 与 Wiki 工具规则

- Wiki 是 Agent 的一等工作区。
- Agent 可以读取、搜索、写入、替换、重命名、删除 Wiki 页面。
- Agent 可读取源文档、标记 issue、读取 issue、更新 issue。
- Agent 工具执行受 Wiki Scope 限制，可通过会话和 mention 收窄范围。
- 共享 KB 场景下工具读写仍受租户、RBAC 和 KB access 控制。
- Wiki 问题闭环由 `wiki_page_issues`、lint、auto-fix 与 Wiki Fixer 共同支持。
