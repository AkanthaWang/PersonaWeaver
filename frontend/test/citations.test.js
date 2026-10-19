import test from "node:test";
import assert from "node:assert/strict";
import { citationParts } from "../src/domains/documents/citations.js";
import { formatCoverage } from "../src/domains/documents/coverage.js";

test("citation uses Unicode characters rather than UTF-16 offsets", () => {
  assert.deepEqual(citationParts("甲\u{1F600}乙丙", { start: 2, end: 3, quote: "乙" }), ["甲\u{1F600}", "乙", "丙"]);
});
test("legacy, stale and invalid citations show text without incorrect highlighting", () => {
  for (const citation of [null, { start: -1, end: 3 }, { start: 0, end: 2, quote: "错" }, { start: 0, end: 99, quote: "甲" }]) {
    assert.deepEqual(citationParts("甲乙", citation), ["甲乙", "", ""]);
  }
});
test("coverage is compact for large books and preserves gaps", () => {
  assert.equal(formatCoverage([3, 2, 1, 3, 7, 9, 10]), "1-3、7、9-10");
  assert.equal(formatCoverage([]), "无");
});
