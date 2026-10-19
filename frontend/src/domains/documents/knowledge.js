export function factPosition(fact) {
  const sources = [...(fact.sources || [])].sort((a, b) => a.chapter_no - b.chapter_no || a.start - b.start);
  return [sources[0]?.chapter_no ?? fact.chapter_no ?? Number.MAX_SAFE_INTEGER, sources[0]?.start ?? 0];
}

export function compareFacts(a, b) {
  const left = factPosition(a), right = factPosition(b);
  return left[0] - right[0] || left[1] - right[1] || String(a.fact_id || "").localeCompare(String(b.fact_id || ""));
}

export function orderedEvidence(entry) {
  return [...(entry?.evidence || [])].sort(compareFacts);
}

export function firstChapter(entry) {
  return entry.first_chapter ?? entry.chapter_no ?? factPosition(orderedEvidence(entry)[0] || {})[0];
}

export function overview(entry) {
  return entry?.synthesis?.map((paragraph) => paragraph.text).join("\n\n")
    || entry?.summary || entry?.description || entry?.identity || "";
}

export function filterEntries(entries, { query = "", reviewOnly = false, chapter = null } = {}) {
  const term = query.trim().toLocaleLowerCase();
  return entries.filter((entry) => (!reviewOnly || entry.needs_review)
    && (!term || JSON.stringify(entry).toLocaleLowerCase().includes(term))
    && (chapter == null || orderedEvidence(entry).some((fact) => Number(fact.chapter_no) === chapter
      || fact.sources?.some((source) => Number(source.chapter_no) === chapter))
      || firstChapter(entry) === chapter));
}

export function timelineGroups(entries) {
  const position = (entry) => orderedEvidence(entry)[0] || entry;
  const sorted = [...entries].sort((a, b) => compareFacts(position(a), position(b)));
  const groups = new Map();
  for (const entry of sorted) {
    const chapter = firstChapter(entry);
    if (!groups.has(chapter)) groups.set(chapter, {
      chapter_no: chapter, title: entry.chapter || position(entry).chapter || `第 ${chapter} 章`, entries: [],
    });
    groups.get(chapter).entries.push(entry);
  }
  return [...groups.values()];
}

export function changesFor(entry) {
  const keys = new Set(["identity", "appearance", "personality", "owner", "type", "significance",
    "state_changes", "relationships", "key_events"]);
  return Object.entries(entry?.field_history || {})
    .filter(([key, values]) => keys.has(key) && (values.length > 1 || ["state_changes", "key_events"].includes(key)))
    .flatMap(([field, values]) => values.map((value) => ({ field, ...value })))
    .sort((a, b) => a.chapter_no - b.chapter_no);
}
