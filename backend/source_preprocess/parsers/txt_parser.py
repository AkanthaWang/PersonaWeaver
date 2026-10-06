from pathlib import Path

try:
    import chardet
except Exception:  # pragma: no cover - optional dependency
    chardet = None


_CANDIDATE_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "gb18030",
    "gbk",
    "big5",
    "cp936",
)


def _decode_with_candidates(raw: bytes) -> tuple[str, str]:
    if not raw:
        return "", "utf-8"

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="ignore"), "utf-8-sig"

    if chardet is not None:
        detected = chardet.detect(raw) or {}
        detected_encoding = detected.get("encoding")
        if detected_encoding:
            try:
                return raw.decode(detected_encoding, errors="ignore"), detected_encoding
            except Exception:
                pass

    for encoding in _CANDIDATE_ENCODINGS:
        try:
            return raw.decode(encoding, errors="ignore"), encoding
        except Exception:
            continue

    return raw.decode("utf-8", errors="replace"), "utf-8"


def detect_encoding(file_path: Path) -> str:
    raw = file_path.read_bytes()[:4096]
    if not raw:
        return "utf-8"

    _, encoding = _decode_with_candidates(raw)
    return encoding


def decode_text_file(file_path: Path) -> str:
    raw = file_path.read_bytes()
    text, _ = _decode_with_candidates(raw)
    return text


def normalize_text_file_to_utf8(file_path: Path) -> str:
    text = decode_text_file(file_path)
    file_path.write_text(text, encoding="utf-8")
    return text


def parse_txt(file_path: Path) -> str:
    return decode_text_file(file_path)
