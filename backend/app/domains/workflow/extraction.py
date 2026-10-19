"""Incremental extraction worker. Checkpoints never mutate published knowledge."""

import json

from fastapi import HTTPException

from backend.app.ai.agents.extraction import AgentAction, ExtractionAgent
from backend.app.ai.extraction_pipeline import (
    Synthesis, combine, digest, extract_inputs, model_fingerprint, request_json, segments,
)
from backend.app.ai.prompts.extraction import CHARACTER_SYNTHESIS_SYSTEM_PROMPT
from backend.app.db.database import identifier, now
from backend.app.domains.documents import knowledge
from backend.app.domains.workflow import failures


class Cancelled(Exception):
    pass


def select_chapters(chapters, request):
    start = request.get("chapter_start") or 1
    end = request.get("chapter_end") or request.get("max_chapters") or len(chapters)
    if not chapters or start < 1 or end > len(chapters) or start > end:
        raise HTTPException(422, "提取范围超出已有章节")
    return chapters[start - 1:end]


def input_fingerprint(chapters):
    return digest([(c["id"], c["title"], c["content"]) for c in chapters])


def lookup_segments(chapters, chapter, questions, seen):
    candidates = []
    for candidate in chapters:
        for question in questions:
            for term in (question["query"], question["subject"]):
                if not term.strip():
                    continue
                pos = candidate["content"].find(term)
                if pos >= 0:
                    candidates.append((0, candidate, max(0, pos - 500)))
        if abs(candidate["chapter_no"] - chapter["chapter_no"]) == 1:
            candidates.append((1, candidate, 0 if candidate["chapter_no"] > chapter["chapter_no"]
                               else max(0, len(candidate["content"]) - 2000)))
    output = []
    for _, candidate, start in sorted(candidates, key=lambda c: (c[0], c[1]["chapter_no"], c[2])):
        end = min(start + 2000, len(candidate["content"]))
        segment_id = f"{candidate['id']}:{start}:{end}"
        if segment_id in seen:
            continue
        seen.add(segment_id)
        output.append({
            "segment_id": segment_id, "book_id": candidate["book_id"], "chapter_id": candidate["id"],
            "chapter_no": candidate["chapter_no"], "chapter_title": candidate["title"],
            "start": start, "end": end, "text": candidate["content"][start:end],
        })
        if len(output) == 3:
            break
    return output


class ExtractionWorker:
    cancelled_error = Cancelled

    def __init__(self, db, book, task_id, settings):
        self.db, self.book, self.task_id, self.settings = db, book, task_id, settings
        self.task = db.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        self.request = json.loads(self.task["request_json"])
        self.config_hash = model_fingerprint(settings)
        self.lineage = []
        parent = self.task.get("parent_task_id")
        while parent:
            self.lineage.append(parent)
            row = db.one("SELECT parent_task_id FROM tasks WHERE id=?", (parent,))
            parent = row["parent_task_id"] if row else None
        # Units that were given up on for this task. They never abort the run;
        # they are reported on publish and re-executed by the next attempt
        # because ``unit`` only reuses completed/reused checkpoints.
        self.failures = []

    def check(self):
        task = self.db.one("SELECT cancel_requested,status FROM tasks WHERE id=?", (self.task_id,))
        if not task or task["cancel_requested"] or task["status"] not in {"pending", "running"}:
            raise Cancelled()

    def step(self, stage, label, percent):
        from .tasks import progress
        self.check()
        self.db.execute("UPDATE tasks SET stage=? WHERE id=?", (stage, self.task_id))
        progress(self.db, self.task_id, self.book["book_id"], percent, label)

    def unit(self, kind, key, fingerprint, fn, chapter_id=None, force=False):
        self.check()
        cache = self.db.all(
            "SELECT * FROM extraction_units WHERE book_id=? AND kind=? AND unit_key=? "
            "AND fingerprint=? AND status IN ('completed','reused') ORDER BY updated_at DESC",
            (self.book["book_id"], kind, key, fingerprint),
        )
        cached = next((row for row in cache if not force or row["task_id"] in self.lineage), None)
        unit_id, stamp = identifier("unit"), now()
        self.db.execute(
            "INSERT INTO extraction_units(id,task_id,book_id,chapter_id,kind,unit_key,fingerprint,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (unit_id, self.task_id, self.book["book_id"], chapter_id, kind, key, fingerprint, "running", stamp, stamp),
        )
        try:
            payload = json.loads(cached["payload"]) if cached else fn()
            self.db.execute(
                "UPDATE extraction_units SET status=?,payload=?,updated_at=? WHERE id=?",
                ("reused" if cached else "completed", json.dumps(payload, ensure_ascii=False), now(), unit_id),
            )
            if cached:
                self.db.execute("UPDATE tasks SET reused_units=reused_units+1 WHERE id=?", (self.task_id,))
            self.check()
            return payload
        except Exception as exc:
            cancelled = isinstance(exc, Cancelled)
            self.db.execute(
                "UPDATE extraction_units SET status=?,error_message=?,updated_at=? WHERE id=? AND status='running'",
                ("cancelled" if cancelled else "failed",
                 "" if cancelled else failures.label(exc)[:500], now(), unit_id),
            )
            raise

    def log(self, level, message):
        self.db.execute(
            "INSERT INTO task_logs VALUES(?,?,?,?,?)",
            (identifier("log"), self.task_id, level, message[:400], now()),
        )

    def mark_skipped(self, kind, unit_key):
        """Distinguish "gave up and continued" from "task died inside the unit"."""
        self.db.execute(
            "UPDATE extraction_units SET status='skipped',updated_at=? "
            "WHERE task_id=? AND kind=? AND unit_key=? AND status='failed'",
            (now(), self.task_id, kind, unit_key),
        )

    def record_failure(self, kind, unit_key, label, exc):
        self.failures.append({
            "kind": kind, "unit_key": unit_key, "label": label,
            "error_type": failures.classify(exc), "error_message": failures.describe(exc),
        })
        self.mark_skipped(kind, unit_key)
        self.log("warning", f"{label} 失败已跳过（{failures.PREFIXES[failures.classify(exc)]}）：{str(exc)[:200]}")

    def isolate(self, kind, key, fingerprint, fn, label, chapter_id=None, force=False):
        """Run one unit. A failure is recorded and skipped instead of aborting the task.

        ``Cancelled`` always propagates: user intent outranks isolation.
        """
        try:
            return self.unit(kind, key, fingerprint, fn, chapter_id, force), None
        except Cancelled:
            raise
        except Exception as exc:
            self.record_failure(kind, key, label, exc)
            return None, exc

    def synthesize(self, entity):
        batches, batch = [], []
        for fact in entity["evidence"]:
            candidate = batch + [fact]
            if batch and len(json.dumps(candidate, ensure_ascii=False)) > 12000:
                batches.append(batch)
                batch = []
            batch.append(fact)
        if batch:
            batches.append(batch)
        paragraphs = []
        for index, facts in enumerate(batches):
            allowed = {fact["fact_id"] for fact in facts}

            def validate(value):
                parsed = Synthesis.model_validate(value).model_dump()
                if not parsed["paragraphs"] or any(not set(p["fact_ids"]) <= allowed for p in parsed["paragraphs"]):
                    raise ValueError("综合档案必须引用本批次已有事实 ID")
                return parsed

            fingerprint = digest([self.config_hash, facts])
            value = self.unit("synthesis", f"{entity['entity_id']}:{index}", fingerprint, lambda: request_json(
                self.settings, [
                    {"role": "system", "content": CHARACTER_SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
                ], validate, self.check,
            ))
            paragraphs.extend(value["paragraphs"])
        entity.update(synthesis=paragraphs, synthesis_status="ready", synthesis_model=self.config_hash)

    def run(self, chapters):
        selected = select_chapters(chapters, self.request)
        scope_hash = input_fingerprint(selected)
        self.db.execute("UPDATE tasks SET input_fingerprint=? WHERE id=?", (scope_hash, self.task_id))
        chunks = [(chapter, part) for chapter in selected for part in segments(chapter)]
        by_chapter = {chapter["id"]: [] for chapter in selected}
        agent = ExtractionAgent(self)
        extraction_actions = [
            AgentAction(
                kind="extract",
                key=part["segment_id"],
                fingerprint=digest([self.config_hash, part]),
                label=f"提取第 {chapter['chapter_no']} 章 · 分段 {index + 1}/{len(chunks)}",
                execute=lambda part=part: extract_inputs(self.settings, [part], self.check),
                chapter_id=chapter["id"],
                force=self.request.get("force", False),
                percent=10 + int(index / max(len(chunks), 1) * 55),
            )
            for index, (chapter, part) in enumerate(chunks)
        ]
        extracted = agent.run(extraction_actions, "extract")
        for action, payload in zip(extraction_actions, extracted):
            if payload is not None:
                by_chapter[action.chapter_id].append(payload)
        staged = {}
        for chapter in selected:
            # A chapter with no successful segment is left out of ``staged`` so
            # an older published extraction cannot be erased by a failed retry.
            if not by_chapter[chapter["id"]]:
                self.log("warning", f"第 {chapter['chapter_no']} 章没有成功完成的提取分段，保留上一版本")
                continue
            payload = combine(by_chapter[chapter["id"]])
            questions = payload["questions"]
            seen = {part["segment_id"] for part in segments(chapter)}
            lookup_actions = []
            for round_no in range(2):
                if not questions:
                    break
                inputs = lookup_segments(selected, chapter, questions, seen)
                if not inputs:
                    break
                lookup_actions.append(
                    AgentAction(
                        kind="lookup",
                        key=f"{chapter['id']}:{round_no}",
                        fingerprint=digest([self.config_hash, scope_hash, inputs, questions]),
                        label=f"补查第 {chapter['chapter_no']} 章 · 第 {round_no + 1}/2 轮",
                        execute=lambda inputs=inputs, questions=questions: extract_inputs(
                            self.settings, inputs, self.check, questions
                        ),
                        chapter_id=chapter["id"],
                        force=self.request.get("force", False),
                        percent=67,
                    )
                )
                # The next question set depends on the previous answer, so the
                # agent executes lookup rounds one at a time below.
                supplement = agent.run([lookup_actions[-1]], "lookup")[0]
                if supplement is None:
                    break
                payload = combine([payload, supplement])
                questions = supplement["questions"]
            payload["questions"] = questions
            if questions:
                self.db.execute("INSERT INTO task_logs VALUES(?,?,?,?,?)", (
                    identifier("log"), self.task_id, "warning",
                    f"第 {chapter['chapter_no']} 章仍有 {len(questions)} 个待核实问题", now(),
                ))
            staged[chapter["id"]] = (chapter, payload)
        results = {chapter["id"]: (chapter, payload) for chapter, payload in knowledge.load_results(self.db, self.book["book_id"])}
        results.update(staged)
        results = sorted(results.values(), key=lambda pair: pair[0]["chapter_no"])
        self.step("merge", "正在归并全书已发布及本轮章节事实", 72)
        previous = self.db.all("SELECT * FROM knowledge_entities WHERE book_id=?", (self.book["book_id"],))
        decisions = self.db.all(
            "SELECT * FROM entity_resolutions WHERE book_id=? AND status='active' ORDER BY created_at,id",
            (self.book["book_id"],),
        )
        summaries, invalid = knowledge.project(results, previous, decisions)
        people = summaries["characters"]
        for index, entity in enumerate(people):
            self.step("synthesis", f"人物综合 {index + 1}/{len(people)}：{entity['name']}",
                      75 + int(index / max(len(people), 1) * 20))
            if entity["synthesis_status"] != "ready" or entity.get("synthesis_model") != self.config_hash:
                try:
                    self.synthesize(entity)
                except Cancelled:
                    raise
                except Exception as exc:
                    if not failures.is_recoverable(exc):
                        raise
                    self.record_failure("synthesis", entity["entity_id"], f"人物综合：{entity['name']}", exc)
                    entity.update(synthesis=[], synthesis_status="pending", synthesis_model=self.config_hash)
        self.step("publish", "正在原子发布资料", 98)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute("SELECT cancel_requested,status FROM tasks WHERE id=?", (self.task_id,)).fetchone()
            if task["cancel_requested"] or task["status"] != "running":
                raise Cancelled()
            revision = conn.execute("SELECT knowledge_revision FROM books WHERE book_id=?", (self.book["book_id"],)).fetchone()[0]
            if revision != self.book["knowledge_revision"]:
                raise RuntimeError("资料版本已改变，请重新提取")
            for chapter, payload in staged.values():
                conn.execute(
                    "INSERT INTO extractions(id,book_id,chapter_id,content,model_name,created_at) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(book_id,chapter_id) DO UPDATE SET content=excluded.content,"
                    "model_name=excluded.model_name,created_at=excluded.created_at",
                    (identifier("extraction"), self.book["book_id"], chapter["id"],
                     json.dumps(payload, ensure_ascii=False), self.settings["model"], now()),
                )
            knowledge.persist(conn, self.book["book_id"], summaries, invalid)
            status = "completed_with_warnings" if self.failures else "completed"
            message = f"提取完成，累计覆盖 {len(results)}/{len(chapters)} 章"
            if self.failures:
                message += f"，{len(self.failures)} 个动作待续跑"
            conn.execute("UPDATE tasks SET status=?,stage='completed',progress=100,current_step=?,error_message=?,updated_at=? WHERE id=?",
                         (status, message, message if self.failures else None, now(), self.task_id))
            conn.execute("UPDATE books SET status='parsed',progress=100,err_message=NULL,updated_at=? WHERE book_id=?",
                         (now(), self.book["book_id"]))
            conn.execute("INSERT INTO task_logs VALUES(?,?,?,?,?)",
                         (identifier("log"), self.task_id, "info", message, now()))
