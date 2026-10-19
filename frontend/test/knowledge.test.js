import test from "node:test";
import assert from "node:assert/strict";
import { changesFor, filterEntries, orderedEvidence, overview, timelineGroups } from "../src/domains/documents/knowledge.js";

test("events follow numeric chapter and quote positions, with recurring names retained", () => {
  const entry = (chapter, start, name = "抵达") => ({
    name, first_chapter: chapter, evidence: [{ chapter_no: chapter, chapter: `第${chapter}章`,
      sources: [{ chapter_no: chapter, start }] }],
  });
  const input = [entry(10, 2), entry(2, 40), entry(2, 1, "出发")];
  const groups = timelineGroups(input);
  assert.deepEqual(groups.map(group => group.chapter_no), [2, 10]);
  assert.deepEqual(groups[0].entries.map(event => event.name), ["出发", "抵达"]);
  assert.equal(input[0].first_chapter, 10);
});

test("chapter filters cover later evidence without filtering the entire archive as a historical snapshot", () => {
  const entry = { name: "药箱", owner: "阿遥", evidence: [{ chapter_no: 1 }, { chapter_no: 3 }], needs_review: true };
  assert.equal(filterEntries([entry], { chapter: 3, query: "阿遥", reviewOnly: true }).length, 1);
  assert.equal(filterEntries([entry], { chapter: 2 }).length, 0);
  assert.equal(filterEntries([entry], { chapter: 1, query: "城" }).length, 0);
});

test("one overview uses all synthesized paragraphs and falls back to legacy descriptions", () => {
  assert.equal(overview({ summary: "重复简介", synthesis: [{ text: "整体介绍" }, { text: "后续变化" }] }), "整体介绍\n\n后续变化");
  assert.equal(overview({ description: "旧资料" }), "旧资料");
  assert.equal(overview(null), "");
});

test("change history preserves chapter order, ownership transfers and state changes", () => {
  const changes = changesFor({ field_history: {
    summary: [{ chapter_no: 1, value: "简介一" }, { chapter_no: 3, value: "简介二" }],
    owner: [{ chapter_no: 1, value: "林川" }, { chapter_no: 3, value: "阿遥" }],
    state_changes: [{ chapter_no: 2, value: ["损坏"] }],
  } });
  assert.deepEqual(changes.map(change => [change.chapter_no, change.field]), [[1, "owner"], [2, "state_changes"], [3, "owner"]]);
  assert.deepEqual(orderedEvidence({ evidence: [{ chapter_no: 10 }, { chapter_no: 2 }] }).map(f => f.chapter_no), [2, 10]);
});
