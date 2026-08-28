Scenario Eval 生成计划
目标：在 docs/evals/wiki/scenarios/ 下新增 3 个中等生活场景包，用来补足 Micro Eval 覆盖不到的真实复杂度：多文档聚合、多实体关系、冲突事实、参数保真、QA 召回稳定性。
目录结构
docs/evals/wiki/
  cases/                 # Micro Eval，已存在
  scenarios/             # Scenario Eval，新建
    family_trip_001/
      scenario.yaml
      documents/
        hotel-booking.md
        train-ticket.md
        itinerary.md
        budget.md
        change-notice.md
        packing-note.md

    community_property_001/
      scenario.yaml
      documents/
        repair-notice.md
        access-control.md
        activity-plan.md
        complaint-log.md
        fee-notice.md
        contact-list.md

    home_renovation_001/
      scenario.yaml
      documents/
        purchase-list.md
        construction-schedule.md
        material-specs.md
        budget-change.md
        acceptance-record.md
        after-sale-note.md
首批 3 个 Scenario
scenario	场景	重点验证
family_trip_001	家庭旅行资料包	酒店、车票、行程、预算、变更通知、未确认事项
community_property_001	小区物业资料包	维修、门禁、活动、投诉、费用、联系人
home_renovation_001	家庭装修资料包	材料、施工、预算、验收、售后、责任人


每个 Scenario 规模
- 6 个输入文档
- 每篇约 150-500 字
- 6 个 questions
- 结构化 expectations
- max_dead_links: 0
- max_self_loops: 0
scenario.yaml 字段
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
问题设计规则
每个 scenario 固定 6 个问题：
1. 事实题：查时间、地点、编号、负责人。
2. 事实题：查规格、预算、数量或限制。
3. 跨文档综合题：需要至少 2 个文档才能答完整。
4. 关系题：验证图谱/实体关系是否能辅助回答。
5. 冲突或变更题：要求区分旧计划和新通知。
6. 无答案题：文档没有的信息必须拒答，不能编造。
实施步骤
1. 更新 docs/evals/wiki/README.md，补充 scenarios/ 目录、scenario.yaml 字段和 Scenario/Micro 区别。
2. 新建 docs/evals/wiki/scenarios/family_trip_001/，先作为样板。
3. 新建 community_property_001/ 和 home_renovation_001/。
4. 每个 scenario 写 6 个短文档、6 个 questions 和 expectations。
5. 跑静态校验：YAML 可解析、文档路径存在、每个 scenario 有 5-10 文档和 5-8 questions。
6. 不跑后端 pytest；本轮仍是文档型数据集。
验收标准
validated 3 scenarios, 18 documents, 18 questions
并满足：
- 每个 scenario 可独立运行。
- 每个 scenario 覆盖多文档聚合。
- 每个 scenario 至少有 1 个无答案问题。
- 每个 scenario 至少有 1 个跨文档综合问题。
- 所有 scenario 的 expectations 都包含页面、引用、关系、禁止内容、死链和自链约束。