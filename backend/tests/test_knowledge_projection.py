import json
from unittest.mock import Mock

import pytest

from backend.app.ai.extraction_pipeline import KINDS
from backend.app.domains.documents import knowledge
from backend.app.domains.settings import llm
from backend.tests.test_extraction_workflow import book, client, extract, model_reply, summaries


def result(number, kind, **fields):
    chapter = {"id": f"c{number}", "chapter_no": number, "title": f"第{number}章"}
    return chapter, {**{key: [] for key in KINDS}, kind: [{
        "fact_id": f"{kind}-{number}", "name": "林川" if kind == "characters" else "青石",
        "sources": [{"chapter_id": chapter["id"], "chapter_no": number, "chapter_title": chapter["title"],
                     "start": number, "end": number + 2, "quote": f"依据{number}"}], **fields,
    }]}


@pytest.mark.parametrize("kind", ["characters", "items", "world_locations"])
def test_cross_chapter_profiles_merge_missing_identity_and_keep_new_information(kind):
    rows = [result(3, kind, description="后来修复", owner="阿遥", state_changes=["修复"]),
            result(1, kind, description="首次出现", owner="林川", related_characters=["林川"]),
            result(2, kind, description="交给阿遥", owner="阿遥", related_characters=["阿遥"])]
    projected, invalid = knowledge.project(rows, [], [])
    assert not invalid
    assert len(projected[kind]) == 1
    entry = projected[kind][0]
    assert [fact["chapter_no"] for fact in entry["evidence"]] == [1, 2, 3]
    assert entry["owner"] == "阿遥"
    assert entry["related_characters"] == ["林川", "阿遥"]
    assert entry["state_changes"] == ["修复"]
    assert [(change["chapter_no"], change["value"]) for change in entry["field_history"]["owner"]] == [
        (1, "林川"), (2, "阿遥"),
    ]
    assert entry["field_history"]["owner"][1]["fact_ids"] == [f"{kind}-2", f"{kind}-3"]
    assert (entry["first_chapter"], entry["last_chapter"]) == (1, 3)


def test_missing_identity_cannot_bridge_two_conflicting_people():
    projected, _ = knowledge.project([
        result(1, "characters", identity="医师"), result(2, "characters"),
        result(3, "characters", identity="守卫"), result(4, "characters", identity="医师"),
    ], [], [])
    assert len(projected["characters"]) == 2
    assert sorted(sorted(fact["chapter_no"] for fact in entry["evidence"])
                  for entry in projected["characters"]) == [[1, 2, 4], [3]]
    assert all(entry["needs_review"] for entry in projected["characters"])


def test_owner_change_does_not_split_item_and_conflicting_types_remain_reviewable():
    projected, _ = knowledge.project([
        result(1, "items", type="药材", owner="林川"),
        result(2, "items", type="药材", owner="阿遥"),
        result(3, "items", type="兵器"),
    ], [], [])
    assert sorted(len(entry["evidence"]) for entry in projected["items"]) == [1, 2]
    assert all(entry["needs_review"] for entry in projected["items"])


def test_recurring_named_events_stay_separate_and_sort_by_source_position():
    early = result(1, "storyline_events", time="三年前", description="第一次抵达")
    later = result(2, "storyline_events", time="翌日", description="再次抵达")
    same_chapter = result(1, "storyline_events", name="离开")
    same_chapter[1]["storyline_events"][0]["fact_id"] = "later-position"
    same_chapter[1]["storyline_events"][0]["sources"][0]["start"] = 30
    projected, _ = knowledge.project([later, same_chapter, early], [], [])
    events = projected["storyline_events"]
    assert [entry["evidence"][0]["fact_id"] for entry in events] == [
        "storyline_events-1", "later-position", "storyline_events-2",
    ]
    assert not any(entry["needs_review"] for entry in events)
    assert [entry.get("time") for entry in events] == ["三年前", None, "翌日"]


def test_normalized_names_and_synthesis_metadata_survive_reprojection():
    rows = [result(1, "characters", name=" 林川 "), result(2, "characters", name="林川", identity="医师")]
    projected, _ = knowledge.project(rows, [], [])
    entry = projected["characters"][0]
    entry.update(synthesis=[{"text": "档案", "fact_ids": entry["source_ids"]}],
                 synthesis_status="ready", synthesis_version="prompt-version", synthesis_model="model")
    previous = [{"id": entry["entity_id"], "source_ids": json.dumps(entry["source_ids"]),
                 "content": json.dumps(entry)}]
    updated, _ = knowledge.project(rows, previous, [])
    assert len(updated["characters"]) == 1
    assert updated["characters"][0]["entity_id"] == entry["entity_id"]
    assert updated["characters"][0]["synthesis_version"] == "prompt-version"


def test_rebuild_old_results_without_model_calls_preserves_split_and_checks_revision(client, monkeypatch):
    book_id = book(client)
    extract(client, book_id)
    before = summaries(client, book_id)
    person = next(row["content"][0] for row in before["summaries"] if row["type"] == "characters")
    response = client.post(f"/api/v1/books/{book_id}/entity-resolutions", json={
        "revision": before["revision"], "action": "split", "source_ids": person["source_ids"][:1],
    })
    response.raise_for_status()
    data = response.json()
    invoke = Mock(side_effect=AssertionError("rebuild must not call a model"))
    monkeypatch.setattr(llm, "chat", invoke)
    response = client.post(f"/api/v1/books/{book_id}/rebuild-knowledge", params={"revision": data["revision"]})
    response.raise_for_status()
    rebuilt = response.json()
    assert len(next(row["content"] for row in rebuilt["summaries"] if row["type"] == "characters")) == 2
    assert rebuilt["coverage"] == before["coverage"]
    assert rebuilt["revision"] == data["revision"] + 1
    assert client.post(f"/api/v1/books/{book_id}/rebuild-knowledge",
                       params={"revision": data["revision"]}).status_code == 409
    invoke.assert_not_called()


def test_rebuild_rejects_active_task_and_other_owner(client):
    from backend.app.domains.workflow import tasks

    book_id = book(client)
    tasks.create_task(client.app.state.db, book_id, "extract")
    assert client.post(f"/api/v1/books/{book_id}/rebuild-knowledge", params={"revision": 0}).status_code == 409
    assert client.post("/api/v1/books/missing/rebuild-knowledge", params={"revision": 0}).status_code == 404


def test_synthesis_includes_items_world_and_ownership_history(client, monkeypatch):
    def reply(settings, messages, **kwargs):
        prompt = json.loads(messages[1]["content"])
        if isinstance(prompt, list):
            return model_reply(settings, messages)
        payload = json.loads(model_reply(settings, messages))
        part = prompt["segments"][0]
        citation = [{"segment_id": part["segment_id"], "quote": "林川"}]
        payload["items"] = [{"name": "药箱", "owner": "林川" if part["chapter_no"] == 1 else "阿遥",
                             "evidence": citation}]
        payload["world_locations"] = [{"name": "青石镇", "description": "行医地点", "evidence": citation}]
        return json.dumps(payload)

    monkeypatch.setattr(llm, "chat", reply)
    book_id = book(client)
    assert extract(client, book_id)["status"] == "completed"
    data = summaries(client, book_id)
    for kind in ("characters", "items", "world_locations"):
        entries = next(row["content"] for row in data["summaries"] if row["type"] == kind)
        assert len(entries) == 1
        assert entries[0]["synthesis_status"] == "ready"
        assert entries[0]["synthesis"]
        assert len(entries[0]["evidence"]) == 3


def test_long_archive_is_consolidated_after_batched_synthesis(client, monkeypatch):
    calls = []

    def reply(settings, messages, **kwargs):
        prompt = json.loads(messages[1]["content"])
        if isinstance(prompt, list):
            calls.append(prompt)
            return model_reply(settings, messages)
        part = prompt["segments"][0]
        return json.dumps({**{kind: [] for kind in KINDS}, "characters": [{
            "name": "林川", "description": "行医经历" * 100,
            "evidence": [{"segment_id": part["segment_id"], "quote": "林川"}],
        }]})

    monkeypatch.setattr(llm, "chat", reply)
    text = "\n\n".join(f"第{number}章 行医\n林川行医。" for number in range(1, 21))
    book_id = book(client, text)
    assert extract(client, book_id)["status"] == "completed"
    person = next(row["content"][0] for row in summaries(client, book_id)["summaries"] if row["type"] == "characters")
    assert len(person["evidence"]) == 20
    assert len(calls) >= 3
    assert "summary" in calls[-1][0] and "fact_ids" in calls[-1][0]
    assert len(person["synthesis"]) == 1
    assert set(person["synthesis"][0]["fact_ids"]) <= set(person["source_ids"])
