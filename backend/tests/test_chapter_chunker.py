from backend.app.domains.documents.parsing.chapter_chunker import split_into_chapters


def test_recognizes_supported_heading_formats_and_metadata():
    text = (
        "第十二章 风起\n中文正文\n\n"
        "第12节 暗流\n第二段\n\n"
        "第3回 相逢\n第三段\n\n"
        "Chapter 4: Arrival\nEnglish text\n\n"
        "1. First\nNumbered text\n\n"
        "2、Second\nMore text\n\n"
        "# Markdown title\nMarkdown text"
    )

    chapters = split_into_chapters(text)

    assert [chapter["split_method"] for chapter in chapters] == ["heading"] * 7
    assert [chapter["confidence"] for chapter in chapters] == [0.95, 0.95, 0.95, 0.85, 0.85, 0.85, 0.85]
    assert [chapter["title"] for chapter in chapters] == [
        "第十二章 风起", "第12节 暗流", "第3回 相逢", "Chapter 4: Arrival",
        "1. First", "2、Second", "# Markdown title",
    ]
    for chapter in chapters:
        assert text[chapter["source_start"]:chapter["source_end"]] == chapter["content"]


def test_preface_and_repeated_heading_are_kept_without_duplicate_chapters():
    text = "序\n序言正文\n\n第一章 开始\n正文\n\n第一章 开始\n重复页眉后正文"

    chapters = split_into_chapters(text)

    assert chapters[0]["title"] == "序"
    assert chapters[0]["split_method"] == "preface"
    assert chapters[0]["confidence"] == 0.75
    assert len(chapters) == 2
    assert "第一章 开始\n重复页眉后正文" in chapters[1]["content"]


def test_urls_decorations_and_noise_lines_are_not_chapter_candidates():
    text = "目录\nhttps://example.test\n------\n普通正文\nwww.example.test"

    chapters = split_into_chapters(text)

    assert len(chapters) == 1
    assert chapters[0]["split_method"] == "paragraph_fallback"
    assert chapters[0]["content"] == text


def test_fallback_accumulates_paragraphs_near_target_and_tracks_ranges():
    first = "甲" * 3500
    second = "乙" * 3000
    third = "丙" * 1000
    text = f"{first}\n\n{second}\n\n{third}"

    chapters = split_into_chapters(text)

    assert len(chapters) == 2
    assert chapters[0]["content"] == f"{first}\n\n"
    assert chapters[1]["content"] == f"{second}\n\n{third}"
    assert all(chapter["split_method"] == "paragraph_fallback" for chapter in chapters)
    assert all(chapter["confidence"] == 0.55 for chapter in chapters)
    assert all(text[c["source_start"]:c["source_end"]] == c["content"] for c in chapters)
    assert chapters[0]["source_end"] <= chapters[1]["source_start"]


def test_oversized_paragraph_splits_on_sentences_then_character_limit():
    text = ("句子。" * 1000) + ("超" * 13000)

    chapters = split_into_chapters(text)

    assert len(chapters) >= 4
    assert all(len(chapter["content"]) <= 6000 for chapter in chapters)
    assert all(text[c["source_start"]:c["source_end"]] == c["content"] for c in chapters)
    assert chapters[0]["content"].endswith("。")
    assert "".join(chapter["content"] for chapter in chapters) == text
    assert all(left["source_end"] == right["source_start"] for left, right in zip(chapters, chapters[1:]))

