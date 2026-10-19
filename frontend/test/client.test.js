import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createPinia, setActivePinia } from "pinia";

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};
globalThis.window = new EventTarget();
const { api, TOKEN_KEY, upload, uploadBatch } = await import("../src/api/client.js");
const { useAuthStore } = await import("../src/stores/auth.js");
const { useWorkspaceStore } = await import("../src/stores/workspace.js");
const response = (config, data) => ({ config, data, status: 200, statusText: "OK", headers: {} });
beforeEach(() => { storage.clear(); setActivePinia(createPinia()); });

test("workspace profile loads without credentials or session storage", async () => {
  let request;
  api.defaults.adapter = async (config) => { request = config; return response(config, { username: "创作者", avatar: null }); };
  const auth = useAuthStore();
  await auth.fetchMe();
  assert.equal(auth.user.username, "创作者");
  assert.equal(auth.loaded, true);
  assert.equal(request.url, "/auth/me");
  assert.equal(request.headers.Authorization, undefined);
  assert.equal(storage.size, 0);
});

test("file upload uses the local endpoint and raw bytes", async () => {
  storage.set(TOKEN_KEY, "local-token");
  let request;
  api.defaults.adapter = async (config) => { request = config; return response(config, { book_id: "book" }); };
  const file = new Blob(["hello"], { type: "text/plain" });
  file.name = "story.txt";
  await upload("/books", file, { title: "story" });
  assert.equal(request.url, "/books");
  assert.equal(request.params.filename, "story.txt");
  assert.equal(request.headers.Authorization, undefined);
  assert.equal(request.headers["Content-Type"], "application/octet-stream");
  assert.equal(request.data, file);
});

test("batch upload uses multipart form data with every selected file", async () => {
  let request;
  api.defaults.adapter = async (config) => { request = config; return response(config, { items: [], succeeded: 0, failed: 0 }); };
  const first = new Blob(["one"], { type: "text/plain" });
  const second = new Blob(["two"], { type: "text/markdown" });
  first.name = "one.txt";
  second.name = "two.md";
  await uploadBatch([first, second]);
  assert.equal(request.url, "/books/batch");
  assert.ok(request.data instanceof FormData);
  assert.deepEqual(request.data.getAll("files").map((file) => file.name), ["one.txt", "two.md"]);
});

test("old session tokens do not block a password-free workspace", async () => {
  storage.set(TOKEN_KEY, "expired-token");
  let request;
  api.defaults.adapter = async (config) => { request = config; return response(config, { books: [] }); };
  await api.get("/books");
  assert.equal(request.headers.Authorization, undefined);
});

test("validation errors have a usable message", async () => {
  api.defaults.adapter = async (config) => { throw { config, response: { status: 422, data: { detail: [{ loc: ["body", "model"], msg: "required" }] } } }; };
  await assert.rejects(api.put("/settings/model", {}), /model: required/);
});

test("workspace preserves valid selection and drops deleted books", async () => {
  const workspace = useWorkspaceStore();
  api.defaults.adapter = async (config) => response(config, { books: [{ book_id: "a" }, { book_id: "b" }] });
  await workspace.refresh();
  assert.equal(workspace.selectedId, "a");
  workspace.selectedId = "b";
  await workspace.refresh();
  assert.equal(workspace.selectedId, "b");
  api.defaults.adapter = async (config) => response(config, { books: [{ book_id: "a" }] });
  await workspace.refresh();
  assert.equal(workspace.selectedId, "a");
});

test("late workspace responses cannot restore data after a reset", async () => {
  storage.set(TOKEN_KEY, "account-a");
  let resolve;
  api.defaults.adapter = (config) => new Promise((done) => { resolve = () => done(response(config, { books: [{ book_id: "private-book" }] })); });
  const workspace = useWorkspaceStore();
  const pending = workspace.refresh();
  await new Promise((done) => setImmediate(done));
  workspace.reset();
  storage.set(TOKEN_KEY, "account-b");
  resolve();
  await pending;
  assert.deepEqual(workspace.books, []);
  assert.equal(workspace.loading, false);
});
