const RELATION_LABEL_RULES = [
  { label: "亲属", pattern: /父亲|母亲|父母|兄弟|姐妹|哥哥|姐姐|弟弟|妹妹|夫妻|丈夫|妻子|亲属|家人|血缘/ },
  { label: "师徒", pattern: /师徒|师父|师傅|弟子|门生/ },
  { label: "上下级", pattern: /上下级|上司|下属|部下|主从|臣属|隶属/ },
  { label: "敌对", pattern: /敌对|敌人|仇敌|冲突|对立|仇恨|战斗|追杀|追捕/ },
  { label: "背叛", pattern: /背叛|欺骗|出卖/ },
  { label: "合作", pattern: /同盟|盟友|合作|协作/ },
  { label: "同伴", pattern: /朋友|好友|同伴|伙伴|同行者/ },
  { label: "情感", pattern: /喜欢|爱慕|爱恋|恋人|暧昧/ },
  { label: "保护", pattern: /保护|救助|帮助|照顾/ },
];

export function relationLabel(type) {
  const raw = String(type || "").replace(/\s+/g, " ").trim();
  if (!raw) return "相关";
  const matched = RELATION_LABEL_RULES.find((rule) => rule.pattern.test(raw));
  if (matched) return matched.label;
  return raw.length <= 8 && !/[，。；：、,.!?！？]/.test(raw) ? raw : "相关";
}

export function groupRelations(relations) {
  const groups = new Map();
  for (const relation of relations) {
    if (!relation.subject_id || !relation.object_id) continue;
    const id = JSON.stringify([relation.subject_id, relation.object_id].sort());
    if (!groups.has(id)) {
      groups.set(id, { id, subject_id: relation.subject_id, object_id: relation.object_id, labels: [], records: [] });
    }
    const group = groups.get(id);
    const label = relationLabel(relation.relation_type);
    if (!group.labels.includes(label)) group.labels.push(label);
    group.records.push(relation);
  }
  return [...groups.values()];
}

function eventTexts(value) {
  let parsed = value;
  if (typeof value === "string") {
    try { parsed = JSON.parse(value); } catch { parsed = value; }
  }
  const values = Array.isArray(parsed) ? parsed : [parsed];
  return values.filter((item) => typeof item === "string" && item.trim());
}

export function characterMilestones(character, facts = [], chapters = []) {
  const active = facts.filter((fact) =>
    fact.entity_id === character?.id && fact.fact_type === "key_events"
    && fact.state === "active" && !fact.deleted_at);
  const manual = active.filter((fact) => fact.source_type === "user");
  let entries = character?.milestones || [];
  const supplementalFacts = manual.length ? manual : entries.length ? [] : active;
  if (supplementalFacts.length) {
    entries = [...entries, ...supplementalFacts.flatMap((fact) =>
      eventTexts(fact.value_json).map((text) => ({
        text,
        // Agent facts merge chapters and share one citation; only manual facts have a reliable single source.
        chapters: fact.source_type === "user" && fact.chapter_id
          ? chapters.filter((chapter) => chapter.id === fact.chapter_id)
            .map((chapter) => ({ chapter_id: chapter.id, chapter_no: chapter.chapter_no, chapter_title: chapter.title }))
          : [],
      })))];
  } else if (entries.length && !active.length) {
    entries = [];
  }
  const groups = new Map();
  for (const entry of entries) {
    if (typeof entry.text !== "string") continue;
    const text = entry.text.replace(/\s+/g, " ").trim();
    if (!text) continue;
    const key = text.replace(/[。；;.!！?？]+$/, "");
    if (!groups.has(key)) groups.set(key, { id: key, text, chapters: [] });
    const group = groups.get(key);
    for (const chapter of entry.chapters || []) {
      if (!group.chapters.some((item) => item.chapter_id === chapter.chapter_id && item.chapter_no === chapter.chapter_no)) {
        group.chapters.push(chapter);
      }
    }
  }
  return [...groups.values()].map((entry) => ({
    ...entry,
    // Show the earliest documented chapter, including for legacy multi-source responses.
    chapters: entry.chapters.toSorted((a, b) => (a.chapter_no ?? Infinity) - (b.chapter_no ?? Infinity)).slice(0, 1),
  })).sort((a, b) =>
    (a.chapters[0]?.chapter_no ?? Infinity) - (b.chapters[0]?.chapter_no ?? Infinity));
}
