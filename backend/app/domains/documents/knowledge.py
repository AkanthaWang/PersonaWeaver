"""Deterministic fact projections and persistent human identity decisions."""

import json
import unicodedata

from fastapi import HTTPException

from backend.app.ai.extraction_pipeline import KINDS, digest
from backend.app.db.database import identifier, now

PROJECTION_VERSION = "entity-timeline-v5-ranked-storylines"
SCALAR_FIELDS = ("summary", "description", "identity", "appearance", "personality",
                 "time", "owner", "significance", "type")
LIST_FIELDS = ("aliases", "behavior", "speech", "relationships", "key_events", "state_changes",
               "involved_characters", "related_characters")


def normalized_name(value):
    return " ".join(unicodedata.normalize("NFKC", value or "").split()).casefold()


def fact_order(fact):
    sources = fact.get("sources", [])
    origin = min(sources, key=lambda source: (source["chapter_no"], source["start"])) if sources else {}
    return (origin.get("chapter_no", fact.get("chapter_no", 0)), origin.get("start", 0), fact["fact_id"])


def aggregate(group):
    """Keep changing values dated instead of flattening them into one biography."""
    fields, history = {}, {}
    for fact in group:
        for key in SCALAR_FIELDS + LIST_FIELDS:
            value = fact.get(key)
            if not value:
                continue
            if key in LIST_FIELDS:
                values = value if isinstance(value, list) else [value]
                target = fields.setdefault(key, [])
                for item in values:
                    if item not in target:
                        target.append(item)
            else:
                fields[key] = value
            changes = history.setdefault(key, [])
            if changes and changes[-1]["value"] == value:
                changes[-1]["fact_ids"].append(fact["fact_id"])
                continue
            changes.append({
                "value": value, "chapter_no": fact["chapter_no"], "chapter_id": fact["chapter_id"],
                "chapter": fact["chapter"], "fact_ids": [fact["fact_id"]],
            })
    frequency = sum(
        max(1, sum(source.get("occurrence", 1) for source in fact.get("sources", [])))
        for fact in group
    )
    return {**fields, "field_history": history, "frequency": frequency}


def world_category(entry):
    value = normalized_name(" ".join(
        str(entry.get(key, "")) for key in ("type", "description", "significance")
    ))
    if any(term in value for term in ("势力", "组织", "宗门", "殿", "联盟", "团")):
        return "势力"
    if any(term in value for term in ("规则", "体系", "制度", "职业", "灵力")):
        return "规则体系"
    if any(term in value for term in ("种族", "族群", "魔族", "人族")):
        return "种族"
    if any(term in value for term in ("装备", "武器", "物品")):
        return "关键物品"
    return "地域"


def build_storylines(events):
    """Build a conservative event-to-storyline projection.

    Entity identity is deliberately not used as a storyline boundary. Events
    are grouped only when their names or state changes provide an explicit
    continuity signal; otherwise every event gets its own line.
    """
    lines = []
    for event in sorted(events, key=lambda item: fact_order(item["evidence"][0])):
        event_names = {normalized_name(event.get("name"))}
        event_names.update(normalized_name(value) for value in event.get("aliases", []))
        changes = {normalized_name(value) for value in event.get("state_changes", [])}
        best = None
        for line in lines:
            previous = line["stages"][-1]
            previous_names = {normalized_name(previous.get("name"))}
            previous_names.update(normalized_name(value) for value in previous.get("aliases", []))
            previous_changes = {normalized_name(value) for value in previous.get("state_changes", [])}
            same_signal = bool(event_names & previous_names) or bool(changes & previous_changes)
            adjacent = event["first_chapter"] <= previous["last_chapter"] + 1
            if same_signal and adjacent:
                best = line
                break
        if best is None:
            best = {
                "storyline_id": "storyline_" + digest([event["entity_id"]])[:32],
                "title": event["name"],
                "summary": event.get("summary") or event.get("description") or event["name"],
                "stages": [],
                "source_ids": [],
                "chapters": [],
            }
            lines.append(best)
        best["stages"].append({
            "stage_id": "stage_" + digest([best["storyline_id"], event["entity_id"]])[:32],
            "title": event["name"],
            "summary": event.get("summary") or event.get("description") or event["name"],
            "aliases": event.get("aliases", []),
            "state_changes": event.get("state_changes", []),
            "event_id": event["entity_id"],
            "fact_ids": event["source_ids"],
            "evidence": event["evidence"],
            "chapter_no": event["first_chapter"],
            "last_chapter": event["last_chapter"],
        })
        best["source_ids"] = sorted(set(best["source_ids"]) | set(event["source_ids"]))
        best["chapters"] = sorted(set(best["chapters"]) | set(
            fact["chapter_no"] for fact in event["evidence"]
        ))
    for line in lines:
        line["stage_count"] = len(line["stages"])
    return lines


def load_results(db, book_id):
    return [(dict(row), json.loads(row["payload"])) for row in db.all(
        "SELECT c.*,e.content AS payload FROM extractions e JOIN chapters c ON c.id=e.chapter_id "
        "WHERE e.book_id=? ORDER BY c.chapter_no", (book_id,),
    )]


def facts_for(results):
    facts = {}
    for chapter, payload in results:
        for kind in KINDS:
            for index, raw in enumerate(payload.get(kind, [])):
                fact = dict(raw)
                fact_id = fact.get("fact_id") or "legacy_" + digest([chapter["id"], kind, index, raw])[:32]
                sources = sorted(fact.get("sources", []), key=lambda s: (s["chapter_no"], s["start"]))
                origin = min(sources, key=lambda source: (source["chapter_no"], source["start"])) if sources else None
                facts[fact_id] = {
                    **fact, "fact_id": fact_id, "kind": kind,
                    "chapter_id": origin["chapter_id"] if origin else chapter["id"],
                    "chapter_no": origin["chapter_no"] if origin else chapter["chapter_no"],
                    "chapter": origin["chapter_title"] if origin else chapter["title"], "sources": sources,
                }
    return facts


def project(results, previous, resolutions):
    facts = facts_for(results)
    parent = {key: key for key in facts}
    members = {key: {key} for key in facts}

    def root(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    barriers, invalid, active = [], [], []
    for decision in resolutions:
        left = set(json.loads(decision["source_ids"]))
        right = set(json.loads(decision["other_source_ids"]))
        if not (left | right) <= facts.keys():
            invalid.append(decision["id"])
            continue
        if decision["action"] == "split":
            barriers.append((left, right))
        active.append((decision, left, right))

    def union(left, right, manual=False):
        a, b = root(left), root(right)
        if a == b:
            return
        a_ids, b_ids = members[a], members[b]
        if not manual and any((a_ids & x and b_ids & y) or (a_ids & y and b_ids & x) for x, y in barriers):
            return
        parent[b] = a
        members[a].update(members.pop(b))

    by_name = {}
    for key, fact in facts.items():
        by_name.setdefault((fact["kind"], normalized_name(fact["name"])), []).append(key)
    for (kind, _), ids in by_name.items():
        for index, left_id in enumerate(ids):
            left = facts[left_id]
            for right_id in ids[index + 1:]:
                right = facts[right_id]
                same_quote = bool({digest(s) for s in left["sources"]} & {digest(s) for s in right["sources"]})
                same_position = any(
                    left_source["chapter_id"] == right_source["chapter_id"]
                    and left_source["start"] == right_source["start"]
                    for left_source in left["sources"] for right_source in right["sources"]
                )
                duplicate = (same_quote or same_position) and all(
                    left.get(field) == right.get(field)
                    for field in SCALAR_FIELDS + LIST_FIELDS
                )
                # Identity attributes are dated facts, never identity
                # boundaries. Recurring events remain distinct unless their
                # source position proves they are duplicate descriptions.
                if kind != "storyline_events" or duplicate:
                    union(left_id, right_id)
    for key, fact in facts.items():
        if fact["kind"] != "characters":
            continue
        for alias in fact.get("aliases", []):
            if any(fact["name"] in s["quote"] and alias in s["quote"] for s in fact["sources"]):
                for other in by_name.get(("characters", normalized_name(alias)), []):
                    union(key, other)
    for decision, left, right in active:
        for side in (left, right):
            ordered = sorted(side)
            for key in ordered[1:]:
                union(ordered[0], key, manual=decision["action"] == "merge")
        if decision["action"] == "merge":
            ordered = sorted(left | right)
            for key in ordered[1:]:
                union(ordered[0], key, manual=True)

    groups = {}
    for key in facts:
        groups.setdefault(root(key), []).append(facts[key])
    old = [(row["id"], set(json.loads(row["source_ids"])), json.loads(row["content"])) for row in previous]
    output, used = {kind: [] for kind in KINDS}, set()
    for group in groups.values():
        group.sort(key=fact_order)
        ids = {fact["fact_id"] for fact in group}
        matches = sorted((item for item in old if item[0] not in used and item[1] & ids),
                         key=lambda item: (-len(item[1] & ids), item[0]))
        entity_id = matches[0][0] if matches else "entity_" + digest([group[0]["kind"], sorted(ids)[0]])[:32]
        if entity_id in used:
            entity_id = "entity_" + digest([group[0]["kind"], sorted(ids)])[:32]
        used.add(entity_id)
        entry = {
            "entity_id": entity_id, "name": group[0]["name"], "kind": group[0]["kind"],
            "source_ids": sorted(ids), "evidence": group, "synthesis": [], "synthesis_status": "pending",
            "aliases": [],
            "needs_review": False, "projection_version": PROJECTION_VERSION,
            "first_chapter": group[0]["chapter_no"], "last_chapter": group[-1]["chapter_no"],
            "chapter_no": group[0]["chapter_no"], "chapter": group[0]["chapter"],
            "chapter_id": group[0]["chapter_id"],
        }
        entry.update(aggregate(group))
        entry["first_appear"] = entry["first_chapter"]
        if entry["kind"] == "world_locations":
            entry["category"] = world_category(entry)
        entry["facts_fingerprint"] = digest(group)
        if matches and matches[0][2].get("facts_fingerprint") == entry["facts_fingerprint"]:
            entry["synthesis"] = matches[0][2].get("synthesis", [])
            entry["synthesis_status"] = matches[0][2].get("synthesis_status", "pending")
            entry["synthesis_model"] = matches[0][2].get("synthesis_model")
            entry["synthesis_version"] = matches[0][2].get("synthesis_version")
        output[entry["kind"]].append(entry)
    for entries in output.values():
        for entry in entries:
            entry["needs_review"] = any(
                other["entity_id"] != entry["entity_id"]
                and entry["kind"] != "storyline_events"
                and ({normalized_name(n) for n in [entry["name"], *entry.get("aliases", [])]}
                     & {normalized_name(n) for n in [other["name"], *other.get("aliases", [])]})
                and not any(
                    (set(entry["source_ids"]) & left and set(other["source_ids"]) & right)
                    or (set(entry["source_ids"]) & right and set(other["source_ids"]) & left)
                    for left, right in barriers
                )
                for other in entries
            )
        entries.sort(key=lambda entry: (
            -entry.get("frequency", 0), entry.get("first_appear", 0),
            normalized_name(entry.get("name")), entry["entity_id"],
        ))
        for display_order, entry in enumerate(entries, start=1):
            entry["display_order"] = display_order
    return output, invalid


def rebuild(db, user_id, book_id, revision):
    from .service import DocumentService

    service = DocumentService(db)
    service.owned_record(user_id, book_id)
    book_db = db.book_database(book_id)
    with book_db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if db.one("SELECT knowledge_revision FROM books WHERE book_id=?", (book_id,))["knowledge_revision"] != revision:
            raise HTTPException(409, "资料已更新，请刷新后重试")
        if conn.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('pending','running')", (book_id,)).fetchone():
            raise HTTPException(409, "提取执行中，暂不能整理资料")
        results = load_results(book_db, book_id)
        if not results:
            raise HTTPException(422, "没有可整理的章节提取结果")
        previous = [dict(row) for row in conn.execute("SELECT * FROM knowledge_entities WHERE book_id=?", (book_id,))]
        decisions = [dict(row) for row in conn.execute(
            "SELECT * FROM entity_resolutions WHERE book_id=? AND status='active' ORDER BY created_at,id", (book_id,),
        )]
        summaries, invalid = project(results, previous, decisions)
        persist(conn, book_id, summaries, invalid)
        db.execute("UPDATE books SET knowledge_revision=knowledge_revision+1 WHERE book_id=?", (book_id,))
    return service.summaries(user_id, book_id)


def persist(conn, book_id, summaries, invalid):
    stamp = now()
    conn.execute("DELETE FROM knowledge_entities WHERE book_id=?", (book_id,))
    for kind, entries in summaries.items():
        for entry in entries:
            conn.execute(
                "INSERT INTO knowledge_entities(id,book_id,kind,name,source_ids,content) VALUES(?,?,?,?,?,?)",
                (entry["entity_id"], book_id, kind, entry["name"], json.dumps(entry["source_ids"]),
                 json.dumps(entry, ensure_ascii=False)),
            )
        conn.execute(
            "INSERT INTO summaries(id,book_id,type,content,created_at,updated_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(book_id,type) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at",
            (identifier("summary"), book_id, kind, json.dumps(entries, ensure_ascii=False), stamp, stamp),
        )
    events = summaries.get("storyline_events", [])
    storylines = build_storylines(events)
    fingerprint = digest([event.get("source_ids", []) for event in events])
    conn.execute(
        "INSERT INTO storylines(id,book_id,content,input_fingerprint,status,error_message,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(book_id) DO UPDATE SET content=excluded.content,"
        "input_fingerprint=excluded.input_fingerprint,status=excluded.status,error_message=excluded.error_message,"
        "updated_at=excluded.updated_at",
        (identifier("storylines"), book_id, json.dumps(storylines, ensure_ascii=False), fingerprint,
         "ready", None, stamp, stamp),
    )
    for decision_id in invalid:
        conn.execute("UPDATE entity_resolutions SET status='pending' WHERE id=?", (decision_id,))


def resolve(db, user_id, book_id, payload):
    from .service import DocumentService

    DocumentService(db).owned_record(user_id, book_id)
    book_db = db.book_database(book_id)
    with book_db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        book = db.one("SELECT knowledge_revision FROM books WHERE book_id=?", (book_id,))
        if book["knowledge_revision"] != payload.revision:
            raise HTTPException(409, "资料已更新，请刷新后重试")
        if conn.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('pending','running')", (book_id,)).fetchone():
            raise HTTPException(409, "提取执行中，暂不能修改归并决定")
        results = [(dict(row), json.loads(row["payload"])) for row in conn.execute(
            "SELECT c.*,e.content AS payload FROM extractions e JOIN chapters c ON c.id=e.chapter_id "
            "WHERE e.book_id=? ORDER BY c.chapter_no", (book_id,),
        )]
        facts = facts_for(results)
        chosen, other = set(payload.source_ids), set(payload.other_source_ids)
        if chosen & other or not (chosen | other) <= facts.keys():
            raise HTTPException(422, "来源记录无效或两组有交集")
        if len({facts[key]["kind"] for key in chosen | other}) != 1:
            raise HTTPException(422, "不能归并不同类别的资料")
        previous = [dict(row) for row in conn.execute("SELECT * FROM knowledge_entities WHERE book_id=?", (book_id,))]
        if payload.action == "split":
            existing = next((set(json.loads(row["source_ids"])) for row in previous
                             if chosen < set(json.loads(row["source_ids"]))), None)
            if not existing:
                raise HTTPException(422, "拆分必须选择某个实体的部分来源")
            other = existing - chosen
        elif len(chosen | other) < 2:
            raise HTTPException(422, "合并至少需要两条来源记录")
        # A split replaces only merges crossing its new boundary. Unrelated
        # earlier split boundaries must survive a later merge with a third entity.
        for row in conn.execute("SELECT * FROM entity_resolutions WHERE book_id=? AND status='active'", (book_id,)):
            old_sources = set(json.loads(row["source_ids"])) | set(json.loads(row["other_source_ids"]))
            if payload.action == "split" and row["action"] == "merge" and old_sources & chosen and old_sources & other:
                conn.execute("UPDATE entity_resolutions SET status='superseded' WHERE id=?", (row["id"],))
        conn.execute(
            "INSERT INTO entity_resolutions(id,book_id,action,source_ids,other_source_ids,created_at) VALUES(?,?,?,?,?,?)",
            (identifier("resolution"), book_id, payload.action, json.dumps(sorted(chosen)), json.dumps(sorted(other)), now()),
        )
        decisions = [dict(row) for row in conn.execute(
            "SELECT * FROM entity_resolutions WHERE book_id=? AND status='active' ORDER BY created_at,id", (book_id,),
        )]
        summaries, invalid = project(results, previous, decisions)
        persist(conn, book_id, summaries, invalid)
        db.execute("UPDATE books SET knowledge_revision=knowledge_revision+1 WHERE book_id=?", (book_id,))
    return DocumentService(db).summaries(user_id, book_id)


def dismiss_resolution(db, user_id, book_id, resolution_id, revision):
    from .service import DocumentService

    DocumentService(db).owned_record(user_id, book_id)
    book_db = db.book_database(book_id)
    with book_db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if db.one("SELECT knowledge_revision FROM books WHERE book_id=?", (book_id,))["knowledge_revision"] != revision:
            raise HTTPException(409, "资料已更新，请刷新后重试")
        if conn.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('pending','running')", (book_id,)).fetchone():
            raise HTTPException(409, "提取执行中，暂不能修改归并决定")
        row = conn.execute("UPDATE entity_resolutions SET status='dismissed' WHERE id=? AND book_id=? AND status='pending'",
                           (resolution_id, book_id))
        if not row.rowcount:
            raise HTTPException(404, "待确认归并不存在")
        db.execute("UPDATE books SET knowledge_revision=knowledge_revision+1 WHERE book_id=?", (book_id,))
    return {"ok": True}
