import test from "node:test";
import assert from "node:assert/strict";
import { changesFor, filterEntries, orderedEvidence, overview, relationGraph, timelineGroups } from "../src/domains/documents/knowledge.js";

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

test("relation graph keeps identities separate and unresolved duplicate names explicit", () => {
  const people = [
    { entity_id: "a", name: "林川", identity: "医师", relationships: [{ target_name: "阿遥", relation: "同伴" }] },
    { entity_id: "b", name: "林川", identity: "守卫" },
    { entity_id: "c", name: "阿遥", relationships: [{ target_name: "林川", relation: "恩人" }] },
  ];
  const graph = relationGraph(people);
  assert.equal(graph.nodes.filter((node) => node.name === "林川").length, 3);
  assert.ok(graph.nodes.some((node) => node.id === "a"));
  assert.ok(graph.nodes.some((node) => node.id === "b"));
  assert.equal(graph.edges.find((edge) => edge.from === "c").ambiguous, true);
  assert.equal(graph.edges.find((edge) => edge.from === "c").to, "unresolved:林川");
});

test("relation graph preserves directed relationships, aliases, chapter evidence and deduplication", () => {
  const source = (chapter) => ({ chapter_id: `c${chapter}`, chapter_no: chapter, start: 2, end: 5, quote: "原文" });
  const relationship = { target_name: " Ａ遥 ", relation: "父亲" };
  const a = { entity_id: "a", name: "林川", first_chapter: 1, relationships: [relationship],
    evidence: [
      { chapter_no: 1, relationships: [relationship], sources: [source(1)] },
      { chapter_no: 3, relationships: [relationship], sources: [source(3)] },
    ] };
  const b = { entity_id: "b", name: "阿遥", aliases: ["A遥"],
    evidence: [{ chapter_no: 1, relationships: [{ target_name: "林川", relation: "儿子" }], sources: [source(1)] }] };
  const graph = relationGraph([a, b]);
  assert.equal(graph.edges.length, 2);
  assert.deepEqual(graph.edges.map((edge) => [edge.from, edge.to, edge.relation]), [["a", "b", "父亲"], ["b", "a", "儿子"]]);
  assert.equal(graph.edges[0].sources.length, 2);
  const scoped = relationGraph([a, b], { chapter: 3 });
  assert.equal(scoped.edges.length, 1);
  assert.deepEqual(scoped.edges[0].sources.map((item) => item.chapter_no), [3]);
  assert.equal(relationGraph([a, b], { query: "不匹配" }).nodes.length, 0);
  assert.equal(relationGraph([a, b], { reviewOnly: true }).nodes.length, 0);
});
