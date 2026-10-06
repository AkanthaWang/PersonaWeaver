from backend.source_preprocess.chapter_chunker import split_into_chapters


def test_split_into_chapters_removes_duplicate_heading_line():
    body = "这里才是正文的开始，内容足够长，可以保留。" * 8
    text = f"第1回 第一章\n第1回 第一章\n{body}"

    chapters = split_into_chapters(text, filter_noise=True)

    assert len(chapters) == 1
    assert chapters[0]["title"] == "第1回 第一章"
    assert chapters[0]["content"].startswith("第1回 第一章")
    assert "第1回 第一章\n第1回 第一章" not in chapters[0]["content"]
    assert "这里才是正文的开始" in chapters[0]["content"]


def test_split_into_chapters_keeps_short_but_real_chapter():
    text = "第1回 第一章\n第1回 第一章\n只有一点点正文，但这是有效内容。"

    chapters = split_into_chapters(text, filter_noise=True)

    assert len(chapters) == 1
    assert chapters[0]["title"] == "第1回 第一章"
    assert "只有一点点正文" in chapters[0]["content"]


def test_split_into_chapters_discards_title_only_shell():
    text = "第1回 第一章\n第1回 第一章\n"

    chapters = split_into_chapters(text, filter_noise=True)

    assert chapters == []