from app.models import WikiPage
from app.services.wiki.pipeline import (
    WikiCandidate,
    deterministic_dedup_merges,
    merge_candidate_slugs,
    relation_evidence_chunk_id,
)


def candidate(
    *,
    name: str,
    slug: str,
    page_type: str = "entity",
    aliases: list[str] | None = None,
    source_ref: str = "doc-1",
) -> WikiCandidate:
    return WikiCandidate(
        name=name,
        slug=slug,
        page_type=page_type,
        entity_type="other" if page_type == "entity" else "concept",
        aliases=aliases or [name],
        description=f"{name} 的描述。",
        source_refs=[source_ref],
    )


def test_batch_local_dedup_merges_same_object_and_keeps_preferred_slug() -> None:
    candidates = [
        candidate(name="晨光咖啡", slug="entity/chenguang-coffee", aliases=["晨光咖啡"], source_ref="doc-1"),
        candidate(name="晨光咖啡", slug="entity/morning-light-cafe", aliases=["Morning Light Cafe", "晨光"], source_ref="doc-2"),
        candidate(name="CG Coffee", slug="entity/cg-coffee", aliases=["CG Coffee"], source_ref="doc-2"),
    ]

    merged = merge_candidate_slugs(
        candidates=candidates,
        existing_pages=[],
        merges={
            "entity/chenguang-coffee": "entity/morning-light-cafe",
            "entity/cg-coffee": "entity/morning-light-cafe",
        },
    )

    assert [item.slug for item in merged] == ["entity/morning-light-cafe"]
    assert merged[0].source_refs == ["doc-1", "doc-2"]
    assert set(merged[0].aliases) >= {"晨光咖啡", "Morning Light Cafe", "晨光", "CG Coffee"}


def test_dedup_derives_canonical_identifier_slug_for_same_batch_cluster() -> None:
    candidates = [
        candidate(name="G7391次列车", slug="entity/g7391-train"),
        candidate(name="G7391", slug="entity/train-g7391", aliases=["G7391"], source_ref="doc-2"),
    ]

    merged = merge_candidate_slugs(
        candidates=candidates,
        existing_pages=[],
        merges={"entity/g7391-train": "entity/train-g7391"},
    )

    assert [item.slug for item in merged] == ["entity/g7391"]
    assert set(merged[0].aliases) >= {"G7391次列车", "G7391"}


def test_dedup_keeps_related_but_different_candidates_separate() -> None:
    candidates = [
        candidate(name="晨光咖啡馆", slug="entity/morning-light-cafe"),
        candidate(name="晨光烘焙教室", slug="entity/morning-light-baking-class"),
    ]

    assert deterministic_dedup_merges(candidates, []) == {}

    merged = merge_candidate_slugs(
        candidates=candidates,
        existing_pages=[],
        merges={},
    )

    assert {item.slug for item in merged} == {"entity/morning-light-cafe", "entity/morning-light-baking-class"}


def test_dedup_does_not_merge_place_with_larger_place_name_sharing_slug_prefix() -> None:
    candidates = [
        candidate(name="西湖", slug="entity/west-lake"),
        candidate(name="西湖花园酒店", slug="entity/west-lake-garden-hotel"),
    ]

    assert deterministic_dedup_merges(candidates, []) == {}


def test_relation_evidence_ignores_target_name_embedded_in_longer_candidate() -> None:
    trip = candidate(
        name="杭州家庭旅行计划",
        slug="entity/hangzhou-family-trip",
        aliases=["杭州家庭旅行", "杭州家庭旅行计划"],
    )
    west_lake = candidate(name="西湖", slug="entity/west-lake", aliases=["西湖"])
    hotel = candidate(name="西湖花园酒店", slug="entity/xihu-garden-hotel", aliases=["西湖花园酒店"])
    chunks = [
        type(
            "Chunk",
            (),
            {
                "id": "hotel",
                "header_path": ["酒店预订"],
                "content": "杭州家庭旅行的住宿已确认：西湖花园酒店。",
            },
        )(),
        type(
            "Chunk",
            (),
            {
                "id": "itinerary",
                "header_path": ["游玩安排"],
                "content": "杭州家庭旅行计划第一天下午去西湖，第二天上午去浙江自然博物院。",
            },
        )(),
    ]

    assert (
        relation_evidence_chunk_id(
            candidate=trip,
            target=west_lake,
            chunks=chunks,
            blocking_candidates=[west_lake, hotel],
        )
        == "itinerary"
    )


def test_dedup_rejects_cross_type_merge_and_uses_existing_page_target() -> None:
    existing = WikiPage(
        id="page-1",
        kb_id="kb-1",
        slug="entity/morning-run-plan",
        title="晨跑计划",
        page_type="entity",
        summary="晨跑计划是每周三次的训练计划。",
        content="",
        category_path=["实体", "计划"],
        aliases=["晨跑计划"],
        source_refs=["doc-existing"],
    )
    candidates = [
        candidate(name="晨跑计划", slug="entity/entity", aliases=["晨跑计划"], source_ref="doc-1"),
        candidate(name="Morning Run Log Template", slug="concept/concept", page_type="concept", aliases=["晨跑记录模板"], source_ref="doc-2"),
    ]

    merged = merge_candidate_slugs(
        candidates=candidates,
        existing_pages=[existing],
        merges={
            "entity/entity": "entity/morning-run-plan",
            "concept/concept": "entity/morning-run-plan",
        },
    )

    by_slug = {item.slug: item for item in merged}
    assert set(by_slug) == {"entity/morning-run-plan", "concept/morning-run-log-template"}
    assert by_slug["entity/morning-run-plan"].source_refs == ["doc-1", "doc-existing"]
    assert by_slug["entity/morning-run-plan"].name == "晨跑计划"
