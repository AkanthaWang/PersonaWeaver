"""Deterministic chapter detection and paragraph-first fallback chunking."""

from __future__ import annotations

import re


TARGET_CHARS = 6000
MAX_HEADING_CHARS = 120

_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"第\s*(?:[0-9]{1,8}|[一二三四五六七八九十百千万零〇两]+)\s*(?:章|节|回|卷|部|篇)[^\n]*"
    r"|Chapter\s+[0-9IVXLCDM]+(?:\s*[:.\-、]\s*[^\n]*)?"
    r"|[0-9]{1,4}\s*[、.．:：]\s*[^\n]+"
    r"|#{1,6}\s+[^\n]+"
    r")\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHINESE_HEADING_RE = re.compile(
    r"^\s*第\s*(?:[0-9]{1,8}|[一二三四五六七八九十百千万零〇两]+)\s*(?:章|节|回|卷|部|篇)",
    re.IGNORECASE,
)
_NUMBERED_RE = re.compile(r"^\s*[0-9]{1,4}\s*[、.．:：]\s*")
_SENTENCE_RE = re.compile(r"[^。！？.!?]*[。！？.!?]+|[^。！？.!?]+$", re.S)


def _normalize_text(text: str) -> str:
    """Normalize line endings while preserving character offsets."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _normalize_heading_text(text: str) -> str:
    text = re.sub(r"^\s*#{1,6}\s*", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if len(stripped) > MAX_HEADING_CHARS:
        return True
    if re.fullmatch(r"[\s\-—_*·.=~#]+", stripped):
        return True
    if re.search(r"(?:https?://|www\.|<a\b|bookid=|\.swf\b)", stripped, re.IGNORECASE):
        return True
    if re.search(r"(?:目录|目录页|页眉|页脚|图片链接|点击察看图片|播放器|视频访谈)", stripped):
        return True
    return False


def _heading_confidence(line: str) -> float:
    return 0.95 if _CHINESE_HEADING_RE.match(line) else 0.85


def _heading_candidates(text: str) -> list[dict]:
    candidates = []
    for match in _HEADING_RE.finditer(text):
        line = match.group(0).strip()
        if _is_noise_line(line):
            continue
        normalized = _normalize_heading_text(line)
        if not normalized:
            continue
        candidates.append(
            {
                "start": match.start(),
                "end": match.end(),
                "title": line,
                "normalized": normalized,
                "confidence": _heading_confidence(line),
            }
        )

    # Repeated page headers or duplicated chapter lines are noise. Retaining
    # the first candidate keeps all following text in the original chapter.
    seen = set()
    unique = []
    for candidate in candidates:
        if candidate["normalized"] in seen:
            continue
        seen.add(candidate["normalized"])
        unique.append(candidate)
    return unique


def _is_noise_block(block: str) -> bool:
    stripped = block.strip()
    if not stripped:
        return True
    if re.fullmatch(r"[\s\-—_*·.=~]+", stripped):
        return True
    if re.search(r"（图）|图片链接|点击察看图片|视频访谈|播放器|\[sp=player|\.swf", stripped):
        return True
    return bool(re.search(r"https?://|www\.|<a\b|bookid=", stripped, re.IGNORECASE))


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end, text[start:end]


def _record(
    text: str,
    start: int,
    end: int,
    title: str,
    method: str,
    confidence: float,
    preserve_span: bool = False,
) -> dict | None:
    if preserve_span:
        content = text[start:end]
    else:
        start, end, content = _trimmed_span(text, start, end)
    if not content:
        return None
    return {
        "title": title.strip() or "章节",
        "content": content,
        "source_start": start,
        "source_end": end,
        "split_method": method,
        "confidence": confidence,
    }


def _sentence_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans = []
    for match in _SENTENCE_RE.finditer(text[start:end]):
        piece_start = start + match.start()
        piece_end = start + match.end()
        if text[piece_start:piece_end].strip():
            spans.append((piece_start, piece_end))
    return spans


def _fallback_chunks(text: str) -> list[dict]:
    paragraphs = []
    cursor = 0
    parts = re.split(r"(\n\s*\n+)", text)
    for index in range(0, len(parts), 2):
        part = parts[index]
        separator = parts[index + 1] if index + 1 < len(parts) else ""
        start = cursor
        end = start + len(part) + len(separator)
        if part.strip():
            paragraphs.append((start, end))
        cursor = end

    chunks = []
    current_start = None
    current_end = None

    def flush():
        nonlocal current_start, current_end
        if current_start is not None and current_end is not None:
            record = _record(
                text, current_start, current_end, "文本片段", "paragraph_fallback", 0.55, preserve_span=True
            )
            if record:
                chunks.append(record)
        current_start = current_end = None

    for paragraph_start, paragraph_end in paragraphs:
        if paragraph_end - paragraph_start <= TARGET_CHARS:
            if current_start is None:
                current_start = paragraph_start
            if current_end is not None and paragraph_end - current_start > TARGET_CHARS:
                flush()
                current_start = paragraph_start
            current_end = paragraph_end
            continue

        flush()
        sentence_spans = _sentence_spans(text, paragraph_start, paragraph_end)
        if not sentence_spans:
            sentence_spans = [(paragraph_start, paragraph_end)]
        sentence_start = sentence_end = None
        for part_start, part_end in sentence_spans:
            if part_end - part_start > TARGET_CHARS:
                if sentence_start is not None:
                    chunks.append(
                        _record(text, sentence_start, sentence_end, "文本片段", "paragraph_fallback", 0.55, preserve_span=True)
                    )
                    sentence_start = sentence_end = None
                for offset in range(part_start, part_end, TARGET_CHARS):
                    chunks.append(
                        _record(
                            text, offset, min(offset + TARGET_CHARS, part_end),
                            "文本片段", "paragraph_fallback", 0.55, preserve_span=True,
                        )
                    )
                continue
            if sentence_start is None:
                sentence_start = part_start
            if sentence_end is not None and part_end - sentence_start > TARGET_CHARS:
                chunks.append(
                    _record(text, sentence_start, sentence_end, "文本片段", "paragraph_fallback", 0.55, preserve_span=True)
                )
                sentence_start = part_start
            sentence_end = part_end
        if sentence_start is not None:
            chunks.append(
                _record(text, sentence_start, sentence_end, "文本片段", "paragraph_fallback", 0.55, preserve_span=True)
            )

    flush()
    return [chunk for chunk in chunks if chunk]


def split_into_chapters(text: str, filter_noise: bool = False) -> list[dict]:
    """Split unified text into chapter records with source metadata."""
    text = _normalize_text(text)
    if not text.strip():
        return []

    candidates = _heading_candidates(text)
    if not candidates:
        return _fallback_chunks(text)

    chapters = []
    first_start = candidates[0]["start"]
    preface_start, preface_end, preface = _trimmed_span(text, 0, first_start)
    if preface:
        if filter_noise:
            blocks = [
                block.strip()
                for block in re.split(r"\n\s*\n+", preface)
                if block.strip() and not _is_noise_block(block)
            ]
            preface = "\n\n".join(blocks)
        if preface:
            title = "前言"
            if re.search(r"(?:^|\n)\s*自序\s*(?:\n|$)", preface):
                title = "自序"
            elif re.search(r"(?:^|\n)\s*序\s*(?:\n|$)", preface):
                title = "序"
            chapters.append(
                {
                    "title": title,
                    "content": preface,
                    "source_start": preface_start,
                    "source_end": preface_end,
                    "split_method": "preface",
                    "confidence": 0.75,
                }
            )

    for index, candidate in enumerate(candidates):
        start = candidate["start"]
        end = candidates[index + 1]["start"] if index + 1 < len(candidates) else len(text)
        record = _record(
            text, start, end, candidate["title"], "heading", candidate["confidence"], preserve_span=True
        )
        if record:
            chapters.append(record)

    return chapters or _fallback_chunks(text)
