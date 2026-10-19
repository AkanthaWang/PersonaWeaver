export function formatCoverage(chapters = []) {
  const sorted = [...new Set(chapters)].sort((a, b) => a - b);
  const ranges = [];
  let start, end;
  for (const chapter of sorted) {
    if (start === undefined) start = end = chapter;
    else if (chapter === end + 1) end = chapter;
    else { ranges.push(start === end ? String(start) : `${start}-${end}`); start = end = chapter; }
  }
  if (start !== undefined) ranges.push(start === end ? String(start) : `${start}-${end}`);
  return ranges.join("、") || "无";
}
