<template>
  <header class="page-header page-header-compact"><BookPicker /></header>
  <div class="toolbar">
    <el-input v-model="query" placeholder="搜索知识内容" :prefix-icon="Search" clearable />
    <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    <el-button :icon="Download" :disabled="!bookId" @click="exportData">导出当前资料</el-button>
  </div>
  <section class="knowledge-summary-head">
    <div>
      <p class="eyebrow">EDITABLE KNOWLEDGE</p>
      <h1>故事资料</h1>
      <p class="muted">只展示当前有效记录。历史版本、删除和修订可从变更记录追溯。</p>
    </div>
    <div class="knowledge-metrics">
      <span><strong>{{ characters.length }}</strong>人物</span>
      <span><strong>{{ facts.length }}</strong>事实</span>
      <span><strong>{{ events.length }}</strong>事件</span>
      <span><strong>{{ clues.length }}</strong>伏笔</span>
      <span><strong>{{ reviews.length }}</strong>待审核</span>
    </div>
  </section>
  <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
  <el-tabs v-model="tab" class="view-tabs">
    <el-tab-pane name="characters" label="人物档案" />
    <el-tab-pane name="timeline" label="事件时间线" />
    <el-tab-pane name="relations" label="人物关系" />
    <el-tab-pane name="clues" label="伏笔线索" />
    <el-tab-pane name="reviews" :label="`待审核${reviews.length ? ` (${reviews.length})` : ''}`" />
  </el-tabs>

  <section v-if="tab === 'characters'" class="knowledge-grid">
    <el-empty v-if="!filteredCharacters.length" description="暂无人物资料" />
    <article v-for="character in filteredCharacters" :key="character.id" class="knowledge-card character-card">
      <div class="character-collapsed-row">
        <div class="character-title-wrap"><img class="knowledge-avatar" :src="characterAvatarUrl(character.canonical_name)" :alt="`${character.canonical_name}头像`" /><div class="character-title"><h2>{{ character.canonical_name }}</h2><p class="muted">{{ aliases(character.aliases_json) || '暂无别名' }}</p></div></div>
        <div class="character-meta"><span class="frequency">出现 {{ character.frequency || 0 }} 次</span><el-tag size="small" :type="character.state === 'active' ? 'success' : 'info'">{{ character.state }}</el-tag></div>
      </div>
      <p class="character-intro" :class="{ placeholder: !characterIntro(character) }">{{ characterIntro(character) || '暂无介绍，提取到事实后可自动生成。' }}</p>
      <div class="character-actions">
        <el-button v-if="cardFor(character.canonical_name)" size="small" type="success" plain @click="goCards">已有角色卡</el-button>
        <el-button v-else size="small" type="primary" plain :loading="cardBusy === character.id" @click="createCard(character)">生成角色卡</el-button>
        <el-button size="small" @click="openDetail(character)">查看详情</el-button>
      </div>
    </article>
  </section>

  <section v-else-if="tab === 'timeline'" class="story-timeline">
    <el-empty v-if="!filteredEvents.length" description="暂无事件时间线" />
    <template v-else>
      <div class="timeline-toolbar">
        <span class="muted">{{ timelineGroups.length }} 个章节 · {{ filteredEvents.length }} 个事件</span>
        <el-button link type="primary" @click="toggleAllChapters">{{ collapsedChapters.size ? '展开全部' : '收起全部' }}</el-button>
      </div>
      <article v-for="group in timelineGroups" :key="group.key" class="chapter-block knowledge-card">
        <header class="chapter-heading" @click="toggleChapter(group.key)">
          <div class="chapter-title">
            <span class="chapter-index">{{ group.label }}</span>
            <h2>{{ group.title }}</h2>
          </div>
          <div class="chapter-meta">
            <el-tag size="small" effect="plain">{{ group.events.length }} 个事件</el-tag>
            <span class="expand-mark">{{ collapsedChapters.has(group.key) ? '展开' : '收起' }}</span>
          </div>
        </header>
        <ol v-show="!collapsedChapters.has(group.key)" class="chapter-events">
          <li v-for="event in group.events" :key="event.id" class="timeline-event">
            <div class="event-heading">
              <h3>{{ event.title }}</h3>
              <span v-if="event.story_time_start" class="event-time">{{ event.story_time_start }}{{ event.story_time_end ? ` - ${event.story_time_end}` : '' }}</span>
            </div>
            <p class="event-description">{{ event.description || '暂无描述' }}</p>
            <div class="card-actions">
              <el-button v-if="event.quote" link type="primary" @click="openCitation(event)">查看原文</el-button>
              <el-button size="small" type="danger" plain @click="removeEvent(event)">删除事件</el-button>
            </div>
          </li>
        </ol>
      </article>
    </template>
  </section>

  <section v-else-if="tab === 'relations'" class="knowledge-card relation-panel">
    <div class="relation-toolbar">
      <el-radio-group v-model="relationView" size="small">
        <el-radio-button value="graph">关系图谱</el-radio-button>
        <el-radio-button value="list">关系列表</el-radio-button>
      </el-radio-group>
      <span class="muted">{{ filteredRelations.length }} 条关系 · {{ characterNameCount }} 位人物</span>
    </div>

    <div v-show="relationView === 'graph'" class="relation-graph-wrap">
      <el-empty v-if="!filteredRelations.length" description="暂无可展示的人物关系" />
      <div v-show="filteredRelations.length" ref="graphEl" class="relation-graph"></div>
      <p v-if="filteredRelations.length" class="graph-hint muted">拖拽节点可调整位置，滚轮缩放画布，拖拽空白处平移。</p>
    </div>

    <div v-show="relationView === 'list'">
      <el-empty v-if="!filteredRelations.length" description="暂无人物关系" />
      <article v-for="relation in filteredRelations" :key="relation.id" class="relation-record">
        <div>
          <strong>{{ characterName(relation.subject_id) }}</strong>
          <el-tag size="small" effect="plain" class="relation-type">{{ relation.relation_type || '相关' }}</el-tag>
          <strong>{{ characterName(relation.object_id) }}</strong>
        </div>
        <div><el-button v-if="relation.evidence_id" link type="primary" @click="openCitation(relation)">原文</el-button><el-button link type="danger" @click="removeRelation(relation)">删除</el-button></div>
      </article>
    </div>
  </section>

  <section v-else-if="tab === 'clues'" class="knowledge-grid">
    <el-empty v-if="!filteredClues.length" description="暂无伏笔线索" />
    <article v-for="clue in filteredClues" :key="clue.id" class="knowledge-card">
      <div class="card-heading"><h2>{{ clue.title }}</h2><el-tag :type="clue.state === 'revealed' ? 'success' : 'warning'">{{ clue.state }}</el-tag></div>
      <p class="quote-text">“{{ clue.original_text }}”</p>
      <p>{{ clue.possible_meaning || '尚未记录可能含义' }}</p>
      <div class="card-actions">
        <el-button v-if="clue.evidence_id" link type="primary" @click="openCitation(clue)">查看依据</el-button>
        <el-button v-if="clue.state !== 'revealed'" size="small" type="success" @click="verifyClue(clue)">标记已验证</el-button>
        <el-button size="small" type="danger" plain @click="removeClue(clue)">删除</el-button>
      </div>
    </article>
  </section>

  <section v-else class="knowledge-card">
    <el-empty v-if="!reviews.length" description="暂无待审核内容" />
    <article v-for="review in reviews" :key="review.id" class="review-row">
      <div><el-tag type="warning">{{ review.review_type }}</el-tag><p>{{ reviewText(review.payload_json) }}</p></div>
      <div><el-button type="success" size="small" @click="resolveReview(review, 'approve')">通过</el-button><el-button type="danger" size="small" plain @click="resolveReview(review, 'reject')">拒绝</el-button></div>
    </article>
  </section>

  <ChapterReader v-model="showReader" :book-id="bookId" :chapter-id="citation?.chapter_id" :citation="citation" />

  <el-drawer v-model="detailOpen" :title="detail?.canonical_name || '人物详情'" size="620px" class="character-drawer">
    <template v-if="detail">
      <div class="drawer-meta">
        <el-tag :type="detail.state === 'active' ? 'success' : 'info'">{{ detail.state }}</el-tag>
        <span class="frequency">出现 {{ detail.frequency || 0 }} 次</span>
        <span class="muted">{{ aliases(detail.aliases_json) || '暂无别名' }}</span>
      </div>
      <section class="drawer-section">
        <h3>人物介绍</h3>
        <p v-if="detailIntro" class="character-intro full">{{ detailIntro }}</p>
        <el-empty v-else-if="!detailSynthesis.length" :image-size="50" description="暂无介绍" />
        <p v-else class="muted">本人物只有模型归纳结果，已展示在下方综合档案，生成角色卡时自动取用。</p>
      </section>
      <section v-if="detailSynthesis.length" class="drawer-section">
        <h3>综合档案（模型归纳）</h3>
        <p v-for="(paragraph, index) in detailSynthesis" :key="index" class="synthesis-paragraph">{{ paragraph.text }}</p>
      </section>
      <section class="drawer-section">
        <h3>事实依据</h3>
        <el-empty v-if="!detailFacts.length" :image-size="50" description="暂无事实" />
        <div v-for="fact in detailFacts" :key="fact.id" class="fact-row">
          <div><strong>{{ factTypeLabel(fact.fact_type) }}</strong><p>{{ displayValue(fact.value_json) }}</p></div>
          <div class="fact-actions">
            <el-tag size="small" effect="plain">v{{ fact.version }}</el-tag>
            <el-button v-if="fact.quote" link type="primary" @click="openCitation(fact)">原文</el-button>
            <el-button link type="danger" @click="removeFact(fact)">删除</el-button>
          </div>
        </div>
      </section>
      <section v-if="detailRelations.length" class="drawer-section">
        <h3>人物关系</h3>
        <article v-for="relation in detailRelations" :key="relation.id" class="relation-record">
          <div>
            <strong>{{ relation.subject_id === detail.id ? detail.canonical_name : characterName(relation.subject_id) }}</strong>
            <el-tag size="small" effect="plain" class="relation-type">{{ relation.relation_type || '相关' }}</el-tag>
            <strong>{{ relation.object_id === detail.id ? detail.canonical_name : characterName(relation.object_id) }}</strong>
          </div>
          <el-button v-if="relation.chapter_id || relation.evidence_id" link type="primary" @click="openCitation(relation)">原文</el-button>
        </article>
      </section>
      <div class="drawer-actions">
        <el-button v-if="cardFor(detail.canonical_name)" type="success" @click="goCards">前往角色卡</el-button>
        <el-button v-else type="primary" :loading="cardBusy === detail.id" @click="createCard(detail)">生成角色卡</el-button>
        <el-button type="danger" plain @click="removeDetailCharacter">移除人物</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Download, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Graph } from "@antv/g6";
import BookPicker from "../../../components/BookPicker.vue";
import ChapterReader from "../components/ChapterReader.vue";
import { api } from "../../../api/client.js";
import { useWorkspaceStore } from "../../../stores/workspace.js";
import { report } from "../../../lib/ui.js";
import { characterAvatarUrl } from "../../../lib/avatar.js";

const workspace = useWorkspaceStore();
const router = useRouter();
const bookId = ref(""), tab = ref("characters"), query = ref(""), loading = ref(false), error = ref("");
const characters = ref([]), facts = ref([]), events = ref([]), relations = ref([]), clues = ref([]), reviews = ref([]);
const cards = ref([]), cardBusy = ref("");
const factsLoading = reactive({}), showReader = ref(false), citation = ref(null);
const detail = ref(null), detailOpen = ref(false);
const chapters = ref([]), collapsedChapters = reactive(new Set());
const relationView = ref("graph"), graphEl = ref(null);
let relationGraph = null;
const GRAPH_COLORS = ["#2f6f5e", "#3c7a9c", "#8a6bb1", "#b1734a", "#9c5a75", "#5c7d3e", "#a3893a", "#4f6e91"];
const characterName = (id) => characters.value.find((item) => item.id === id)?.canonical_name || id;
const characterNameCount = computed(() => new Set(filteredRelations.value.flatMap((item) => [item.subject_id, item.object_id])).size);
const relationColor = (type) => GRAPH_COLORS[[...String(type || "")].reduce((sum, char) => sum + char.codePointAt(0), 0) % GRAPH_COLORS.length];
const text = (value) => String(value || "").toLocaleLowerCase();
const matches = (value) => !query.value.trim() || text(value).includes(text(query.value.trim()));
const filteredCharacters = computed(() => characters.value.filter((item) => matches(`${item.canonical_name} ${aliases(item.aliases_json)}`)));
const filteredEvents = computed(() => events.value.filter((item) => matches(`${item.title} ${item.description}`)));
const filteredRelations = computed(() => relations.value.filter((item) => matches(`${item.subject_id} ${item.relation_type} ${item.object_id}`)));
const filteredClues = computed(() => clues.value.filter((item) => matches(`${item.title} ${item.original_text} ${item.possible_meaning}`)));
const chapterTitles = computed(() => Object.fromEntries(chapters.value.map((item) => [item.chapter_no, item.title])));
const timelineGroups = computed(() => {
  const groups = new Map();
  for (const event of filteredEvents.value) {
    const key = event.chapter_no ?? "none";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(event);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => (left === "none" ? Infinity : left) - (right === "none" ? Infinity : right))
    .map(([key, list]) => ({
      key: String(key),
      chapterNo: key === "none" ? null : key,
      label: key === "none" ? "未归章" : `第 ${key} 章`,
      title: key === "none" ? "未归属章节" : (chapterTitles.value[key] || "未命名章节"),
      events: list.toSorted((left, right) =>
        (left.sequence_no ?? 0) - (right.sequence_no ?? 0)
        || String(left.story_time_start || "").localeCompare(String(right.story_time_start || ""), "zh")
        || text(left.title).localeCompare(text(right.title), "zh")),
    }));
});
function toggleChapter(key) {
  if (collapsedChapters.has(key)) collapsedChapters.delete(key);
  else collapsedChapters.add(key);
}
function toggleAllChapters() {
  if (collapsedChapters.size) collapsedChapters.clear();
  else timelineGroups.value.forEach((group) => collapsedChapters.add(group.key));
}
const characterFacts = (id) => facts.value.filter((item) => item.entity_id === id && item.state === "active");
const FACT_LABELS = { summary: "简介", identity: "身份", appearance: "外貌", personality: "性格",
  behavior: "行为", speech: "台词", relationships: "关系", key_events: "关键经历", state_changes: "状态变化" };
const factTypeLabel = (type) => FACT_LABELS[type] || type;
const clip = (value, limit = 140) => {
  const flat = String(value || "").replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat;
};
function factIntro(character, limit) {
  if (!character) return "";
  const values = ["summary", "identity"].flatMap((type) => characterFacts(character.id)
    .filter((fact) => fact.fact_type === type)
    .map((fact) => displayValue(fact.value_json)));
  const source = values.some(Boolean) ? values
    : characterFacts(character.id).map((fact) => displayValue(fact.value_json));
  return clip(source.filter(Boolean).join(" "), limit);
}
function characterIntro(character) {
  const synthesis = (character?.synthesis || []).map((item) => item.text).filter(Boolean)[0];
  return clip(synthesis || factIntro(character, 400), 140);
}
const detailIntro = computed(() => (detail.value ? factIntro(detail.value, 800) : ""));
const detailSynthesis = computed(() => detail.value?.synthesis || []);
const detailFacts = computed(() => (detail.value ? characterFacts(detail.value.id) : []));
const detailRelations = computed(() => (detail.value
  ? filteredRelations.value.filter((item) => item.subject_id === detail.value.id || item.object_id === detail.value.id)
  : []));
const cardFor = (name) => cards.value.find((card) => card.name === name);
function openDetail(character) {
  detail.value = character;
  detailOpen.value = true;
}
function goCards() { router.push("/characters"); }
async function createCard(character) {
  if (!bookId.value || cardBusy.value) return;
  cardBusy.value = character.id;
  try {
    const result = await api.post("/cards/from-character", { book_id: bookId.value, character_id: character.id });
    cards.value = [...cards.value.filter((card) => card.id !== result.card.id), result.card];
    ElMessage.success(result.created ? "已生成角色卡，可在「角色卡」中编辑" : "该人物已有角色卡");
  } catch (err) { report(err); } finally { cardBusy.value = ""; }
}
async function removeDetailCharacter() {
  if (!detail.value) return;
  await removeCharacter(detail.value);
  detailOpen.value = false;
}
function aliases(value) { try { return JSON.parse(value || "[]").join("、"); } catch { return ""; } }

async function renderRelationGraph() {
  if (tab.value !== "relations" || relationView.value !== "graph") return;
  await nextTick();
  const container = graphEl.value;
  if (!container) return;
  relationGraph?.destroy();
  relationGraph = null;
  if (!filteredRelations.value.length) return;

  const visibleIds = new Set(filteredRelations.value.flatMap((item) => [item.subject_id, item.object_id]));
  const nodes = characters.value.filter((item) => visibleIds.has(item.id)).map((item) => ({
    id: item.id,
    style: {
      labelText: item.canonical_name,
      size: Math.min(64, 32 + Math.sqrt(item.frequency || 0) * 4),
      fill: "#eaf4f0",
      stroke: "#2f6f5e",
      lineWidth: 1.5,
      labelPlacement: "bottom",
      labelFill: "#1d3b33",
      labelFontSize: 12,
      cursor: "pointer",
    },
  }));
  const edges = filteredRelations.value.map((item) => ({
    id: item.id,
    source: item.subject_id,
    target: item.object_id,
    style: {
      labelText: item.relation_type || "",
      stroke: relationColor(item.relation_type),
      lineWidth: 1.6,
      endArrow: true,
      endArrowSize: 8,
      labelFontSize: 10,
      labelFill: "#4b635a",
      labelBackground: true,
      labelBackgroundFill: "#ffffff",
      labelBackgroundOpacity: 0.85,
      labelPadding: [1, 3],
    },
  }));

  relationGraph = new Graph({
    container,
    autoResize: true,
    data: { nodes, edges },
    node: { type: "circle" },
    layout: { type: "force", preventOverlap: true, nodeSize: 48, linkDistance: 160, collideStrength: 0.9 },
    behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
  });
  await relationGraph.render();
  relationGraph.fitView();
}
function displayValue(value) { try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed.join("、") : typeof parsed === "object" ? JSON.stringify(parsed) : parsed; } catch { return value; } }
function reviewText(value) { try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; } }
async function load() {
  if (!bookId.value) return;
  loading.value = true; error.value = "";
  try {
    const [characterRows, eventRows, relationRows, clueRows, reviewRows, chapterRows] = await Promise.all([
      api.get(`/books/${bookId.value}/knowledge/characters`), api.get(`/books/${bookId.value}/knowledge/events`),
      api.get(`/books/${bookId.value}/knowledge/relations`), api.get(`/books/${bookId.value}/knowledge/clues`),
      api.get(`/books/${bookId.value}/knowledge/reviews`), api.get(`/books/${bookId.value}/chapters`),
    ]);
    characters.value = characterRows; events.value = eventRows; relations.value = relationRows; clues.value = clueRows; reviews.value = reviewRows;
    chapters.value = chapterRows.chapters || [];
    cards.value = (await api.get("/cards", { params: { book_id: bookId.value } })).cards || [];
    const factRows = await Promise.all(characterRows.map(async (character) => {
      factsLoading[character.id] = true;
      try { return await api.get(`/books/${bookId.value}/knowledge/characters/${character.id}/facts`); }
      finally { factsLoading[character.id] = false; }
    }));
    facts.value = factRows.flat();
  } catch (err) { error.value = err.message; } finally { loading.value = false; }
}
function openCitation(row) {
  if (!row.chapter_id && !row.evidence_id) return;
  citation.value = { chapter_id: row.chapter_id, start: row.start_offset, end: row.end_offset, quote: row.quote };
  showReader.value = true;
}
async function removeCharacter(row) { await remove(`/books/${bookId.value}/knowledge/characters/${row.id}`, "确认移除这个人物？"); }async function removeFact(row) { await remove(`/books/${bookId.value}/knowledge/facts/${row.id}`, "确认删除这个事实版本？"); }
async function removeEvent(row) { await remove(`/books/${bookId.value}/knowledge/events/${row.id}`, "确认删除这个事件？"); }
async function removeRelation(row) { await remove(`/books/${bookId.value}/knowledge/relations/${row.id}`, "确认删除这条关系？"); }
async function removeClue(row) { await remove(`/books/${bookId.value}/knowledge/clues/${row.id}`, "确认删除这个线索？"); }
async function remove(path, message) {
  try { await ElMessageBox.confirm(message, "确认操作", { type: "warning" }); await api.delete(path); ElMessage.success("已更新知识库"); await load(); }
  catch (err) { if (err !== "cancel" && err !== "close") report(err); }
}
async function verifyClue(row) { try { await api.post(`/books/${bookId.value}/knowledge/clues/${row.id}/verify`); ElMessage.success("线索已标记为已验证"); await load(); } catch (err) { report(err); } }
async function resolveReview(row, action) { try { await api.post(`/books/${bookId.value}/knowledge/reviews/${row.id}/resolve`, { action }); ElMessage.success("审核状态已更新"); await load(); } catch (err) { report(err); } }
function exportData() { const data = JSON.stringify({ characters: characters.value, facts: facts.value, events: events.value, relations: relations.value, clues: clues.value }, null, 2); const blob = new Blob([data], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "knowledge.json"; link.click(); URL.revokeObjectURL(link.href); }
watch(() => workspace.selectedId, (value) => { bookId.value = value || ""; detailOpen.value = false; detail.value = null; load(); }, { immediate: true });
watch([tab, relationView], () => renderRelationGraph());
watch(filteredRelations, () => renderRelationGraph());
onBeforeUnmount(() => { relationGraph?.destroy(); relationGraph = null; });
</script>

<style scoped>
.knowledge-summary-head { display:flex; justify-content:space-between; gap:24px; align-items:end; margin:24px 0 12px; }
.knowledge-summary-head h1 { margin:4px 0 8px; }
.knowledge-metrics { display:flex; gap:18px; flex-wrap:wrap; color:#718078; }
.knowledge-metrics strong { display:block; color:#1d4d42; font-size:24px; }
.knowledge-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }
.knowledge-card { padding:18px; border:1px solid #dfe8e2; border-radius:12px; background:#fff; margin:12px 0; }
.card-heading,.card-actions,.relation-record,.review-row,.character-collapsed-row { display:flex; justify-content:space-between; align-items:center; gap:12px; }
.character-collapsed-row { cursor: default; min-height:54px; }
.character-title-wrap { display:flex; align-items:center; gap:10px; min-width:0; }
.knowledge-avatar { width:44px; height:44px; flex:0 0 44px; border-radius:12px; object-fit:cover; background:#e7f2ee; }
.character-card { display:flex; flex-direction:column; gap:10px; }
.character-intro { margin:0; color:#48605a; line-height:1.6; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; }
.character-intro.placeholder { color:#93a49c; }
.character-intro.full { -webkit-line-clamp:unset; display:block; overflow:visible; }
.character-actions { display:flex; justify-content:flex-end; gap:8px; }
.drawer-meta { display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding-bottom:12px; border-bottom:1px solid #edf1ee; }
.drawer-section { margin-top:18px; }
.drawer-section h3 { margin:0 0 8px; font-size:15px; color:#22453c; }
.drawer-section .character-intro { -webkit-line-clamp:unset; display:block; overflow:visible; }
.synthesis-paragraph { margin:0 0 10px; color:#3f5750; line-height:1.7; }
.drawer-actions { position:sticky; bottom:0; display:flex; justify-content:flex-end; gap:8px; padding:14px 0 4px; margin-top:18px; background:#fff; border-top:1px solid #edf1ee; }
.character-title { min-width:0; }
.character-title h2 { margin:0; overflow-wrap:anywhere; font-size:18px; }
.character-title p { margin:4px 0 0; }
.character-meta { display:flex; align-items:center; gap:10px; white-space:nowrap; }
.frequency { color:#477568; font-size:13px; }
.timeline-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:0 0 12px; }
.chapter-block { padding:0; overflow:hidden; }
.chapter-heading { display:flex; justify-content:space-between; align-items:center; gap:12px; padding:14px 18px; cursor:pointer; background:#f5faf7; border-bottom:1px solid #e7efeb; }
.chapter-title { display:flex; align-items:baseline; gap:10px; min-width:0; }
.chapter-title h2 { margin:0; font-size:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.chapter-index { flex:none; font-size:12px; color:#3f6f60; background:#e3f0ea; border-radius:999px; padding:2px 10px; }
.chapter-meta { display:flex; align-items:center; gap:10px; white-space:nowrap; }
.chapter-events { list-style:none; margin:0; padding:4px 18px 14px 34px; position:relative; }
.chapter-events::before { content:""; position:absolute; left:16px; top:12px; bottom:16px; width:2px; background:#e1ece7; }
.chapter-events li { position:relative; padding:12px 0 4px; border-bottom:1px dashed #eef3f0; }
.chapter-events li:last-child { border-bottom:none; }
.chapter-events li::before { content:""; position:absolute; left:-22px; top:19px; width:9px; height:9px; border-radius:50%; background:#69a58f; box-shadow:0 0 0 3px #eaf4f0; }
.chapter-events .event-heading { display:flex; align-items:baseline; gap:10px; justify-content:space-between; }
.chapter-events h3 { margin:0; font-size:15px; }
.event-time { flex:none; font-size:12px; color:#718078; }
.chapter-events .event-description { margin:6px 0 0; color:#53645c; }
.expand-mark { color:#6d8b80; font-size:13px; }
.card-heading h2 { margin:0; font-size:18px; }
.fact-list { margin-top:12px; }
.fact-row,.review-row { padding:10px 0; border-top:1px solid #edf1ee; }
.fact-row { display:flex; justify-content:space-between; gap:10px; }
.fact-row strong,.fact-row p { margin:0; }
.fact-row p { margin-top:4px; color:#53645c; }
.fact-actions { display:flex; align-items:center; white-space:nowrap; }
.card-actions { margin-top:14px; justify-content:flex-end; }
.relation-record { padding:14px 0; border-bottom:1px solid #edf1ee; }
.relation-record small { display:block; color:#718078; margin-top:5px; }
.relation-arrow { margin:0 10px; color:#70958a; }
.relation-panel { padding:18px; }
.relation-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:8px; }
.relation-type { margin:0 10px; }
.relation-graph { width:100%; height:560px; border-radius:10px; background:#f7fbf9; border:1px solid #e6efea; }
.graph-hint { margin:8px 0 0; font-size:12px; }
.relation-graph-wrap { margin-top:8px; }
.quote-text { padding:12px; background:#f6faf7; border-left:3px solid #82ad9d; color:#4d6258; }
.review-row p { white-space:pre-wrap; max-width:700px; color:#53645c; }
@media (max-width:700px) { .knowledge-summary-head { display:block; } .knowledge-metrics { margin-top:16px; } .fact-row,.review-row { display:block; } .fact-actions { margin-top:8px; } }</style>
