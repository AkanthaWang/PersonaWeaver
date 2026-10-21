"""One durable, idempotent generation lifecycle for JSON and SSE clients."""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field

from fastapi import HTTPException

from backend.app.ai.providers import conversation_stream as provider
from backend.app.db.database import identifier, now
from backend.app.domains.settings import llm

from . import budget, compaction
from .memory_context import effective_entries
from .mirror import sync_mirror
from .service import ConversationService, _conversation_lock

logger = logging.getLogger(__name__)


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def snapshot(settings):
    return {k: v for k, v in settings.items() if k not in {"api_key", "headers"}}


@dataclass
class LiveRun:
    conversation_id: str
    request_id: str
    events: list = field(default_factory=list)
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None
    terminal: bool = False
    cancel_reason: str = "cancelled"
    started: bool = False

    async def emit(self, name, data):
        async with self.changed:
            self.events.append({"event": name, "data": data})
            self.changed.notify_all()


class GenerationEngine:
    def __init__(self, db):
        self.db = db
        self.service = ConversationService(db)
        self.live = {}
        from .memories import BranchMemory
        self.memory = BranchMemory(db)

    def get_run(self, user_id, cid, rid):
        self.service.get_owned(user_id, cid)
        row = self.db.one("SELECT * FROM conversation_runs WHERE conversation_id=? AND request_id=?", (cid, rid))
        if not row:
            raise HTTPException(404, "生成记录不存在")
        return row

    def public(self, user_id, cid, rid):
        run = self.get_run(user_id, cid, rid)
        return {k: run[k] for k in (
            "request_id", "status", "reply", "user_node_id", "assistant_node_id", "error", "updated_at", "cleared"
        )} | {k: json.loads(run[k]) for k in ("usage", "context_usage", "sources")}

    def optional_context(self, user_id, row, path, message):
        result = {}
        if row.get("book_id") and row.get("knowledge_enabled"):
            from .knowledge_search import retrieve
            query = message
            if row.get("card_id"):
                query += " " + self.service.characters.owned(user_id, row["card_id"])["name"]
            if len(message) < 16:
                recent = next((n["content"] for n in reversed(path)
                               if n.get("entry_type") == "message" and n.get("role") == "user"), "")
                query += " " + recent[:500]
            result["knowledge"] = retrieve(self.db, user_id, row["book_id"], query)
        if self.memory:
            result["memory"] = self.memory.context(row["id"], path)
        return result

    def prepare(self, user_id, row, payload, parent_id, user_prompt=""):
        path = self.service.repo.path(row["id"], parent_id)
        optional = self.optional_context(user_id, row, path, payload.message)
        return budget.prepare(self.service, user_id, row, payload, parent_id, user_prompt, optional)

    def preview(self, user_id, cid, payload, user_prompt=""):
        row = self.service.get_owned(user_id, cid)
        parent = payload.parent_id if "parent_id" in payload.model_fields_set else row.get("active_leaf_id")
        if parent and not self.service.repo.node(cid, parent):
            raise HTTPException(404, "父消息节点不存在")
        prepared = self.prepare(user_id, row, payload, parent, user_prompt)
        return {"context_usage": prepared["context_usage"], "sources": prepared["sources"],
                "capabilities": provider.capability(prepared["settings"])}

    async def start(self, user_id, cid, payload, user_prompt=""):
        self.service.get_owned(user_id, cid)
        rid = payload.request_id or identifier("request")
        inputs = payload.model_dump(exclude={"request_id"})
        inputs["parent_explicit"] = "parent_id" in payload.model_fields_set
        inputs["user_prompt"] = user_prompt
        fingerprint = hashlib.sha256(dump(inputs).encode()).hexdigest()
        existing = self.db.one("SELECT * FROM conversation_runs WHERE conversation_id=? AND request_id=?", (cid, rid))
        if existing:
            if existing["cleared"]:
                raise HTTPException(409, "历史已清空，旧请求不可重放；重新生成请使用新的 request_id")
            if existing["fingerprint"] != fingerprint:
                raise HTTPException(409, "request_id 已用于不同参数；重新生成请使用新的 ID")
            return self.live.get((cid, rid)) or await self.replay(user_id, existing)
        guard = _conversation_lock(cid)
        guard.__enter__()
        live = None
        try:
            row = self.service.get_owned(user_id, cid)
            parent = payload.parent_id if "parent_id" in payload.model_fields_set else row.get("active_leaf_id")
            if parent and not self.service.repo.node(cid, parent):
                raise HTTPException(404, "父消息节点不存在")
            prepared = await asyncio.to_thread(self.prepare, user_id, row, payload, parent, user_prompt)
            stamp = now()
            self.db.execute(
                "INSERT INTO conversation_runs(conversation_id,request_id,fingerprint,status,parent_id,message,"
                "profile_id,model_snapshot,context_usage,sources,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, rid, fingerprint, "running", parent, payload.message, payload.profile_id or row.get("profile_id"),
                 dump(snapshot(prepared["settings"])), dump(prepared["context_usage"]),
                 dump(prepared["sources"]), stamp, stamp),
            )
            live = LiveRun(cid, rid)
            self.live[(cid, rid)] = live
            await live.emit("start", {"request_id": rid, "capabilities": provider.capability(prepared["settings"])})
            live.task = asyncio.create_task(self.run(live, guard, user_id, row, payload, prepared, user_prompt))
            # Enter the worker's try/finally before cancellation can be requested.
            await asyncio.sleep(0)
            return live
        except BaseException:
            if live and live.task:
                live.cancel_reason = "interrupted"
                live.task.cancel()
                if live.started:
                    await asyncio.shield(live.task)
                else:
                    self.live.pop((cid, rid), None)
                    guard.__exit__(None, None, None)
            else:
                guard.__exit__(None, None, None)
            raise

    async def replay(self, user_id, run):
        if run["status"] == "running":
            with _conversation_lock(run["conversation_id"]):
                self.finalize(user_id, run["conversation_id"], run["request_id"], run["reply"],
                              "interrupted", "生成任务已退出，恢复已保存文本；不会自动调用模型",
                              json.loads(run["usage"]))
                sync_mirror(self.db, run["conversation_id"])
            run = self.get_run(user_id, run["conversation_id"], run["request_id"])
        live = LiveRun(run["conversation_id"], run["request_id"])
        await live.emit("start", {"request_id": run["request_id"], "replayed": True,
                                "capabilities": provider.capability(json.loads(run["model_snapshot"]))})
        await live.emit("context", json.loads(run["context_usage"]))
        await live.emit("sources", json.loads(run["sources"]))
        if run["reply"]:
            await live.emit("delta", {"text": run["reply"]})
        await live.emit("terminal", self.result(user_id, run["conversation_id"], run["request_id"]))
        live.terminal = True
        return live

    def result(self, user_id, cid, rid):
        run = self.public(user_id, cid, rid)
        result = {**self.service.get(user_id, cid), **run, "response": run["reply"]}
        mirror = self.db.one("SELECT error FROM conversation_mirrors WHERE conversation_id=?", (cid,))
        if mirror and mirror["error"]:
            result["mirror_warning"] = "回复已保存，JSONL 镜像待恢复同步"
        return result

    async def auto_compact(self, user_id, row, payload, prepared, user_prompt):
        entries = effective_entries(prepared["path"])
        previous = next((e.get("summary", "") for e in entries if e.get("entry_type") == "compaction"), "")
        history = [e for e in entries if e.get("entry_type") != "compaction"]
        room = prepared["context_usage"]["available_input"] - prepared["fixed_tokens"]
        keep = min(2000, max(100, room // 2))
        cut = compaction.choose_cut_point(history, keep)
        if cut <= 0:
            if not prepared["context_usage"]["fits"]:
                raise HTTPException(422, "最近完整轮次超出预算，请缩短输入、手动压缩或切换更大上下文模型")
            return prepared
        summary = previous
        settings = {**prepared["settings"], "max_tokens": min(1024, max(128, room // 4))}
        limit = settings["context_window"] - settings["max_tokens"] - prepared["context_usage"]["safety"]
        # Split only the summarizer input, never discard parts of a long message.
        pending = [dict(e) for e in history[:cut]]
        while pending:
            batch = []
            while pending and compaction.messages_tokens(compaction.build_prompt(batch + [pending[0]], summary)) <= limit:
                batch.append(pending.pop(0))
            if not batch:
                item = pending[0]
                text = item["content"]
                low, high = 0, len(text)
                while low < high:
                    middle = (low + high + 1) // 2
                    test = [{**item, "content": text[:middle]}]
                    if compaction.messages_tokens(compaction.build_prompt(test, summary)) <= limit:
                        low = middle
                    else:
                        high = middle - 1
                if not low:
                    raise HTTPException(422, "摘要本身超出预算，请增加模型上下文窗口")
                batch = [{**item, "content": text[:low]}]
                item["content"] = text[low:]
                if not item["content"]:
                    pending.pop(0)
            summary = await provider.complete(settings, compaction.build_prompt(batch, summary))
        kept = history[cut:]
        node = identifier("compaction")
        self.service.repo.append_compaction(
            row["id"], node, row.get("active_leaf_id"), summary,
            prepared["context_usage"]["input_tokens"], kept[0].get("id") if kept else None,
            compaction.to_retained_tail(kept), now(),
        )
        row["active_leaf_id"] = node
        # User explicitly chose this parent; subsequent exchange must attach to its checkpoint.
        prepared = self.prepare(user_id, row, payload, node, user_prompt)
        if not prepared["context_usage"]["fits"]:
            raise HTTPException(422, "压缩后仍超出预算，请调整模型或输入")
        return prepared

    async def run(self, live, guard, user_id, row, payload, prepared, user_prompt):
        live.started = True
        cid, rid = live.conversation_id, live.request_id
        reply, usage, error, status = "", {}, None, "completed"
        parent = None
        try:
            parent = self.get_run(user_id, cid, rid)["parent_id"]
            if prepared["context_usage"]["needs_compaction"]:
                # Compaction must follow the requested branch, not an unrelated active leaf.
                row["active_leaf_id"] = parent
                prepared = await self.auto_compact(user_id, row, payload, prepared, user_prompt)
                parent = row.get("active_leaf_id")
            self.db.execute(
                "UPDATE conversation_runs SET parent_id=?,context_usage=?,sources=? WHERE conversation_id=? AND request_id=?",
                (parent, dump(prepared["context_usage"]), dump(prepared["sources"]), cid, rid),
            )
            await live.emit("context", prepared["context_usage"])
            await live.emit("sources", prepared["sources"])
            async for event in provider.stream(prepared["settings"], prepared["messages"]):
                if event.get("text"):
                    reply += event["text"]
                    # Each checkpoint is a short independent transaction, never held over network I/O.
                    self.db.execute(
                        "UPDATE conversation_runs SET reply=?,updated_at=? WHERE conversation_id=? AND request_id=?",
                        (reply, now(), cid, rid),
                    )
                    await live.emit("delta", {"text": event["text"]})
                if event.get("usage"):
                    usage = event["usage"]
                    self.db.execute(
                        "UPDATE conversation_runs SET usage=?,updated_at=? WHERE conversation_id=? AND request_id=?",
                        (dump(usage), now(), cid, rid),
                    )
            if not reply.strip():
                raise ValueError("模型返回空回复")
        except asyncio.CancelledError:
            status, error = live.cancel_reason, "生成已停止" if live.cancel_reason == "cancelled" else "连接中断"
        except Exception as exc:
            status = "interrupted" if reply.strip() else "failed"
            error = str(exc.detail) if isinstance(exc, HTTPException) else llm.error_message(exc)
            logger.warning("Conversation generation stopped: %s", type(exc).__name__)
        try:
            self.finalize(user_id, cid, rid, reply, status, error, usage, parent)
            warning = sync_mirror(self.db, cid)
            result = self.result(user_id, cid, rid)
            if warning:
                result["mirror_warning"] = warning
            if status == "completed" and self.memory and row.get("memory_enabled"):
                try:
                    self.memory.enqueue(user_id, cid, rid, result["assistant_node_id"], prepared["settings"])
                except Exception:
                    result["memory_warning"] = "回复已保存，记忆任务创建失败，可手动重试"
            await live.emit("terminal", result)
        except Exception:
            # Leave running checkpoint recoverable, and surface a durable-save error.
            logger.exception("Could not persist conversation generation")
            await live.emit("terminal", {"request_id": rid, "status": "failed", "reply": reply,
                                       "error": "回复持久化失败；保留请求 ID，恢复后查询状态", "storage_error": True})
        finally:
            guard.__exit__(None, None, None)
            async with live.changed:
                live.terminal = True
                live.changed.notify_all()
            self.live.pop((cid, rid), None)

    def finalize(self, user_id, cid, rid, reply, status, error, usage, parent=None):
        run = self.get_run(user_id, cid, rid)
        if run["status"] != "running":
            return
        stamp = now()
        if reply.strip():
            row = self.service.get_owned(user_id, cid)
            model = json.loads(run["model_snapshot"])
            self.service.repo.append_exchange(
                cid, parent if parent is not None else run["parent_id"], identifier("message"), identifier("message"),
                run["message"], reply, run["message"][:30] if row["title"] == "新会话" else row["title"], stamp,
                metadata={"status": status, "request_id": rid, "usage": usage,
                          "provider": model.get("provider"), "model": model.get("model"),
                          "sources": json.loads(run["sources"]), "context_usage": json.loads(run["context_usage"])},
                run_update={"request_id": rid, "status": status, "error": error, "usage": usage,
                            "memory_enabled": bool(row.get("memory_enabled"))},
            )
        else:
            self.db.execute(
                "UPDATE conversation_runs SET status=?,reply='',error=?,usage=?,updated_at=? WHERE conversation_id=? AND request_id=?",
                (status, error, dump(usage), stamp, cid, rid),
            )

    def recover(self):
        self.memory.recover()
        for run in self.db.all("SELECT r.*,c.user_id FROM conversation_runs r JOIN conversations c "
                               "ON c.id=r.conversation_id WHERE r.status='running'"):
            self.finalize(run["user_id"], run["conversation_id"], run["request_id"], run["reply"],
                          "interrupted", "服务重启，生成已中断；不会自动重新调用模型", json.loads(run["usage"]))
            sync_mirror(self.db, run["conversation_id"])

    async def cancel(self, user_id, cid, rid, reason="cancelled"):
        run = self.get_run(user_id, cid, rid)
        live = self.live.get((cid, rid))
        if run["status"] == "running" and live and live.task and not live.task.done():
            live.cancel_reason = reason
            live.task.cancel()
            await asyncio.shield(live.task)
        elif run["status"] == "running":
            with _conversation_lock(cid):
                self.finalize(user_id, cid, rid, run["reply"], "interrupted",
                              "任务已退出，恢复已保存的文本", json.loads(run["usage"]))
                sync_mirror(self.db, cid)
        return self.result(user_id, cid, rid)

    async def events(self, live):
        index = 0
        try:
            while True:
                if index < len(live.events):
                    event = live.events[index]
                    index += 1
                    yield f"event: {event['event']}\ndata: {dump(event['data'])}\n\n"
                    if event["event"] == "terminal":
                        return
                    continue
                if live.terminal:
                    return
                try:
                    async with live.changed:
                        await asyncio.wait_for(live.changed.wait(), timeout=5)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            if not live.terminal and live.task and not live.task.done():
                live.cancel_reason = "interrupted"
                live.task.cancel()
                try:
                    await asyncio.shield(live.task)
                except asyncio.CancelledError:
                    pass

    async def shutdown(self):
        tasks = []
        for live in list(self.live.values()):
            if live.task:
                live.cancel_reason = "interrupted"
                live.task.cancel()
                tasks.append(live.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.memory.shutdown()
