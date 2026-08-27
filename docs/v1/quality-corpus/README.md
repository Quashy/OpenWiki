# M0 固定质量语料

本目录保存 v1 后续里程碑共用的最小验收语料。M0 只要求语料存在并可被人工或测试读取；M2-M6 再把它接入分块、检索、Wiki ingest 和问答验收。

## 文件

| 文件 | 用途 |
|---|---|
| `product-handbook.md` | Markdown Header-aware 分块、别名、跨文档关系、精确编号。 |
| `product-handbook-duplicate.md` | 与 `product-handbook.md` 内容完全相同，用于同一 KB SHA-256 去重。 |
| `operations-notes.txt` | TXT 递归分块、别名、跨文档关系。 |
| `conflict-facts.md` | 冲突事实与来源溯源。 |
| `questions.md` | 固定问题集合，覆盖可回答与无答案场景。 |

## 验收关注点

- 重复文档：`product-handbook.md` 与 `product-handbook-duplicate.md` 在同一 KB 上传应返回 `409 document_duplicate`。
- 别名：`OpenWiki V2`、`OWV2`、`内部 Wiki 助手` 应能归并到同一产品实体。
- 冲突事实：不同来源给出的默认超时时间冲突时，回答和 Wiki 页面必须保留来源差异。
- 跨文档关系：`OpenWiki V2` 使用 `Langfuse` 做观测，使用 `Ollama bge-m3` 做 embedding。
- 精确编号：问题涉及 `OWV2-INV-2026-0007` 时应召回精确编号所在 chunk。
- 无答案问题：语料没有 SLA 赔付条款，问答应明确无法从知识库确认。
