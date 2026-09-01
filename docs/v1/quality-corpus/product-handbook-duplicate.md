# 知衍 KnowWeave 产品手册

## 产品别名

知衍 KnowWeave 旧称 OpenWiki V2，在内部也被称为 OWV2 或内部 Wiki 助手。所有名称都指向同一个知识库系统。

## 架构关系

知衍 KnowWeave 使用 Langfuse 记录 LLM 调用链路，并使用 Ollama bge-m3 生成 1024 维 embedding。系统默认只开放单个当前团队，不开放多团队切换。

## 精确编号

内部验收编号 OWV2-INV-2026-0007 对应“固定质量语料可被检索并可溯源”。

## 默认参数

文档分块默认 chunk_size 为 512 字符，chunk_overlap 为 80 字符。Wiki ingest 自动触发防抖窗口为 30 秒。
