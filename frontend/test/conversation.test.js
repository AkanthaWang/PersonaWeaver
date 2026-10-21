import test from "node:test";
import assert from "node:assert/strict";
import { readEventStream, timelineForPath, GenerationSession } from "../src/domains/conversation/stream.js";

function body(text, size = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream({ start(controller) {
    for (let i = 0; i < bytes.length; i += size) controller.enqueue(bytes.slice(i, i + size));
    controller.close();
  } });
}
test("UTF-8, CRLF, split fields, multiline data, comments, terminal", async () => {
  const events = [];
  await readEventStream(body(': ping\r\nevent: delta\r\ndata: {"text":\r\ndata: "你好😀"}\r\n\r\nevent: terminal\ndata: {"status":"completed"}\n\n'),
    (name, data) => events.push([name, data]));
  assert.deepEqual(events, [["delta", { text: "你好😀" }], ["terminal", { status: "completed" }]]);
});
test("disconnect is not a completed reply", async () => {
  await assert.rejects(readEventStream(body('event: delta\ndata: {"text":"partial"}\n\n'), () => {}), /连接已断开/);
  await assert.rejects(readEventStream(body('data: invalid\n\n'), () => {}), SyntaxError);
});
test("timeline uses the backend path, preserves checkpoint order and excludes memory markers", () => {
  const path = [
    { id: "1", entry_type: "message", role: "user" },
    { id: "2", entry_type: "compaction", summary: "summary" },
    { id: "3", entry_type: "memory_update", role: "assistant" },
    { id: "4", entry_type: "message", role: "assistant" },
  ];
  assert.deepEqual(timelineForPath(path).map(e => e.key), ["message-1", "marker-2", "message-4"]);
});
test("late responses cannot replace a newer conversation", async () => {
  let resolve;
  const events = [];
  const session = new GenerationSession({
    api: { defaults: { baseURL: "http://local/api" } },
    fetchImpl: () => new Promise(r => { resolve = r; }),
    onEvent: (...args) => events.push(args),
  });
  const pending = session.send("a", { request_id: "id" });
  session.epoch++;
  resolve({ ok: true, body: body('event: terminal\ndata: {"status":"completed"}\n\n') });
  await pending;
  assert.deepEqual(events, []);
});
test("network failure queries status instead of calling the model again", async () => {
  let requests = 0, cancels = 0;
  const events = [];
  const session = new GenerationSession({
    api: { defaults: { baseURL: "/api/v1" },
      get: async path => path.includes("generations") ? { status: "running" } : {},
      post: async () => { cancels++; return { status: "cancelled", reply: "保存部分", messages: [] }; } },
    fetchImpl: async () => { requests++; throw new Error("offline"); },
    onEvent: (...args) => events.push(args),
  });
  await session.send("a", { request_id: "id" });
  assert.equal(requests, 1); assert.equal(cancels, 1);
  assert.equal(events.at(-1)[1].reply, "保存部分");
});
