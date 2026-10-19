"""Deterministic fact projections and persistent human identity decisions."""

import json

from fastapi import HTTPException

from backend.app.ai.extraction_pipeline import KINDS, digest
from backend.app.db.database import identifier, now


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
                sources = fact.get("sources", [])
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
        identities = {facts[key].get("identity") for key in a_ids | b_ids if facts[key].get("identity")}
        if not manual and facts[left]["kind"] == "characters" and len(identities) > 1:
            return
        parent[b] = a
        members[a].update(members.pop(b))

    by_name = {}
    for key, fact in facts.items():
        by_name.setdefault((fact["kind"], fact["name"]), []).append(key)
    for (kind, name), ids in by_name.items():
        for index, left_id in enumerate(ids):
            left = facts[left_id]
            for right_id in ids[index + 1:]:
                right = facts[right_id]
                same_quote = bool({digest(s) for s in left["sources"]} & {digest(s) for s in right["sources"]})
                same_identity = bool(left.get("identity") and left.get("identity") == right.get("identity"))
                conflicting = bool(left.get("identity") and right.get("identity")
                                   and left["identity"] != right["identity"])
                if not conflicting and (same_quote or (same_identity and kind == "characters")):
                    union(left_id, right_id)
    for key, fact in facts.items():
        if fact["kind"] != "characters":
            continue
        for alias in fact.get("aliases", []):
            if any(fact["name"] in s["quote"] and alias in s["quote"] for s in fact["sources"]):
                for other in by_name.get(("characters", alias), []):
                    if not (fact.get("identity") and facts[other].get("identity")
                            and fact["identity"] != facts[other]["identity"]):
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
        group.sort(key=lambda f: (f["chapter_no"], f["sources"][0]["start"] if f["sources"] else 0, f["fact_id"]))
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
            "aliases": sorted({a for fact in group for a in fact.get("aliases", [])}),
            "needs_review": False,
        }
        for fact in group:
            for field in ("summary", "description", "identity", "appearance", "personality"):
                if fact.get(field) and not entry.get(field):
                    entry[field] = fact[field]
        entry["facts_fingerprint"] = digest(group)
        if matches and matches[0][2].get("facts_fingerprint") == entry["facts_fingerprint"]:
            entry["synthesis"] = matches[0][2].get("synthesis", [])
            entry["synthesis_status"] = matches[0][2].get("synthesis_status", "pending")
            entry["synthesis_model"] = matches[0][2].get("synthesis_model")
        output[entry["kind"]].append(entry)
    for entries in output.values():
        for entry in entries:
            entry["needs_review"] = any(
                other["entity_id"] != entry["entity_id"]
                and ({entry["name"], *entry["aliases"]} & {other["name"], *other["aliases"]})
                and not any(
                    (set(entry["source_ids"]) & left and set(other["source_ids"]) & right)
                    or (set(entry["source_ids"]) & right and set(other["source_ids"]) & left)
                    for left, right in barriers
                )
                for other in entries
            )
    return output, invalid


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
    for decision_id in invalid:
        conn.execute("UPDATE entity_resolutions SET status='pending' WHERE id=?", (decision_id,))
    conn.execute("UPDATE books SET knowledge_revision=knowledge_revision+1 WHERE book_id=?", (book_id,))


def resolve(db, user_id, book_id, payload):
    from .service import DocumentService

    DocumentService(db).owned_record(user_id, book_id)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        book = conn.execute("SELECT knowledge_revision FROM books WHERE book_id=?", (book_id,)).fetchone()
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
    return DocumentService(db).summaries(user_id, book_id)


def dismiss_resolution(db, user_id, book_id, resolution_id, revision):
    from .service import DocumentService

    DocumentService(db).owned_record(user_id, book_id)
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT knowledge_revision FROM books WHERE book_id=?", (book_id,)).fetchone()[0] != revision:
            raise HTTPException(409, "资料已更新，请刷新后重试")
        if conn.execute("SELECT 1 FROM tasks WHERE book_id=? AND status IN ('pending','running')", (book_id,)).fetchone():
            raise HTTPException(409, "提取执行中，暂不能修改归并决定")
        row = conn.execute("UPDATE entity_resolutions SET status='dismissed' WHERE id=? AND book_id=? AND status='pending'",
                           (resolution_id, book_id))
        if not row.rowcount:
            raise HTTPException(404, "待确认归并不存在")
        conn.execute("UPDATE books SET knowledge_revision=knowledge_revision+1 WHERE book_id=?", (book_id,))
    return {"ok": True}
