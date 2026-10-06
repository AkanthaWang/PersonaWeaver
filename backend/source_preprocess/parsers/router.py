from pathlib import Path

from .docx_parser import parse_docx
from .epub_parser import parse_epub
from .pdf_parser import parse_pdf
from .txt_parser import parse_txt


TEXT_EXTS = {"txt", "md"}
PDF_EXTS = {"pdf"}
DOCX_EXTS = {"docx"}
EPUB_EXTS = {"epub"}
UNIMPLEMENTED_TEXT_EXTS = {"doc"}
IMAGE_EXTS = {"jpg", "jpeg", "heic", "heif", "png", "webp"}
WEB_TYPES = {"url", "html"}


def parse_input_to_text(source_path: str, source_type: str | None = None) -> str:
    path = Path(source_path)
    ext = (source_type or path.suffix.lstrip(".")).lower()

    if ext in TEXT_EXTS:
        return parse_txt(path)

    if ext in PDF_EXTS:
        return parse_pdf(path)

    if ext in DOCX_EXTS:
        return parse_docx(path)

    if ext in EPUB_EXTS:
        return parse_epub(path)

    if ext in UNIMPLEMENTED_TEXT_EXTS:
        raise NotImplementedError(f"{ext} parser is not implemented yet. Current phase supports txt/md/pdf/docx/epub.")

    if ext in IMAGE_EXTS:
        raise NotImplementedError("Image OCR parser is not implemented yet in current phase.")

    if ext in WEB_TYPES:
        raise NotImplementedError("Web crawler parser is not implemented yet in current phase.")

    raise ValueError(f"Unsupported source type: {ext}")
