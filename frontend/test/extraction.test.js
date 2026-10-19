import test from "node:test";
import assert from "node:assert/strict";
import { extractionScope } from "../src/domains/documents/extraction.js";

test("extraction scope counts selected coverage without claiming all covered chapters are reusable", () => {
  assert.deepEqual(extractionScope(10, { range: "interval", start: 3, end: 6, coverage: [1, 3, 3, 5, 10] }),
    { from: 3, to: 6, count: 4, covered: 2, uncovered: 2 });
  assert.deepEqual(extractionScope(10, { range: "limited", limit: 2 }),
    { from: 1, to: 2, count: 2, covered: 0, uncovered: 2 });
  assert.equal(extractionScope(10).count, 10);
});

test("invalid, empty and reversed ranges cannot start extraction", () => {
  for (const [total, options] of [
    [0, {}], [undefined, {}], [10, { range: "limited", limit: null }],
    [10, { range: "interval", start: 6, end: 3 }], [10, { range: "interval", start: 0, end: 3 }],
    [10, { range: "interval", start: 1, end: 11 }], [10, { range: "limited", limit: 1.5 }],
  ]) assert.equal(extractionScope(total, options), null);
});
