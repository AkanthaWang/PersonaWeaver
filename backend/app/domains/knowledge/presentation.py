"""Compact character milestones with chapter-specific sources."""


def character_milestones(content):
    groups = {}
    evidence = content.get("evidence") or []
    entries = [
        (entry.get("key_events"), entry)
        for entry in evidence
        if isinstance(entry, dict) and entry.get("key_events")
    ]
    if not entries:
        entries = [
            (entry.get("value"), entry)
            for entry in (content.get("field_history") or {}).get("key_events", [])
            if isinstance(entry, dict)
        ]
    if not entries and content.get("key_events"):
        entries = [(content["key_events"], {})]
    for values, entry in entries:
        values = values if isinstance(values, list) else [values]
        sources = entry.get("sources") or [entry]
        for text in values:
            if not isinstance(text, str) or not text.strip():
                continue
            text = " ".join(text.split())
            key = text.rstrip("。；;.!！?？")
            milestone = groups.setdefault(key, {"text": text, "chapters": []})
            for source in sources:
                chapter = {
                    "chapter_id": source.get("chapter_id"),
                    "chapter_no": source.get("chapter_no"),
                    "chapter_title": source.get("chapter_title") or source.get("chapter"),
                }
                if (chapter["chapter_id"] or chapter["chapter_no"] is not None) and chapter not in milestone["chapters"]:
                    milestone["chapters"].append(chapter)
    for milestone in groups.values():
        milestone["chapters"].sort(key=lambda chapter: chapter["chapter_no"] if chapter["chapter_no"] is not None else float("inf"))
        milestone["chapters"] = milestone["chapters"][:1]
    return sorted(groups.values(), key=lambda milestone: next(
        (chapter["chapter_no"] for chapter in milestone["chapters"] if chapter["chapter_no"] is not None),
        float("inf"),
    ))
