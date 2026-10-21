import json

from backend.app.domains.knowledge.presentation import character_milestones
from backend.app.domains.knowledge.service import KnowledgeService
from backend.tests.test_character_card import book_with_character


def test_milestones_keep_actual_chapters_deduplicate_and_ignore_minor_facts():
    content = {"evidence": [
        {"chapter_id": "c1", "chapter_no": 1, "identity": "医师", "speech": ["你好"]},
        {"chapter_id": "c8", "chapter_no": 8, "key_events": ["拜师。"]},
        {"chapter_id": "c3", "chapter_no": 3, "key_events": ["拜师", "晋升"],
         "sources": [{"chapter_id": "c3", "chapter_no": 3, "chapter_title": "第三章"}]},
    ]}
    result = character_milestones(content)
    assert len(result) == 2
    assert [chapter["chapter_no"] for chapter in result[0]["chapters"]] == [3, 8]
    assert all(chapter["chapter_no"] != 1 for event in result for chapter in event["chapters"])


def test_legacy_history_is_used_without_assigning_overall_first_chapter():
    result = character_milestones({"chapter_no": 1, "field_history": {
        "key_events": [{"value": ["获救"], "chapter_no": 4, "chapter_id": "c4"}],
    }})
    assert result[0]["chapters"][0]["chapter_no"] == 4
    assert character_milestones({"chapter_no": 1, "key_events": ["加入学院"]}) == [
        {"text": "加入学院", "chapters": []},
    ]
    assert character_milestones({}) == []


def test_character_api_includes_compact_milestones_and_keeps_synthesis(tmp_path):
    database, book_db = book_with_character(tmp_path)
    service = KnowledgeService(database)
    content = {
        "evidence": [{"key_events": ["受伤后入城求医"], "chapter_id": "chapter_1", "chapter_no": 1}],
        "synthesis": [{"text": "人物介绍", "fact_ids": ["fact1"]}],
    }
    book_db.execute(
        "UPDATE knowledge_entities SET content=? WHERE id=?",
        (json.dumps(content), "entity_1"),
    )
    character = service.characters("user_1", "book_1")[0]
    assert character["milestones"][0]["text"] == "受伤后入城求医"
    assert character["milestones"][0]["chapters"][0]["chapter_id"] == "chapter_1"
    assert character["synthesis"] == content["synthesis"]
