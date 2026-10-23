"""Incremental extraction worker. Checkpoints never mutate published knowledge."""

import json

from fastapi import HTTPException

from backend.app.ai.agents.extraction import AgentAction, ExtractionAgent
from backend.app.ai.extraction_pipeline import (
    Synthesis, combine, digest, extract_inputs, model_fingerprint, request_json, segments,
)
from backend.app.ai.prompts.extraction import KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT
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
        self.db = db if hasattr(db, "parent") else db.book_database(book["book_id"])
        self.book, self.task_id, self.settings = book, task_id, settings
        self.task = self.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        self.request = json.loads(self.task["request_json"])
        self.config_hash = model_fingerprint(settings)
        self.lineage = []
        parent = self.task.get("parent_task_id")
        while parent:
            self.lineage.append(parent)
            row = self.db.one("SELECT parent_task_id FROM tasks WHERE id=?", (parent,))
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

    def extraction_action(self, part, label, percent):
        def split():
            middle = len(part["text"]) // 2
            boundary = part["text"].rfind("\n", middle // 2, middle + 1)
            if boundary >= 0:
                middle = boundary + 1
            children = []
            for start, end in ((0, middle), (middle, len(part["text"]))):
                child = {
                    **part, "start": part["start"] + start, "end": part["start"] + end,
                    "text": part["text"][start:end],
                    "segment_id": f"{part['chapter_id']}:{part['start'] + start}:{part['start'] + end}",
                }
                children.append(self.extraction_action(child, label, percent))
            return children

        return AgentAction(
            kind="extract", key=part["segment_id"], fingerprint=digest([self.config_hash, part]),
            label=label, execute=lambda: extract_inputs(self.settings, [part], self.check),
            chapter_id=part["chapter_id"], force=self.request.get("force", False),
            percent=percent, split=split if len(part["text"]) > 1000 else None,
            input_size=len(part["text"]),
        )

    def synthesize(self, entity, agent, percent):
        batches, batch = [], []
        for fact in entity["evidence"]:
            candidate = batch + [fact]
            if batch and len(json.dumps(candidate, ensure_ascii=False)) > 12000:
                batches.append(batch)
                batch = []
            batch.append(fact)
        if batch:
            batches.append(batch)
        actions = []
        for index, facts in enumerate(batches):
            allowed = {fact["fact_id"] for fact in facts}

            def validate(value, allowed=allowed):
                parsed = Synthesis.model_validate(value).model_dump()
                if not parsed["paragraphs"] or any(not set(p["fact_ids"]) <= allowed for p in parsed["paragraphs"]):
                    raise ValueError("综合档案必须引用本批次已有事实 ID")
                return parsed

            fingerprint = digest([self.config_hash, KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT, entity["kind"], facts])
            actions.append(AgentAction(
                kind="synthesis", key=f"{entity['entity_id']}:{index}", fingerprint=fingerprint,
                label=f"资料综合：{entity['name']} · {index + 1}/{len(batches)}",
                execute=lambda facts=facts, validate=validate: request_json(
                    self.settings, [
                        {"role": "system", "content": KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
                    ], validate, self.check,
                ), percent=percent, input_size=len(json.dumps(facts, ensure_ascii=False)),
            ))
        values = agent.run(actions, "synthesis")
        complete = all(value is not None for value in values)
        paragraphs = [paragraph for value in values if value is not None for paragraph in value["paragraphs"]]
        if complete and len(batches) > 1:
            allowed = set(entity["source_ids"])
            compact = [{"fact_id": p["fact_ids"][0], "fact_ids": p["fact_ids"], "summary": p["text"]}
                       for p in paragraphs]
            action = AgentAction(
                kind="synthesis", key=f"{entity['entity_id']}:overview",
                fingerprint=digest([self.config_hash, KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT, compact]),
                label=f"整合档案：{entity['name']}",
                execute=lambda: request_json(self.settings, [
                    {"role": "system", "content": KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
                ], lambda value: validate(value, allowed), self.check), percent=percent,
                input_size=len(json.dumps(compact, ensure_ascii=False)),
            )
            overview = agent.run([action], "synthesis")[0]
            complete = overview is not None
            paragraphs = overview["paragraphs"] if complete else []
        entity.update(synthesis=paragraphs if complete else [],
                      synthesis_status="ready" if complete else "pending", synthesis_model=self.config_hash,
                      synthesis_version=digest(KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT))

    def run(self, chapters):
        from backend.app.ai.harness.extraction import run_extraction
        return run_extraction(self, chapters)

    def prepare_graph(self, chapters):
        selected = select_chapters(chapters, self.request)
        scope_hash = input_fingerprint(selected)
        self.db.execute("UPDATE tasks SET input_fingerprint=? WHERE id=?", (scope_hash, self.task_id))
        return {"selected": selected, "scope_hash": scope_hash}

    def extract_graph(self, state):
        selected = state["selected"]
        chunks = [(chapter, part) for chapter in selected for part in segments(chapter)]
        by_chapter = {chapter["id"]: [] for chapter in selected}
        agent = ExtractionAgent(self)
        extraction_actions = [
            self.extraction_action(
                part, f"提取第 {chapter['chapter_no']} 章 · 分段 {index + 1}/{len(chunks)}",
                10 + int(index / max(len(chunks), 1) * 55),
            )
            for index, (chapter, part) in enumerate(chunks)
        ]
        extracted = agent.run(extraction_actions, "extract")
        for action, payload in zip(extraction_actions, extracted):
            if payload is not None:
                by_chapter[action.chapter_id].append(payload)
        return {"by_chapter": by_chapter}

    def lookup_graph(self, state):
        selected, scope_hash, by_chapter = state["selected"], state["scope_hash"], state["by_chapter"]
        agent = ExtractionAgent(self)
        staged = {}
        for chapter in selected:
            # Publish only complete chapters, retaining older complete results
            # when any segment of a long chapter is unavailable.
            expected = len(segments(chapter))
            if len(by_chapter[chapter["id"]]) != expected:
                self.log("warning", f"第 {chapter['chapter_no']} 章分段未全部完成，保留上一版本")
                continue
            payload = combine(by_chapter[chapter["id"]])
            questions = payload["questions"]
            seen = {part["segment_id"] for part in segments(chapter)}
            for round_no in range(2):
                if not questions:
                    break
                inputs = lookup_segments(selected, chapter, questions, seen)
                if not inputs:
                    break
                action = AgentAction(
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
                supplement = agent.run([action], "lookup")[0]
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
        if not staged:
            raise RuntimeError("本轮没有完整提取成功的章节，已保留检查点和上一版本，请续跑")
        return {"staged": staged}

    def merge_graph(self, state):
        staged = state["staged"]
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
        return {"results": results, "summaries": summaries, "invalid": invalid}

    def synthesis_graph(self, state):
        summaries = state["summaries"]
        agent = ExtractionAgent(self)
        entities = [entity for kind in ("characters", "items", "world_locations") for entity in summaries[kind]
                    if any(fact.get("sources") for fact in entity["evidence"])]
        for index, entity in enumerate(entities):
            if (entity["synthesis_status"] != "ready" or entity.get("synthesis_model") != self.config_hash
                    or entity.get("synthesis_version") != digest(KNOWLEDGE_SYNTHESIS_SYSTEM_PROMPT)):
                self.synthesize(entity, agent, 75 + int(index / max(len(entities), 1) * 20))
        return {"summaries": summaries}

    def publish_graph(self, state):
        staged, summaries, invalid = state["staged"], state["summaries"], state["invalid"]
        results, chapters = state["results"], state["chapters"]
        self.step("publish", "正在原子发布资料", 98)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = conn.execute("SELECT cancel_requested,status FROM tasks WHERE id=?", (self.task_id,)).fetchone()
            if task["cancel_requested"] or task["status"] != "running":
                raise Cancelled()
            revision = self.db.parent.one(
                "SELECT knowledge_revision FROM books WHERE book_id=?",
                (self.book["book_id"],),
            )["knowledge_revision"]
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
            knowledge.persist(conn, self.book["book_id"], summaries, invalid, self.task_id)
            status = "completed_with_warnings" if self.failures else "completed"
            message = f"提取完成，累计覆盖 {len(results)}/{len(chapters)} 章"
            if self.failures:
                message += f"，{len(self.failures)} 个动作待续跑"
            error_message = self.failures[0]["error_message"] if self.failures else None
            conn.execute("UPDATE tasks SET status=?,stage='completed',progress=100,current_step=?,error_message=?,updated_at=? WHERE id=?",
                         (status, message, error_message, now(), self.task_id))
            conn.execute("INSERT INTO task_logs VALUES(?,?,?,?,?)",
                         (identifier("log"), self.task_id, "info", message, now()))
        self.db.parent.execute(
            "UPDATE books SET knowledge_revision=knowledge_revision+1 WHERE book_id=?",
            (self.book["book_id"],),
        )
        self.db.parent.execute(
            "UPDATE books SET status='parsed',progress=100,err_message=NULL,updated_at=? WHERE book_id=?",
            (now(), self.book["book_id"]),
        )
        return {"published": True}
