from pathlib import Path

try:
    import chardet
except Exception:  # pragma: no cover - optional dependency
    chardet = None

try:
    from charset_normalizer import from_bytes as normalize_from_bytes
except Exception:  # pragma: no cover - optional dependency
    normalize_from_bytes = None


_CANDIDATE_ENCODINGS = (
    "gb18030",
    "gbk",
    "big5",
    "cp949",
    "cp1252",
)


def _strict_decode(raw: bytes, encoding: str) -> str | None:
    try:
        return raw.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return None


def _script_score(text: str, encoding: str) -> int:
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    hangul = sum("\uac00" <= char <= "\ud7af" for char in text)
    score = cjk * 2 - hangul * 3
    if encoding.lower().replace("_", "-") in {"cp949", "euc-kr", "uhc"} and hangul > cjk and hangul >= 3:
        score += len(text) * 4
    return score


def _decode_with_candidates(raw: bytes) -> tuple[str, str]:
    if not raw:
        return "", "utf-8"

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"

    # UTF-8 is deterministic, so prefer strict decoding before heuristics.
    decoded = _strict_decode(raw, "utf-8")
    if decoded is not None:
        return decoded, "utf-8"

    detected_encodings = []
    if chardet is not None:
        try:
            detected = chardet.detect(raw) or {}
            detected_encoding = detected.get("encoding")
            confidence = float(detected.get("confidence") or 0)
            if detected_encoding and confidence >= 0.5:
                detected_encodings.append(detected_encoding)
        except Exception:
            pass

    if normalize_from_bytes is not None:
        try:
            match = normalize_from_bytes(raw).best()
            if match and match.encoding:
                detected_encodings.append(match.encoding)
        except Exception:
            pass

    checked = set()
    decoded_candidates = []
    for encoding in (*detected_encodings, *_CANDIDATE_ENCODINGS):
        normalized = encoding.lower().replace("_", "-")
        if normalized in checked:
            continue
        checked.add(normalized)
        decoded = _strict_decode(raw, encoding)
        if decoded is not None:
            decoded_candidates.append((decoded, encoding))

    if decoded_candidates:
        return max(decoded_candidates, key=lambda item: _script_score(item[0], item[1]))

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
