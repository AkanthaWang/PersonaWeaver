from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.source_preprocess.parsers import parse_input_to_text


def _write_minimal_pdf(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    stream = f"BT /F1 24 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects.append(
        b"5 0 obj\n<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n"
    )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    path.write_bytes(bytes(pdf))


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "")
        archive.writestr("word/document.xml", document_xml)


def _write_minimal_epub(path: Path, title: str, chapter_text: str) -> None:
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
    opf_xml = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
"""
    chapter_xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>{title}</h1>
    <p>{chapter_text}</p>
  </body>
</html>
"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/container.xml", container_xml)
        archive.writestr("OEBPS/content.opf", opf_xml)
        archive.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)


def test_parse_pdf_extracts_page_text(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    _write_minimal_pdf(pdf_path, "PersonaWeaver PDF parser")

    text = parse_input_to_text(str(pdf_path), source_type="pdf")

    assert "PersonaWeaver PDF parser" in text


def test_parse_docx_extracts_paragraph_text(tmp_path):
    docx_path = tmp_path / "sample.docx"
    _write_minimal_docx(docx_path, ["第一章 起点", "PersonaWeaver DOCX parser"])

    text = parse_input_to_text(str(docx_path), source_type="docx")

    assert "第一章 起点" in text
    assert "PersonaWeaver DOCX parser" in text


def test_parse_epub_extracts_spine_text(tmp_path):
    epub_path = tmp_path / "sample.epub"
    _write_minimal_epub(epub_path, "第一章", "PersonaWeaver EPUB parser")

    text = parse_input_to_text(str(epub_path), source_type="epub")

    assert "第一章" in text
    assert "PersonaWeaver EPUB parser" in text


def test_parse_unsupported_type_raises_clear_error(tmp_path):
    source_path = tmp_path / "sample.xyz"
    source_path.write_text("ignored", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported source type: xyz"):
        parse_input_to_text(str(source_path), source_type="xyz")
