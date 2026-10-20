import pytest

from backend.app.ai.extraction_pipeline import KINDS, combine, segments, validate_extraction


def extract_character(**fields):
    chapter = {"id": "c", "book_id": "b", "chapter_no": 1, "title": "起点",
               "content": "  林川说：我会救你。  "}
    part = segments(chapter)[0]
    value = {kind: [] for kind in KINDS}
    value["characters"] = [{"name": " 林川 ", "evidence": [
        {"segment_id": part["segment_id"], "quote": chapter["content"]},
    ], **fields}]
    return value, part


@pytest.mark.parametrize("fields", [
    {"behavior": ["冒险救下阿遥"]}, {"speech": ["我会救你。"]}, {"description": "关键证人"},
])
def test_important_behavior_speech_and_description_survive(fields):
    value, part = extract_character(**fields)
    result = validate_extraction(value, [part])["characters"][0]
    assert result["name"] == "林川"
    assert all(result[key] == content for key, content in fields.items())
    assert result["sources"][0]["quote"] == part["text"]
    assert result["sources"][0]["start"] == 0
    assert result["sources"][0]["end"] == len(part["text"])


def test_blank_fields_do_not_bypass_key_fact_filter():
    value, part = extract_character(summary="  ", aliases=["  "], relationships=[
        {"target_name": " ", "relation": "同伴"},
    ])
    assert validate_extraction(value, [part])["characters"] == []


def test_routine_character_details_are_removed_but_significant_details_survive():
    value, part = extract_character(
        behavior=["点头", "把证据藏进袖中"],
        speech=["你好。", "我不会再相信你。"],
    )
    result = validate_extraction(value, [part])["characters"][0]
    assert result["behavior"] == ["把证据藏进袖中"]
    assert result["speech"] == ["我不会再相信你。"]


def test_routine_events_and_generic_items_are_removed():
    chapter = {
        "id": "c",
        "book_id": "b",
        "chapter_no": 1,
        "title": "起点",
        "content": "林川向掌柜打招呼，随后坐下喝茶。",
    }
    part = segments(chapter)[0]
    value = {kind: [] for kind in KINDS}
    value["items"] = [{
        "name": "茶杯",
        "description": "桌上的茶杯",
        "evidence": [{"segment_id": part["segment_id"], "quote": part["text"]}],
    }]
    value["storyline_events"] = [{
        "name": "打招呼",
        "description": "林川向掌柜打招呼",
        "involved_characters": ["林川", "掌柜"],
        "evidence": [{"segment_id": part["segment_id"], "quote": part["text"]}],
    }]
    result = validate_extraction(value, [part])
    assert result["items"] == []
    assert result["storyline_events"] == []


def test_generic_item_with_plot_significance_survives():
    chapter = {
        "id": "c",
        "book_id": "b",
        "chapter_no": 1,
        "title": "起点",
        "content": "林川把茶杯藏进袖中。",
    }
    part = segments(chapter)[0]
    value = {kind: [] for kind in KINDS}
    value["items"] = [{
        "name": "茶杯",
        "description": "桌上的茶杯",
        "significance": "藏有暗号",
        "evidence": [{"segment_id": part["segment_id"], "quote": part["text"]}],
    }]
    result = validate_extraction(value, [part])
    assert result["items"][0]["significance"] == "藏有暗号"


def test_even_filtered_entries_must_have_valid_citations():
    value, part = extract_character()
    value["characters"][0]["evidence"][0]["quote"] = "没有发生的事"
    with pytest.raises(ValueError, match="精确匹配"):
        validate_extraction(value, [part])


def test_normalization_deduplicates_lists_relationships_and_fact_ids():
    value, part = extract_character(
        behavior=[" 救人 ", "", "救人"],
        relationships=[{"target_name": " 阿遥 ", "relation": " 同伴 "},
                       {"target_name": "阿遥", "relation": "同伴"}],
    )
    first = validate_extraction(value, [part])
    assert first["characters"][0]["behavior"] == ["救人"]
    assert first["characters"][0]["relationships"] == [{"target_name": "阿遥", "relation": "同伴"}]
    clean, _ = extract_character(behavior=["救人"], relationships=[{"target_name": "阿遥", "relation": "同伴"}])
    second = validate_extraction(clean, [part])
    assert first["characters"][0]["fact_id"] == second["characters"][0]["fact_id"]
    assert len(combine([first, second])["characters"]) == 1


def test_duplicate_questions_are_cleaned_before_lookup_and_combination():
    value, part = extract_character(identity="医师")
    question = {"kind": "identity", "query": " 林川 ", "subject": " 林川 "}
    value["questions"] = [question, question]
    payload = validate_extraction(value, [part])
    assert payload["questions"] == [{"kind": "identity", "query": "林川", "subject": "林川"}]
    assert combine([payload, payload])["questions"] == payload["questions"]
    value["questions"] = [{**question, "query": "  "}]
    with pytest.raises(ValueError, match="不能为空"):
        validate_extraction(value, [part])
