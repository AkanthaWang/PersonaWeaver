from backend.app.domains.documents.parsing.chapter_chunker import split_into_chapters
from backend.app.domains.documents.parsing.parsers.txt_parser import (
    decode_text_file,
    detect_encoding,
    normalize_text_file_to_utf8,
    parse_txt,
)


def test_reads_utf8_and_utf8_bom_without_changing_chinese(tmp_path):
    text = "第一章 标题\n中文正文。"
    plain = tmp_path / "plain.txt"
    bom = tmp_path / "bom.txt"
    plain.write_bytes(text.encode("utf-8"))
    bom.write_bytes(text.encode("utf-8-sig"))

    assert parse_txt(plain) == text
    assert parse_txt(bom) == text
    assert detect_encoding(plain) == "utf-8"
    assert detect_encoding(bom) == "utf-8-sig"


def test_detects_gbk_text_and_recognizes_chapter_heading(tmp_path):
    text = "第一章 标题\n中文正文。"
    source = tmp_path / "gbk.txt"
    source.write_bytes(text.encode("gbk"))

    decoded = decode_text_file(source)
    chapters = split_into_chapters(decoded)

    assert decoded == text
    assert chapters[0]["title"] == "第一章 标题"
    assert chapters[0]["content"] == text


def test_normalize_text_file_rewrites_detected_encoding_as_utf8(tmp_path):
    text = "章节内容，中文。"
    source = tmp_path / "legacy.txt"
    source.write_bytes(text.encode("gbk"))

    assert normalize_text_file_to_utf8(source) == text
    assert source.read_bytes() == text.encode("utf-8")
