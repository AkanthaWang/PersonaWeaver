// TextDecoder preserves UTF-8 sequences split across network chunks.
export async function readEventStream(body, onEvent) {
  if (!body) throw new Error("服务器未返回事件流");
  const reader = body.getReader(), decoder = new TextDecoder();
  let buffer = "", event = "", lines = [], terminal = false;
  function line(value) {
    if (value === "") {
      if (lines.length) {
        const data = JSON.parse(lines.join("\n"));
        onEvent(event || "message", data);
        if (event === "terminal") terminal = true;
      }
      event = ""; lines = [];
    } else if (value.startsWith("event:")) event = value.slice(6).trim();
    else if (value.startsWith("data:")) lines.push(value.slice(5).replace(/^ /, ""));
  }
  function drain(final = false) {
    // A trailing CR may be the first half of CRLF in the next chunk.
    while (true) {
      const found = buffer.search(/[\r\n]/);
      if (found < 0 || (!final && found === buffer.length - 1 && buffer[found] === "\r")) break;
      const width = buffer[found] === "\r" && buffer[found + 1] === "\n" ? 2 : 1;
      const value = buffer.slice(0, found);
      buffer = buffer.slice(found + width); line(value);
    }
    if (final && buffer) { line(buffer); buffer = ""; }
  }
  try {
    while (!terminal) {
      const { done, value } = await reader.read();
      if (done) { buffer += decoder.decode(); drain(true); line(""); break; }
      buffer += decoder.decode(value, { stream: true }); drain();
    }
    if (!terminal) throw new Error("连接已断开，正在确认已保存的生成状态");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export function timelineForPath(path, pending = []) {
  const entries = [];
  for (const node of path || []) {
    if (["compaction", "branch_summary"].includes(node.entry_type)) {
      entries.push({ ...node, key: `marker-${node.id}`, kind: "marker", type: node.entry_type });
    } else if (["message", "custom_message"].includes(node.entry_type || "message")) {
      entries.push({ key: `message-${node.id}`, kind: "message", message: node });
    }
  }
  for (const [index, message] of pending.filter(Boolean).entries()) {
    entries.push({ key: `pending-${index}`, kind: "message", pending: true, message });
  }
  return entries;
}

export class GenerationSession {
  constructor({ api, fetchImpl = globalThis.fetch, onEvent }) {
    Object.assign(this, { api, fetchImpl, onEvent, epoch: 0, active: null });
  }
  emit(epoch, name, data) {
    if (epoch !== this.epoch || this.active?.terminal) return;
    if (name === "terminal") this.active.terminal = true;
    this.onEvent(name, data);
  }
  async send(conversationId, payload) {
    const epoch = ++this.epoch;
    this.active?.controller.abort();
    const controller = new AbortController();
    this.active = { conversationId, requestId: payload.request_id, controller, terminal: false };
    const base = (this.api.defaults.baseURL || "/api/v1").replace(/\/$/, "");
    try {
      const response = await this.fetchImpl(`${base}/conversations/${conversationId}/messages/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload), signal: controller.signal, credentials: "same-origin",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = body.detail;
        throw new Error(typeof detail === "string" ? detail : `发送失败（HTTP ${response.status}）`);
      }
      await readEventStream(response.body, (name, data) => this.emit(epoch, name, data));
    } catch (error) {
      if (epoch !== this.epoch || this.active.terminal) return;
      // A lost response must never result in an automatic second paid request.
      try {
        let saved = await this.api.get(`/conversations/${conversationId}/generations/${payload.request_id}`);
        if (saved.status === "running") saved = await this.api.post(
          `/conversations/${conversationId}/generations/${payload.request_id}/cancel`);
        if (saved.messages) this.emit(epoch, "terminal", saved);
        else this.emit(epoch, "terminal", {
          ...await this.api.get(`/conversations/${conversationId}`), ...saved, response: saved.reply,
        });
      } catch {
        this.emit(epoch, "error", { message: error.message, request_id: payload.request_id });
      }
    }
  }
  async stop() {
    const active = this.active, epoch = this.epoch;
    if (!active || active.terminal) return;
    const result = await this.api.post(
      `/conversations/${active.conversationId}/generations/${active.requestId}/cancel`);
    this.emit(epoch, "terminal", result);
    active.controller.abort();
  }
  dispose() {
    const active = this.active;
    this.epoch++;
    if (active && !active.terminal) {
      this.api.post(`/conversations/${active.conversationId}/generations/${active.requestId}/cancel`).catch(() => {});
    }
    active?.controller.abort();
  }
}
