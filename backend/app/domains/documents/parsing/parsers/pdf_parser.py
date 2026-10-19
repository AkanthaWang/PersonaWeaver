from pathlib import Path


def parse_pdf(file_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError("PDF parser requires pypdf. Install it with `pip install pypdf`.") from exc

    try:
        reader = PdfReader(str(file_path))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"Failed to parse PDF file: {file_path}") from exc

    return "\n\n".join(page_text for page_text in pages if page_text)
