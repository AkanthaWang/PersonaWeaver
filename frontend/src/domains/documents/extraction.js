export function extractionScope(total, { range = "all", limit = 1, start = 1, end = total, coverage = [] } = {}) {
  if (!Number.isInteger(total) || total < 1) return null;
  const from = range === "interval" ? start : 1;
  const to = range === "limited" ? limit : range === "interval" ? end : total;
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 1 || to > total || from > to) return null;
  const count = to - from + 1;
  const covered = new Set(coverage.filter((number) => number >= from && number <= to)).size;
  return { from, to, count, covered, uncovered: count - covered };
}
