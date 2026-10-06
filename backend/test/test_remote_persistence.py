import json

from backend import remote_persistence


class FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def test_persist_summary_rows_uploads_character_details_and_rewrites_index(monkeypatch, tmp_path):
    character_path = tmp_path / "summary" / "characters" / "character_json" / "石野.json"
    index_path = tmp_path / "summary" / "characters" / "all_characters.json"
    character_path.parent.mkdir(parents=True, exist_ok=True)
    character_path.write_text(
        json.dumps({"name": "石野", "summary": "主角"}, ensure_ascii=False),
        encoding="utf-8",
    )
    index_path.write_text(
        json.dumps(
            [
                {
                    "name": "石野",
                    "summary": "主角",
                    "summary_local_url": character_path.as_posix(),
                    "summary_oss_url": "",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    fake_conn = FakeConnection()
    uploaded = []

    monkeypatch.setattr(remote_persistence, "_resolve_db_url", lambda db_url=None: "postgresql://test")
    monkeypatch.setattr(remote_persistence, "_connect_with_fallback", lambda db_url: fake_conn)

    def fake_upload(local_file_path, object_key):
        uploaded.append((str(local_file_path), object_key))
        return f"https://oss.example/{object_key}"

    monkeypatch.setattr(remote_persistence, "_upload_file_to_oss", fake_upload)

    result = remote_persistence.persist_summary_rows(
        summary_rows=[
            {
                "dimension": "characters",
                "content_url": index_path.as_posix(),
                "content_kind": "json",
            }
        ],
        user_id="u_test",
        book_id="b_test",
        source_file_id="sf_test",
    )

    rewritten_index = json.loads(index_path.read_text(encoding="utf-8"))
    assert rewritten_index[0]["summary_oss_url"].endswith(
        "/charpick/u_test/b_test/sf_test/summary/characters/character_json/石野.json"
    )
    assert result["uploaded_summary_count"] == 1
    assert [row["type"] for row in result["uploaded_summary_rows"]] == ["characters_detail", "characters"]
    assert len(uploaded) == 2
    assert uploaded[0][1].endswith("/character_json/石野.json")
    assert uploaded[1][1].endswith("/all_characters.json")
