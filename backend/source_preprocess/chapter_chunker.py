import re


def _normalize_heading_text(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _detect_heading_regex(sample_text: str) -> re.Pattern:
    if re.search(r"^\s*\d{1,4}\s*回\b", sample_text, re.MULTILINE):
        return re.compile(r"^\s*\d{1,4}\s*回\s*.*$", re.MULTILINE)

    if re.search(r"^\s*第\s*[一二三四五六七八九十百千0-9]{1,6}\s*[章节回]\b", sample_text, re.MULTILINE):
        return re.compile(r"^\s*第\s*[一二三四五六七八九十百千0-9]{1,6}\s*[章节回]\s*.*$", re.MULTILINE)

    return re.compile(
        r"^(?:\s*(?:第?\s*[一二三四五六七八九十百千0-9]{1,6}\s*[章节回])\s*.*|\s*\d{1,4}\s*回\s*.*)$",
        re.MULTILINE,
    )


def _is_noise_block(block: str) -> bool:
    stripped = block.strip()
    if not stripped:
        return True
    if re.match(r"^[\s\-—_*·.=]+$", stripped):
        return True
    if re.search(r"（图）|图片链接|点击察看图片", stripped):
        return True
    if re.search(r"视频访谈|播放器|\[sp=player|\.swf", stripped):
        return True
    if re.search(r"新书|已上传|传送门|书号|起点|支持|简介", stripped):
        return True
    if re.search(r"https?://|www\.|<a\b|bookid=", stripped):
        return True
    return False


def _filter_preface_blocks(preface: str) -> str:
    blocks = re.split(r"\n\s*\n+", preface)
    kept = [b.strip() for b in blocks if b.strip() and not _is_noise_block(b)]
    return "\n\n".join(kept).strip()


def _remove_repeated_heading_lines(content: str, heading: str) -> str:
    if not content:
        return ""

    lines = [line.rstrip() for line in content.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)

    if not lines:
        return ""

    heading_norm = _normalize_heading_text(heading)
    if not heading_norm:
        return "\n".join(lines).strip()

    cleaned_lines = []
    heading_seen = False
    for line in lines:
        normalized_line = _normalize_heading_text(line)
        if normalized_line == heading_norm:
            if heading_seen:
                continue
            heading_seen = True
            cleaned_lines.append(line)
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _chapter_body_without_heading(content: str, heading: str) -> str:
    if not content:
        return ""

    lines = [line.rstrip() for line in content.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)

    if not lines:
        return ""

    heading_norm = _normalize_heading_text(heading)
    if heading_norm and _normalize_heading_text(lines[0]) == heading_norm:
        body_lines = lines[1:]
    else:
        body_lines = lines

    return "\n".join(body_lines).strip()


def _should_drop_chapter(content: str, heading: str) -> bool:
    body = _chapter_body_without_heading(content, heading)
    if not body:
        return True

    return False


def split_into_chapters(text: str, filter_noise: bool = False) -> list[dict]:
    sample_text = text[:20000]
    heading_re = _detect_heading_regex(sample_text)
    matches = list(heading_re.finditer(text))

    chapters: list[dict] = []
    if matches:
        preface = text[: matches[0].start()].strip()
        if filter_noise and preface:
            preface = _filter_preface_blocks(preface)
        if preface:
            preface_title = "前言"
            if re.search(r"^\s*自序\s*$", preface, re.MULTILINE):
                preface_title = "自序"
            elif re.search(r"^\s*序\s*$", preface, re.MULTILINE):
                preface_title = "序"
            chapters.append({"title": preface_title, "content": preface})

        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            title_line = match.group(0).strip()
            content = _remove_repeated_heading_lines(content, title_line)

            if filter_noise:
                content = content.strip()

            if _should_drop_chapter(content, title_line):
                continue

            chapters.append({"title": title_line or "章节", "content": content})
    else:
        chunk_size = 4000
        pos = 0
        chunk_no = 1
        while pos < len(text):
            chunk = text[pos : pos + chunk_size]
            cleaned_chunk = _remove_repeated_heading_lines(chunk, f"Chunk {chunk_no}")
            if not _should_drop_chapter(cleaned_chunk, f"Chunk {chunk_no}"):
                chapters.append({"title": f"Chunk {chunk_no}", "content": cleaned_chunk})
            pos += chunk_size
            chunk_no += 1

    return [chapter for chapter in chapters if chapter.get("content", "").strip()]
