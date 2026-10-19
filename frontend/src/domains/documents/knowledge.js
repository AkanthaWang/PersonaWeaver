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

export function worldGroups(entries, filters = {}) {
  const groups = new Map();
  for (const entry of filterEntries(entries, filters)) {
    const category = entry.category || "地域";
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(entry);
  }
  return [...groups.entries()].map(([category, values]) => ({ category, entries: values }));
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

const normalizedName = (name) => String(name || "").normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase();

export function relationGraph(entries, { query = "", reviewOnly = false, chapter = null } = {}) {
  const nodes = new Map(), edges = new Map(), names = new Map();
  const profiles = [...entries].sort((a, b) => (b.frequency || 0) - (a.frequency || 0)
    || (a.first_appear || Number.MAX_SAFE_INTEGER) - (b.first_appear || Number.MAX_SAFE_INTEGER)
    || normalizedName(a.name).localeCompare(normalizedName(b.name), "zh")).map((entry, index) => ({
    id: entry.entity_id || `legacy:${index}`, name: entry.name, entry,
  }));
  for (const profile of profiles) {
    for (const name of new Set([profile.name, ...(profile.entry.aliases || [])].map(normalizedName).filter(Boolean))) {
      if (!names.has(name)) names.set(name, []);
      names.get(name).push(profile);
    }
  }
  const selected = new Set(filterEntries(entries, { query, reviewOnly, chapter }));
  for (const profile of profiles) {
    if (!selected.has(profile.entry)) continue;
    nodes.set(profile.id, profile);
    const facts = orderedEvidence(profile.entry);
    const records = facts.some((fact) => fact.relationships?.length) ? facts : [profile.entry];
    for (const fact of records) {
      if (chapter != null && !filterEntries([fact], { chapter }).length) continue;
      for (const relationship of fact.relationships || []) {
        const name = relationship.target_name?.trim(), relation = relationship.relation?.trim();
        if (!name || !relation) continue;
        const matches = names.get(normalizedName(name)) || [];
        const target = matches.length === 1 ? matches[0] : {
          id: `unresolved:${normalizedName(name)}`, name, ambiguous: matches.length > 1,
        };
        if (profile.id === target.id) continue;
        nodes.set(target.id, target);
        const symmetric = /^(同伴|战友|朋友|敌人|同盟|合作|伴侣|夫妻|爱人|队友|盟友)$/.test(relation);
        const endpoints = symmetric ? [profile.id, target.id].sort() : [profile.id, target.id];
        const id = JSON.stringify([symmetric ? "undirected" : "directed", endpoints[0], endpoints[1]]);
        if (!edges.has(id)) edges.set(id, {
          id, from: endpoints[0], to: endpoints[1],
          fromName: endpoints[0] === profile.id ? profile.name : target.name,
          toName: endpoints[1] === target.id ? target.name : profile.name,
          relation, relations: [], relationCount: 0, strength: 0,
          ambiguous: Boolean(target.ambiguous), sources: [],
        });
        const edge = edges.get(id);
        if (!edge.relations.includes(relation)) edge.relations.push(relation);
        edge.relationCount = edge.relations.length;
        edge.strength = Math.max(edge.strength, relation.length);
        if (edge.relations.length > 1) edge.relation = edge.relations[0];
        const sources = (fact.sources || []).filter((source) => chapter == null || Number(source.chapter_no) === chapter);
        for (const source of sources) {
          if (!edge.sources.some((item) => item.chapter_id === source.chapter_id && item.start === source.start && item.end === source.end)) edge.sources.push(source);
        }
      }
    }
  }
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}
