from __future__ import annotations

import json
import sqlite3

from fastapi import HTTPException

from backend.app.db.database import identifier, now

from .repository import KnowledgeRepository
from .presentation import character_milestones


class KnowledgeService:
    def __init__(self, database):
        self.repo = KnowledgeRepository(database)

    def _book_db(self, user_id, book_id):
        if not self.repo.book(user_id, book_id):
            raise HTTPException(404, "书籍不存在")
        return self.repo.db(book_id)

    def _evidence(self, db, book_id, payload):
        if payload and not self.repo.valid_evidence(db, book_id, payload):
            raise HTTPException(422, "证据章节不存在")
        if not payload:
            return None
        evidence_id = identifier("evidence")
        db.execute(
            "INSERT INTO knowledge_evidence VALUES(?,?,?,?,?,?,?,?,?)",
            (evidence_id, book_id, payload.chapter_id, payload.chunk_id, payload.quote,
             payload.source_type, payload.start_offset, payload.end_offset, now()),
        )
        return evidence_id

    def characters(self, user_id, book_id):
        db = self._book_db(user_id, book_id)
        rows = db.all(
            "SELECT * FROM knowledge_characters WHERE book_id=? AND deleted_at IS NULL "
            "ORDER BY frequency DESC,updated_at DESC,canonical_name COLLATE NOCASE",
            (book_id,),
        )
        summaries = {}
        for entity in db.all(
            "SELECT name,content FROM knowledge_entities WHERE book_id=? AND kind='characters'",
            (book_id,),
        ):
            try:
                content = json.loads(entity["content"])
            except (TypeError, ValueError):
                continue
            summaries[entity["name"].casefold()] = content
        for row in rows:
            content = summaries.get(row["canonical_name"].casefold()) or {}
            row["synthesis"] = content.get("synthesis") or []
            row["synthesis_status"] = content.get("synthesis_status") or "pending"
            row["first_chapter"] = content.get("first_chapter") or content.get("chapter_no")
            row["last_chapter"] = content.get("last_chapter")
            row["milestones"] = character_milestones(content)
        return rows

    def synthesize_character(self, user_id, book_id, character_id, profile_id=None):
        from .synthesis import synthesize_character

        self._book_db(user_id, book_id)
        return synthesize_character(self.repo.database, user_id, book_id, character_id, profile_id)

    def create_character(self, user_id, book_id, payload):
        db = self._book_db(user_id, book_id)
        character_id, stamp = identifier("character"), now()
        try:
            db.execute(
                "INSERT INTO knowledge_characters VALUES(?,?,?,?,?,?,?,?,?,?)",
                (character_id, book_id, payload.name.strip(), json.dumps(payload.aliases, ensure_ascii=False),
                 0, "active", None, None, stamp, stamp),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "该书籍已存在同名人物") from exc
        row = db.one("SELECT * FROM knowledge_characters WHERE id=?", (character_id,))
        self.repo.record_change(db, book_id, "character", character_id, "create", None, row, "", user_id)
        return row

    def update_character(self, user_id, book_id, character_id, payload):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL", (character_id, book_id))
        if not before:
            raise HTTPException(404, "人物不存在")
        name = payload.name if payload.name is not None else before["canonical_name"]
        aliases = payload.aliases if payload.aliases is not None else json.loads(before["aliases_json"])
        state = payload.state or before["state"]
        try:
            db.execute(
                "UPDATE knowledge_characters SET canonical_name=?,aliases_json=?,state=?,updated_at=? WHERE id=?",
                (name.strip(), json.dumps(aliases, ensure_ascii=False), state, now(), character_id),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "该书籍已存在同名人物") from exc
        after = db.one("SELECT * FROM knowledge_characters WHERE id=?", (character_id,))
        self.repo.record_change(db, book_id, "character", character_id, "update", before, after, payload.reason, user_id)
        return after

    def delete_character(self, user_id, book_id, character_id, reason):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL", (character_id, book_id))
        if not before:
            raise HTTPException(404, "人物不存在")
        stamp = now()
        db.execute("UPDATE knowledge_characters SET deleted_at=?,state='rejected',updated_at=? WHERE id=?", (stamp, stamp, character_id))
        after = db.one("SELECT * FROM knowledge_characters WHERE id=?", (character_id,))
        self.repo.record_change(db, book_id, "character", character_id, "delete", before, after, reason, user_id)
        return after

    def restore_character(self, user_id, book_id, character_id):
        db = self._book_db(user_id, book_id)
        row = db.one("SELECT * FROM knowledge_characters WHERE id=? AND book_id=?", (character_id, book_id))
        if not row:
            raise HTTPException(404, "人物不存在")
        db.execute("UPDATE knowledge_characters SET deleted_at=NULL,state='active',updated_at=? WHERE id=?", (now(), character_id))
        return db.one("SELECT * FROM knowledge_characters WHERE id=?", (character_id,))

    def facts(self, user_id, book_id, character_id):
        db = self._book_db(user_id, book_id)
        if not db.one("SELECT id FROM knowledge_characters WHERE id=? AND book_id=?", (character_id, book_id)):
            raise HTTPException(404, "人物不存在")
        return db.all(
            "SELECT f.*,e.quote,e.chapter_id FROM knowledge_facts f LEFT JOIN knowledge_evidence e ON e.id=f.evidence_id "
            "WHERE f.book_id=? AND f.entity_id=? AND f.deleted_at IS NULL ORDER BY f.fact_type,f.version",
            (book_id, character_id),
        )

    def create_fact(self, user_id, book_id, payload):
        db = self._book_db(user_id, book_id)
        if not db.one("SELECT id FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL", (payload.character_id, book_id)):
            raise HTTPException(404, "人物不存在")
        evidence_id = self._evidence(db, book_id, payload.evidence)
        fact_id, stamp = identifier("fact"), now()
        db.execute(
            "INSERT INTO knowledge_facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fact_id, book_id, "character", payload.character_id, payload.fact_type,
             json.dumps(payload.value, ensure_ascii=False), "active", 1, None, evidence_id,
             payload.source_type, int(payload.locked_by_user), None, stamp, stamp),
        )
        row = db.one("SELECT * FROM knowledge_facts WHERE id=?", (fact_id,))
        self.repo.record_change(db, book_id, "fact", fact_id, "create", None, row, "", user_id)
        return row

    def update_fact(self, user_id, book_id, fact_id, payload):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_facts WHERE id=? AND book_id=? AND deleted_at IS NULL", (fact_id, book_id))
        if not before:
            raise HTTPException(404, "事实不存在")
        if before["locked_by_user"] and payload.reason == "":
            raise HTTPException(409, "该事实已被人工锁定，请提供修订原因")
        evidence_id = self._evidence(db, book_id, payload.evidence) or before["evidence_id"]
        new_id, stamp = identifier("fact"), now()
        db.execute("UPDATE knowledge_facts SET state='superseded',updated_at=? WHERE id=?", (stamp, fact_id))
        db.execute(
            "INSERT INTO knowledge_facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_id, book_id, before["entity_type"], before["entity_id"], before["fact_type"],
             json.dumps(payload.value, ensure_ascii=False), "active", before["version"] + 1, fact_id,
             evidence_id, "user", int(payload.locked_by_user if payload.locked_by_user is not None else before["locked_by_user"]),
             None, stamp, stamp),
        )
        after = db.one("SELECT * FROM knowledge_facts WHERE id=?", (new_id,))
        self.repo.record_change(db, book_id, "fact", new_id, "update", before, after, payload.reason, user_id)
        return after

    def delete_fact(self, user_id, book_id, fact_id, reason):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_facts WHERE id=? AND book_id=? AND deleted_at IS NULL", (fact_id, book_id))
        if not before:
            raise HTTPException(404, "事实不存在")
        stamp = now()
        db.execute("UPDATE knowledge_facts SET deleted_at=?,state='deleted',updated_at=? WHERE id=?", (stamp, stamp, fact_id))
        return db.one("SELECT * FROM knowledge_facts WHERE id=?", (fact_id,))

    def clues(self, user_id, book_id):
        return self._book_db(user_id, book_id).all(
            "SELECT c.*,e.quote,e.chapter_id,e.start_offset,e.end_offset "
            "FROM knowledge_clues c LEFT JOIN knowledge_evidence e ON e.id=c.evidence_id "
            "WHERE c.book_id=? AND c.deleted_at IS NULL ORDER BY c.first_chapter_no,c.created_at",
            (book_id,),
        )

    def create_clue(self, user_id, book_id, payload):
        db = self._book_db(user_id, book_id)
        evidence_id = self._evidence(db, book_id, payload.evidence)
        clue_id, stamp = identifier("clue"), now()
        db.execute(
            "INSERT INTO knowledge_clues VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (clue_id, book_id, payload.title, payload.original_text, payload.possible_meaning,
             payload.first_chapter_no, payload.state, payload.confidence, evidence_id, None, stamp, stamp),
        )
        row = db.one("SELECT * FROM knowledge_clues WHERE id=?", (clue_id,))
        self.repo.record_change(db, book_id, "clue", clue_id, "create", None, row, "", user_id)
        return row

    def update_clue(self, user_id, book_id, clue_id, payload):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_clues WHERE id=? AND book_id=? AND deleted_at IS NULL", (clue_id, book_id))
        if not before:
            raise HTTPException(404, "线索不存在")
        evidence_id = self._evidence(db, book_id, payload.evidence) or before["evidence_id"]
        db.execute(
            "UPDATE knowledge_clues SET title=?,original_text=?,possible_meaning=?,first_chapter_no=?,state=?,confidence=?,evidence_id=?,updated_at=? WHERE id=?",
            (payload.title, payload.original_text, payload.possible_meaning, payload.first_chapter_no,
             payload.state, payload.confidence, evidence_id, now(), clue_id),
        )
        after = db.one("SELECT * FROM knowledge_clues WHERE id=?", (clue_id,))
        self.repo.record_change(db, book_id, "clue", clue_id, "update", before, after, payload.reason, user_id)
        return after

    def delete_clue(self, user_id, book_id, clue_id, reason):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_clues WHERE id=? AND book_id=? AND deleted_at IS NULL", (clue_id, book_id))
        if not before:
            raise HTTPException(404, "线索不存在")
        stamp = now()
        db.execute("UPDATE knowledge_clues SET deleted_at=?,state='rejected',updated_at=? WHERE id=?", (stamp, stamp, clue_id))
        after = db.one("SELECT * FROM knowledge_clues WHERE id=?", (clue_id,))
        self.repo.record_change(db, book_id, "clue", clue_id, "delete", before, after, reason, user_id)
        return after

    def verify_clue(self, user_id, book_id, clue_id, reason):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_clues WHERE id=? AND book_id=? AND deleted_at IS NULL", (clue_id, book_id))
        if not before:
            raise HTTPException(404, "线索不存在")
        if before["state"] not in {"candidate", "open", "hypothesis", "partially_revealed"}:
            raise HTTPException(409, "当前线索状态不能验证")
        db.execute("UPDATE knowledge_clues SET state='revealed',updated_at=? WHERE id=?", (now(), clue_id))
        after = db.one("SELECT * FROM knowledge_clues WHERE id=?", (clue_id,))
        self.repo.record_change(db, book_id, "clue", clue_id, "verify", before, after, reason, user_id)
        return after

    def events(self, user_id, book_id):
        return self._book_db(user_id, book_id).all(
            "SELECT e.*,s.quote,s.chapter_id,s.start_offset,s.end_offset "
            "FROM knowledge_events e LEFT JOIN knowledge_evidence s ON s.id=e.evidence_id "
            "WHERE e.book_id=? AND e.deleted_at IS NULL ORDER BY e.chapter_no,e.sequence_no",
            (book_id,),
        )

    def create_event(self, user_id, book_id, payload):
        db = self._book_db(user_id, book_id)
        evidence_id = self._evidence(db, book_id, payload.evidence)
        event_id, stamp = identifier("event"), now()
        db.execute(
            "INSERT INTO knowledge_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, book_id, payload.title, payload.description, payload.story_time_start, payload.story_time_end,
             payload.chapter_no, payload.sequence_no, "active", evidence_id, None, stamp, stamp),
        )
        return db.one("SELECT * FROM knowledge_events WHERE id=?", (event_id,))

    def update_event(self, user_id, book_id, event_id, payload):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_events WHERE id=? AND book_id=? AND deleted_at IS NULL", (event_id, book_id))
        if not before:
            raise HTTPException(404, "事件不存在")
        evidence_id = self._evidence(db, book_id, payload.evidence) or before["evidence_id"]
        db.execute(
            "UPDATE knowledge_events SET title=?,description=?,story_time_start=?,story_time_end=?,chapter_no=?,sequence_no=?,evidence_id=?,updated_at=? WHERE id=?",
            (payload.title, payload.description, payload.story_time_start, payload.story_time_end, payload.chapter_no,
             payload.sequence_no, evidence_id, now(), event_id),
        )
        after = db.one("SELECT * FROM knowledge_events WHERE id=?", (event_id,))
        self.repo.record_change(db, book_id, "event", event_id, "update", before, after, payload.reason, user_id)
        return after

    def delete_event(self, user_id, book_id, event_id, reason):
        db = self._book_db(user_id, book_id)
        if not db.one("SELECT id FROM knowledge_events WHERE id=? AND book_id=? AND deleted_at IS NULL", (event_id, book_id)):
            raise HTTPException(404, "事件不存在")
        db.execute("UPDATE knowledge_events SET deleted_at=?,state='deleted',updated_at=? WHERE id=?", (now(), now(), event_id))
        return {"ok": True}

    def changes(self, user_id, book_id, limit=100):
        return self._book_db(user_id, book_id).all("SELECT * FROM knowledge_changes WHERE book_id=? ORDER BY created_at DESC LIMIT ?", (book_id, limit))

    def relations(self, user_id, book_id):
        return self._book_db(user_id, book_id).all(
            "SELECT r.*,e.quote,e.chapter_id,e.start_offset,e.end_offset "
            "FROM knowledge_relations r LEFT JOIN knowledge_evidence e ON e.id=r.evidence_id "
            "WHERE r.book_id=? AND r.deleted_at IS NULL ORDER BY r.created_at",
            (book_id,),
        )

    def create_relation(self, user_id, book_id, payload):
        db = self._book_db(user_id, book_id)
        evidence_id = self._evidence(db, book_id, payload.evidence)
        relation_id, stamp = identifier("relation"), now()
        db.execute(
            "INSERT INTO knowledge_relations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (relation_id, book_id, payload.subject_type, payload.subject_id, payload.relation_type,
             payload.object_type, payload.object_id, json.dumps(payload.value, ensure_ascii=False),
             "active", evidence_id, None, stamp, stamp),
        )
        return db.one("SELECT * FROM knowledge_relations WHERE id=?", (relation_id,))

    def update_relation(self, user_id, book_id, relation_id, payload):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_relations WHERE id=? AND book_id=? AND deleted_at IS NULL", (relation_id, book_id))
        if not before:
            raise HTTPException(404, "关系不存在")
        evidence_id = self._evidence(db, book_id, payload.evidence) or before["evidence_id"]
        db.execute(
            "UPDATE knowledge_relations SET subject_type=?,subject_id=?,relation_type=?,object_type=?,object_id=?,"
            "value_json=?,evidence_id=?,updated_at=? WHERE id=?",
            (payload.subject_type, payload.subject_id, payload.relation_type, payload.object_type,
             payload.object_id, json.dumps(payload.value, ensure_ascii=False), evidence_id, now(), relation_id),
        )
        after = db.one("SELECT * FROM knowledge_relations WHERE id=?", (relation_id,))
        self.repo.record_change(db, book_id, "relation", relation_id, "update", before, after, payload.reason, user_id)
        return after

    def delete_relation(self, user_id, book_id, relation_id, reason):
        db = self._book_db(user_id, book_id)
        before = db.one("SELECT * FROM knowledge_relations WHERE id=? AND book_id=? AND deleted_at IS NULL", (relation_id, book_id))
        if not before:
            raise HTTPException(404, "关系不存在")
        stamp = now()
        db.execute("UPDATE knowledge_relations SET deleted_at=?,state='deleted',updated_at=? WHERE id=?", (stamp, stamp, relation_id))
        after = db.one("SELECT * FROM knowledge_relations WHERE id=?", (relation_id,))
        self.repo.record_change(db, book_id, "relation", relation_id, "delete", before, after, reason, user_id)
        return after

    def merge_characters(self, user_id, book_id, source_id, target_id, reason):
        db = self._book_db(user_id, book_id)
        source = db.one("SELECT * FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL", (source_id, book_id))
        target = db.one("SELECT * FROM knowledge_characters WHERE id=? AND book_id=? AND deleted_at IS NULL", (target_id, book_id))
        if not source or not target or source_id == target_id:
            raise HTTPException(422, "合并人物无效")
        stamp, merge_id = now(), identifier("merge")
        db.execute("UPDATE knowledge_characters SET state='merged',merged_into_id=?,updated_at=? WHERE id=?", (target_id, stamp, source_id))
        db.execute("UPDATE knowledge_facts SET entity_id=? WHERE book_id=? AND entity_id=?", (target_id, book_id, source_id))
        db.execute("UPDATE knowledge_relations SET subject_id=? WHERE book_id=? AND subject_type='character' AND subject_id=?", (target_id, book_id, source_id))
        db.execute("UPDATE knowledge_relations SET object_id=? WHERE book_id=? AND object_type='character' AND object_id=?", (target_id, book_id, source_id))
        db.execute(
            "INSERT INTO knowledge_merges VALUES(?,?,?,?,?,?,?,?,?)",
            (merge_id, book_id, "character", source_id, target_id, reason, "user", stamp, None),
        )
        self.repo.record_change(db, book_id, "character", source_id, "merge", source, db.one("SELECT * FROM knowledge_characters WHERE id=?", (source_id,)), reason, user_id)
        return {"merge_id": merge_id, "source_id": source_id, "target_id": target_id}

    def unmerge_character(self, user_id, book_id, merge_id):
        db = self._book_db(user_id, book_id)
        merge = db.one("SELECT * FROM knowledge_merges WHERE id=? AND book_id=? AND undone_at IS NULL", (merge_id, book_id))
        if not merge:
            raise HTTPException(404, "合并记录不存在")
        db.execute("UPDATE knowledge_characters SET state='active',merged_into_id=NULL,updated_at=? WHERE id=?", (now(), merge["source_id"]))
        db.execute("UPDATE knowledge_merges SET undone_at=? WHERE id=?", (now(), merge_id))
        return db.one("SELECT * FROM knowledge_characters WHERE id=?", (merge["source_id"],))

    def reviews(self, user_id, book_id, state="pending"):
        return self._book_db(user_id, book_id).all(
            "SELECT * FROM knowledge_reviews WHERE book_id=? AND state=? ORDER BY created_at", (book_id, state),
        )

    def resolve_review(self, user_id, book_id, review_id, payload):
        db = self._book_db(user_id, book_id)
        review = db.one("SELECT * FROM knowledge_reviews WHERE id=? AND book_id=? AND state='pending'", (review_id, book_id))
        if not review:
            raise HTTPException(404, "审核项不存在")
        state = "approved" if payload.action in {"approve", "verify", "merge"} else "rejected"
        if payload.action == "verify":
            if review["entity_type"] != "clue":
                raise HTTPException(422, "只有伏笔可以验证")
            db.execute("UPDATE knowledge_clues SET state='revealed',updated_at=? WHERE id=?", (now(), review["entity_id"]))
        db.execute("UPDATE knowledge_reviews SET state=?,resolution_json=?,resolved_at=? WHERE id=?",
                   (state, json.dumps(payload.model_dump(), ensure_ascii=False), now(), review_id))
        return db.one("SELECT * FROM knowledge_reviews WHERE id=?", (review_id,))

    def rollback_batch(self, user_id, book_id, batch_id, reason):
        db = self._book_db(user_id, book_id)
        changes = db.all(
            "SELECT * FROM knowledge_changes WHERE book_id=? AND batch_id=? AND operator_type='agent' "
            "ORDER BY created_at DESC,id DESC", (book_id, batch_id),
        )
        if not changes:
            raise HTTPException(404, "提取批次没有可回滚的知识变更")
        tables = {
            "character": "knowledge_characters",
            "fact": "knowledge_facts",
            "event": "knowledge_events",
            "relation": "knowledge_relations",
            "clue": "knowledge_clues",
        }
        for change in changes:
            table = tables.get(change["entity_type"])
            if not table:
                continue
            current = db.one(f"SELECT * FROM {table} WHERE id=?", (change["entity_id"],))
            if not current:
                continue
            before = json.loads(change["before_json"]) if change["before_json"] else None
            if before and change["entity_type"] == "fact":
                db.execute("UPDATE knowledge_facts SET state='superseded',deleted_at=?,updated_at=? WHERE id=?",
                           (now(), now(), change["entity_id"]))
                if before.get("id"):
                    db.execute("UPDATE knowledge_facts SET state='active',deleted_at=NULL,updated_at=? WHERE id=?",
                               (now(), before["id"]))
            elif change["entity_type"] in {"character", "event", "relation", "clue"}:
                db.execute(f"UPDATE {table} SET deleted_at=?,state='rejected',updated_at=? WHERE id=?",
                           (now(), now(), change["entity_id"]))
            self.repo.record_change(
                db, book_id, change["entity_type"], change["entity_id"], "rollback",
                current, db.one(f"SELECT * FROM {table} WHERE id=?", (change["entity_id"],)), reason, user_id,
            )
        return {"batch_id": batch_id, "rolled_back": len(changes)}
