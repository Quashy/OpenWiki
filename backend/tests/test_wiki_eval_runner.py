from pathlib import Path

import yaml

from app.models import Entity, Relation, WikiPage
from app.services.wiki.page_service import full_markdown
from app.tools.eval_wiki_quality import WikiEvalCase, evaluate_case, load_cases


def test_load_cases_validates_dataset() -> None:
    cases = load_cases(Path("docs/evals/wiki"))

    assert len(cases) == 10
    assert sum(len(case.documents) for case in cases) == 16
    for case in cases:
        assert case.id == case.root.name
        yaml.safe_load((case.root / "case.yaml").read_text(encoding="utf-8"))


def test_evaluate_case_calculates_deterministic_metrics() -> None:
    case = load_cases(Path("docs/evals/wiki"), ["alias_merge_001"])[0]
    page = WikiPage(
        id="page-1",
        kb_id="kb-1",
        slug="entity/morning-light-cafe",
        title="晨光咖啡",
        page_type="entity",
        summary="晨光咖啡是桂花路 18 号的社区咖啡店。",
        content="CG Coffee 是晨光咖啡的收银系统简称，Morning Light Cafe 是店招英文名。两者是同一家店。",
        category_path=["实体", "place"],
        aliases=["晨光咖啡", "CG Coffee", "晨光", "Morning Light Cafe"],
        source_refs=["doc-1", "doc-2"],
    )

    result = evaluate_case(case, pages=[page], entities=[], relations=[])

    assert result["passed"] is True
    assert result["metrics"]["pass_rate"] == 1.0
    assert result["metrics"]["must_have_page_hit_rate"] == 1.0
    assert result["metrics"]["alias_hit_rate"] == 1.0
    assert result["metrics"]["citation_requirement_pass_rate"] == 1.0
    assert result["metrics"]["required_term_hit_rate"] == 1.0


def test_evaluate_case_reports_forbidden_content_and_self_loop() -> None:
    case = load_cases(Path("docs/evals/wiki"), ["graph_no_self_loop_001"])[0]
    source = Entity(
        id="entity-1",
        kb_id="kb-1",
        slug="entity/morning-run-plan",
        name="晨跑计划",
        entity_type="event",
        description="晨跑计划",
        aliases=["晨跑计划"],
        wiki_page_id="page-1",
    )
    page = WikiPage(
        id="page-1",
        kb_id="kb-1",
        slug="entity/morning-run-plan",
        title="晨跑计划",
        page_type="entity",
        summary="晨跑计划",
        content=full_markdown("晨跑计划", "晨跑计划依赖晨跑计划。"),
        category_path=["实体", "event"],
        aliases=["晨跑计划"],
        source_refs=["doc-1"],
    )
    relation = Relation(
        id="relation-1",
        kb_id="kb-1",
        source_entity_id="entity-1",
        target_entity_id="entity-1",
        relation_type="使用",
    )

    result = evaluate_case(case, pages=[page], entities=[source], relations=[relation])

    assert result["passed"] is False
    assert result["metrics"]["self_loop_count"] == 1
    assert result["metrics"]["forbidden_content_count"] == 1


def test_evaluate_case_matches_expected_page_identity_when_slug_drifts() -> None:
    case = load_cases(Path("docs/evals/wiki"), ["alias_merge_001"])[0]
    page = WikiPage(
        id="page-1",
        kb_id="kb-1",
        slug="entity/ml-cafe",
        title="晨光咖啡",
        page_type="entity",
        summary="晨光咖啡是桂花路 18 号的社区咖啡店。",
        content="CG Coffee 和 Morning Light Cafe 是同一家店。",
        category_path=["实体", "place"],
        aliases=["晨光咖啡", "CG Coffee", "晨光", "Morning Light Cafe"],
        source_refs=["doc-1", "doc-2"],
    )

    result = evaluate_case(case, pages=[page], entities=[], relations=[])

    assert result["passed"] is True
    assert result["metrics"]["must_have_page_hit_rate"] == 1.0
    assert result["metrics"]["slug_policy_violation_count"] == 0


def test_evaluate_case_resolves_relations_through_identity_matched_pages() -> None:
    case = load_cases(Path("docs/evals/wiki"), ["cross_doc_relation_001"])[0]
    trip_page = WikiPage(
        id="page-trip",
        kb_id="kb-1",
        slug="entity/hangzhou-family-trip",
        title="杭州家庭旅行",
        page_type="entity",
        summary="杭州家庭旅行包含西湖花园酒店住宿和 G7391 去程车次。",
        content="杭州家庭旅行住宿为西湖花园酒店，去程车次为 G7391。",
        category_path=["实体", "event"],
        aliases=["杭州家庭旅行", "杭州周末行"],
        source_refs=["doc-1", "doc-2"],
    )
    hotel_page = WikiPage(
        id="page-hotel",
        kb_id="kb-1",
        slug="entity/xihu-huayuan-hotel",
        title="西湖花园酒店",
        page_type="entity",
        summary="西湖花园酒店是杭州家庭旅行的住宿。",
        content="西湖花园酒店是杭州家庭旅行的住宿。",
        category_path=["实体", "place"],
        aliases=["西湖花园酒店"],
        source_refs=["doc-1"],
    )
    train_page = WikiPage(
        id="page-train",
        kb_id="kb-1",
        slug="entity/g7391",
        title="G7391",
        page_type="entity",
        summary="G7391 是杭州家庭旅行的去程车次。",
        content="G7391 是杭州家庭旅行的去程车次。",
        category_path=["实体", "event"],
        aliases=["G7391"],
        source_refs=["doc-2"],
    )
    trip = Entity(
        id="entity-trip",
        kb_id="kb-1",
        slug="entity/hangzhou-family-trip",
        name="杭州家庭旅行",
        entity_type="event",
        description="杭州家庭旅行",
        aliases=["杭州家庭旅行", "杭州周末行"],
        wiki_page_id="page-trip",
    )
    hotel = Entity(
        id="entity-hotel",
        kb_id="kb-1",
        slug="entity/xihu-huayuan-hotel",
        name="西湖花园酒店",
        entity_type="place",
        description="西湖花园酒店",
        aliases=["西湖花园酒店"],
        wiki_page_id="page-hotel",
    )
    train = Entity(
        id="entity-train",
        kb_id="kb-1",
        slug="entity/g7391",
        name="G7391",
        entity_type="event",
        description="G7391",
        aliases=["G7391"],
        wiki_page_id="page-train",
    )
    relations = [
        Relation(
            id="relation-hotel",
            kb_id="kb-1",
            source_entity_id="entity-trip",
            target_entity_id="entity-hotel",
            relation_type="住宿",
        ),
        Relation(
            id="relation-train",
            kb_id="kb-1",
            source_entity_id="entity-trip",
            target_entity_id="entity-train",
            relation_type="交通",
        ),
    ]

    result = evaluate_case(
        case,
        pages=[trip_page, hotel_page, train_page],
        entities=[trip, hotel, train],
        relations=relations,
    )

    assert result["passed"] is True
    assert result["metrics"]["relation_hit_rate"] == 1.0


def test_evaluate_case_reports_identifier_primary_slug_policy_violation() -> None:
    case = WikiEvalCase(
        id="identifier_slug_policy",
        title="编号不应作为事项主 slug",
        purpose="验证高熵编号 slug 单独作为策略问题记录",
        tags=["slug"],
        wiki_config={},
        documents=[{"path": "documents/example.md"}],
        expectations={
            "must_have_pages": [
                {
                    "slug": "entity/parcel-pickup",
                    "page_type": "entity",
                    "title_contains": "快递取件",
                }
            ],
            "must_not_have_pages": [],
            "must_have_aliases": {},
            "must_have_citations": {},
            "must_have_relations": [],
            "must_not_contain": [],
            "max_dead_links": 0,
            "max_self_loops": 0,
        },
        root=Path("."),
    )
    page = WikiPage(
        id="page-1",
        kb_id="kb-1",
        slug="entity/sf-2026-0828-7781",
        title="快递取件记录",
        page_type="entity",
        summary="快递取件记录包含顺丰单号。",
        content="顺丰单号 SF-2026-0828-7781。",
        category_path=["实体", "事项"],
        aliases=["快递取件", "顺丰单号 SF-2026-0828-7781"],
        source_refs=["doc-1"],
    )

    result = evaluate_case(case, pages=[page], entities=[], relations=[])

    assert result["passed"] is False
    assert result["metrics"]["must_have_page_hit_rate"] == 1.0
    assert result["metrics"]["slug_policy_violation_count"] == 1
    assert result["failures"] == [
        "slug policy violation on entity/parcel-pickup: high-entropy identifier used as primary slug: "
        "entity/sf-2026-0828-7781"
    ]
