"""Isolated browser fixture. Every model invocation is replaced by this local stub."""

import asyncio
import json

from fastapi import Depends

from backend.app.application import create_app
from backend.app.ai.providers import conversation_stream as provider
from backend.app.core.dependencies import current_user, get_db
from backend.app.db.database import now
from backend.app.domains.knowledge.schemas import CharacterCreate, EvidenceCreate, FactCreate
from backend.app.domains.knowledge.service import KnowledgeService

calls = {"conversation": 0, "memory": 0}


async def fake_stream(settings, messages, json_mode=False):
    if json_mode:
        calls["memory"] += 1
        data = json.loads(messages[-1]["content"])
        yield {"text": json.dumps({"memories": [{
            "category": "promise", "key": "城东之约", "content": "约定在城东重逢",
            "source_ids": [data["messages"][-1]["id"]],
        }]}, ensure_ascii=False)}
        return
    calls["conversation"] += 1
    text = "## 城东之约\n\n林默在城东等候，双方约定明日重逢。\n\n<script>window.unsafe = true</script>"
    if "暂停" in messages[-1]["content"]:
        yield {"text": "林默正在城东等候，"}
        await asyncio.sleep(30)
        return
    for word in text:
        yield {"text": word}
        await asyncio.sleep(.003)
    yield {"usage": {"prompt_tokens": 120, "completion_tokens": 32, "total_tokens": 152}}


provider.stream = fake_stream
app = create_app()


@app.post("/test/setup")
def setup(user=Depends(current_user), db=Depends(get_db)):
    db.execute("INSERT INTO books(book_id,user_id,title,source_type,file_name,source_path,created_at,updated_at) "
               "VALUES(?,?,?,?,?,?,?,?)", ("browser_book", user["user_id"], "浏览器测试作品", "txt", "test.txt", "test.txt", now(), now()))
    db.book_database("browser_book").execute(
        "INSERT INTO chapters(id,book_id,chapter_no,title,content,word_count) VALUES(?,?,?,?,?,?)",
        ("browser_chapter", "browser_book", 1, "第一章 城东", "😀林默在城东等候。\n双方约定明日重逢。", 20))
    service = KnowledgeService(db)
    c = service.create_character(user["user_id"], "browser_book", CharacterCreate(name="林默", aliases=["小林"]))
    service.create_fact(user["user_id"], "browser_book", FactCreate(
        character_id=c["id"], fact_type="location", value="城东",
        evidence=EvidenceCreate(chapter_id="browser_chapter", quote="林默在城东等候", start_offset=1, end_offset=8)))
    return {"book_id": "browser_book"}


@app.post("/test/stats")
def stats():
    return calls
