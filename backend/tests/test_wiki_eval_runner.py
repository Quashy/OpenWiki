from pathlib import Path

import yaml

from app.models import Entity, Relation, WikiPage
from app.services.wiki.page_service import full_markdown
from app.tools.eval_wiki_quality import evaluate_case, load_cases


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
