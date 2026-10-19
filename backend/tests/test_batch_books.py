import tempfile
from pathlib import Path

try:
    import eval_type_backport  # noqa: F401
except ImportError:
    import typing

    typing.Union = typing.Union
    typing.Optional = typing.Optional

try:
    from fastapi.testclient import TestClient
    from backend.app.application import create_app
    from backend.app.core.config import Config
except TypeError as error:
    raise RuntimeError("Run backend tests with Python >= 3.10 as required by pyproject.toml") from error


def make_app():
    data = Path(tempfile.mkdtemp(prefix="personaweaver-test-"))
    config = Config(
        data_dir=data,
        database_path=data / "test.sqlite3",
        max_upload_bytes=1024,
        max_batch_files=3,
        max_batch_upload_bytes=1800,
    )
    return create_app(config), data


def upload_file(name, content="hello"):
    return ("files", (name, content.encode(), "application/octet-stream"))


def test_batch_upload_creates_books_without_tasks():
    app, data = make_app()
    with TestClient(app) as client:
        response = client.post("/api/v1/books/batch", files=[
            upload_file("novel one.txt", "story"),
            upload_file("novel-two.md", "story"),
        ])
        assert response.status_code == 200
        body = response.json()
        assert body["succeeded"] == 2
        assert body["failed"] == 0
        assert all(item["book"]["title"] for item in body["items"])
        assert client.get("/api/v1/tasks").json()["tasks"] == []


def test_batch_upload_reports_invalid_files_individually():
    app, data = make_app()
    with TestClient(app) as client:
        response = client.post("/api/v1/books/batch", files=[
            upload_file("valid.txt", "story"),
            upload_file("broken.rtf", "story"),
            upload_file("empty.txt", ""),
        ])
        body = response.json()
        assert body["succeeded"] == 1
        assert body["failed"] == 2
        assert body["items"][0]["error"] is None
        assert "RTF" in body["items"][1]["error"] or "TXT" in body["items"][1]["error"]
        assert body["items"][2]["error"] == "文件不能为空"


def test_batch_upload_sanitizes_filenames_and_enforces_per_file_limit():
    app, data = make_app()
    with TestClient(app) as client:
        response = client.post("/api/v1/books/batch", files=[
            upload_file(r"C:\\imports\\safe name.txt", "story"),
            upload_file("oversized.txt", "x" * 1025),
            upload_file("x" * 251 + ".txt", "story"),
        ])
        body = response.json()
        assert body["succeeded"] == 1
        assert body["failed"] == 2
        assert body["items"][0]["book"]["file_name"] == "safe name.txt"
        assert "大小" in body["items"][1]["error"]
        assert body["items"][2]["error"]


def test_batch_upload_enforces_count_and_total_size_limits():
    app, data = make_app()
    with TestClient(app) as client:
        too_many = [upload_file(f"book-{index}.txt") for index in range(4)]
        response = client.post("/api/v1/books/batch", files=too_many)
        assert response.status_code == 413

        response = client.post("/api/v1/books/batch", files=[
            upload_file("first.txt", "a" * 1024),
            upload_file("second.txt", "b" * 1024),
        ])
        body = response.json()
        assert body["succeeded"] == 1
        assert body["failed"] == 1
        assert body["items"][0]["error"] is None
        assert body["items"][1]["error"]


def test_parse_exports_clean_text_and_chapter_files(tmp_path):
    data = tmp_path
    app = create_app(Config(
        data_dir=data,
        database_path=data / "test.sqlite3",
        max_upload_bytes=1024,
        max_batch_files=3,
        max_batch_upload_bytes=1800,
    ))
    source = "第一章 开始\n正文一\n\n第二章 继续\n正文二"

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/books",
            params={"filename": "检验稿.txt"},
            content=source.encode("utf-8"),
        )
        assert uploaded.status_code == 201
        book_id = uploaded.json()["book_id"]

        parsed = client.post(f"/api/v1/books/{book_id}/parse")
        assert parsed.status_code == 202

        chapters = client.get(f"/api/v1/books/{book_id}/chapters").json()["chapters"]
        details = [
            client.get(f"/api/v1/books/{book_id}/chapters/{chapter['id']}").json()
            for chapter in chapters
        ]
        book_dir = data / "novel" / book_id
        assert (book_dir / "unified.txt").is_file()
        assert (book_dir / "chapters.json").is_file()
        assert len(chapters) == 2
        for index, (chapter, detail) in enumerate(zip(chapters, details), start=1):
            output_path = Path(chapter["text_path"])
            assert output_path == book_dir / "chapters" / f"{index:04d}.txt"
            assert output_path.read_text(encoding="utf-8") == detail["content"]

        source_path = Path(app.state.db.one(
            "SELECT source_path FROM books WHERE book_id=?", (book_id,),
        )["source_path"])
        source_path.write_text("新版唯一章节\n更新后的正文", encoding="utf-8")
        assert client.post(f"/api/v1/books/{book_id}/parse").status_code == 202
        refreshed = client.get(f"/api/v1/books/{book_id}/chapters").json()["chapters"]
        assert len(refreshed) == 1
        old_chapter_path = data / "novel" / book_id / "chapters" / "0002.txt"
        assert not old_chapter_path.exists()
        assert client.delete(f"/api/v1/books/{book_id}").status_code == 200
        assert not (data / "novel" / book_id).exists()
