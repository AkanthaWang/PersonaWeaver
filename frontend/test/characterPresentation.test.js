import test from "node:test";
import assert from "node:assert/strict";
import { characterMilestones, groupRelations } from "../src/domains/documents/characterPresentation.js";

const relation = (id, subject_id, object_id, relation_type) => ({ id, subject_id, object_id, relation_type });
const keyFact = (overrides = {}) => ({
  entity_id: "a", fact_type: "key_events", state: "active", source_type: "agent",
  value_json: '["加入学院"]', chapter_id: "c1", ...overrides,
});

test("multiple types, reverse records and repeated labels merge once per character pair", () => {
  const records = [
    relation("r1", "a", "b", "同伴"), relation("r2", "a", "b", "合作"),
    relation("r3", "b", "a", "朋友"), relation("r4", "a", "c", "师徒"),
  ];
  const groups = groupRelations(records);
  assert.equal(groups.length, 2);
  assert.deepEqual(groups[0].labels, ["同伴", "合作"]);
  assert.equal(groups[0].records.length, 3);
  assert.equal(groups[0].records[2].subject_id, "b");
  assert.equal(records.length, 4);
});

test("matching names never merge different character IDs and pair IDs cannot collide", () => {
  const groups = groupRelations([
    relation("r1", "a:b", "c", "同伴"), relation("r2", "a", "b:c", "同伴"),
    relation("r3", "a", "a", "相关"), relation("r4", "", "c", "同伴"),
  ]);
  assert.equal(groups.length, 3);
  assert.equal(new Set(groups.map((group) => group.id)).size, 3);
});

test("milestones deduplicate repeated events, keep one chapter and exclude detailed attributes", () => {
  const character = { id: "a", milestones: [
    { text: "加入学院。", chapters: [{ chapter_id: "c3", chapter_no: 3 }] },
    { text: "加入学院", chapters: [{ chapter_id: "c2", chapter_no: 2 }] },
    { text: "晋升", chapters: [{ chapter_id: "c5", chapter_no: 5 }] },
  ] };
  const result = characterMilestones(character, [
    keyFact(), keyFact({ fact_type: "speech", value_json: '"寒暄"' }),
    keyFact({ entity_id: "b", value_json: '["其他人的事件"]' }),
  ]);
  assert.equal(result.length, 2);
  assert.deepEqual(result[0].chapters.map((chapter) => chapter.chapter_no), [2]);
  assert.equal(character.milestones.length, 3);
});

test("multi-source milestones select one earliest numbered chapter without changing original sources", () => {
  const sources = [
    { chapter_id: "unknown" },
    { chapter_id: "c10", chapter_no: 10 },
    { chapter_id: "c2", chapter_no: 2 },
  ];
  const result = characterMilestones({ id: "a", milestones: [
    { text: "拜师", chapters: sources },
    { text: "晋升", chapters: [{ chapter_id: "c3", chapter_no: 3 }] },
  ] }, [keyFact()]);
  assert.deepEqual(result.map((item) => item.chapters.map((chapter) => chapter.chapter_no)), [[2], [3]]);
  assert.equal(result[0].chapters[0].chapter_id, "c2");
  assert.equal(sources.length, 3);
  assert.equal(sources[0].chapter_id, "unknown");
});

test("manual key events augment extracted milestones and use their real chapter", () => {
  const result = characterMilestones({ id: "a", milestones: [{ text: "旧经历", chapters: [] }] }, [
    keyFact(), keyFact({ source_type: "user", value_json: '["修订经历"]', chapter_id: "c9" }),
  ], [{ id: "c9", chapter_no: 9, title: "重逢" }]);
  assert.deepEqual(result.map((item) => item.text), ["修订经历", "旧经历"]);
  assert.equal(result[0].chapters[0].chapter_no, 9);
});

test("consolidated legacy citations are not assigned to every event and deleted events stay hidden", () => {
  const character = { id: "a" };
  const result = characterMilestones(character, [keyFact()], [{ id: "c1", chapter_no: 1 }]);
  assert.deepEqual(result[0].chapters, []);
  assert.deepEqual(characterMilestones({ ...character, milestones: [{ text: "已删除", chapters: [] }] }, [
    keyFact({ state: "superseded" }), keyFact({ deleted_at: "yesterday" }),
  ]), []);
});
