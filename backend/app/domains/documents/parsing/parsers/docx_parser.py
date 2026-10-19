from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        name = _local_name(node.tag)
        if name == "t" and node.text:
            parts.append(node.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def parse_docx(file_path: Path) -> str:
    try:
        with ZipFile(file_path) as archive:
            document_xml = archive.read("word/document.xml")
    except KeyError as exc:
        raise ValueError(f"Invalid DOCX file, missing word/document.xml: {file_path}") from exc
    except BadZipFile as exc:
        raise ValueError(f"Invalid DOCX zip file: {file_path}") from exc

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid DOCX document XML: {file_path}") from exc

    paragraphs = [
        text
        for node in root.iter()
        if _local_name(node.tag) == "p"
        for text in [_paragraph_text(node)]
        if text
    ]
    return "\n\n".join(paragraphs)
