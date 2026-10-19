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
    <article v-for="character in filteredCharacters" :key="character.id" class="knowledge-card">
      <div class="character-collapsed-row" @click="toggleCharacter(character.id)">
        <div class="character-title"><h2>{{ character.canonical_name }}</h2><p class="muted">{{ aliases(character.aliases_json) || '暂无别名' }}</p></div>
        <div class="character-meta"><span class="frequency">出现 {{ character.frequency || 0 }} 次</span><el-tag :type="character.state === 'active' ? 'success' : 'info'">{{ character.state }}</el-tag><span class="expand-mark">{{ expandedCharacters.has(character.id) ? '收起' : '展开' }}</span></div>
      </div>
      <div v-if="expandedCharacters.has(character.id)" v-loading="factsLoading[character.id]" class="fact-list">
        <div v-for="fact in characterFacts(character.id)" :key="fact.id" class="fact-row">
          <div><strong>{{ fact.fact_type }}</strong><p>{{ displayValue(fact.value_json) }}</p></div>
          <div class="fact-actions">
            <el-tag size="small" effect="plain">v{{ fact.version }}</el-tag>
            <el-button v-if="fact.quote" link type="primary" @click.stop="openCitation(fact)">原文</el-button>
            <el-button link type="danger" @click.stop="removeFact(fact)">删除</el-button>
          </div>
        </div>
        <el-empty v-if="!characterFacts(character.id).length" :image-size="50" description="暂无事实" />
      </div>
      <div v-if="expandedCharacters.has(character.id)" class="card-actions">
        <el-button size="small" @click="openCharacterFacts(character)">查看历史版本</el-button>
        <el-button size="small" type="danger" plain @click="removeCharacter(character)">移除人物</el-button>
      </div>
    </article>
  </section>

  <section v-else-if="tab === 'timeline'" class="story-timeline">
    <el-empty v-if="!filteredEvents.length" description="暂无事件时间线" />
    <article v-for="event in filteredEvents" :key="event.id" class="timeline-event knowledge-card">
      <div class="event-heading"><h2>{{ event.title }}</h2><el-tag v-if="event.chapter_no" size="small">第 {{ event.chapter_no }} 章</el-tag></div>
      <p class="event-description">{{ event.description || '暂无描述' }}</p>
      <p v-if="event.story_time_start" class="muted">故事时间：{{ event.story_time_start }}{{ event.story_time_end ? ` - ${event.story_time_end}` : '' }}</p>
      <div class="card-actions">
        <el-button v-if="event.quote" link type="primary" @click="openCitation(event)">查看原文</el-button>
        <el-button size="small" type="danger" plain @click="removeEvent(event)">删除事件</el-button>
      </div>
    </article>
  </section>

  <section v-else-if="tab === 'relations'" class="knowledge-card relation-list">
    <el-empty v-if="!filteredRelations.length" description="暂无人物关系" />
    <article v-for="relation in filteredRelations" :key="relation.id" class="relation-record">
      <div><strong>{{ relation.subject_id }}</strong><span class="relation-arrow">→</span><strong>{{ relation.object_id }}</strong><small>{{ relation.relation_type }}</small></div>
      <div><el-button v-if="relation.evidence_id" link type="primary" @click="openCitation(relation)">原文</el-button><el-button link type="danger" @click="removeRelation(relation)">删除</el-button></div>
    </article>
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
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Download, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import BookPicker from "../../../components/BookPicker.vue";
import ChapterReader from "../components/ChapterReader.vue";
import { api } from "../../../api/client.js";
import { useWorkspaceStore } from "../../../stores/workspace.js";
import { report } from "../../../lib/ui.js";

const workspace = useWorkspaceStore();
const bookId = ref(""), tab = ref("characters"), query = ref(""), loading = ref(false), error = ref("");
const characters = ref([]), facts = ref([]), events = ref([]), relations = ref([]), clues = ref([]), reviews = ref([]);
const factsLoading = reactive({}), expandedCharacters = reactive(new Set()), showReader = ref(false), citation = ref(null);
const text = (value) => String(value || "").toLocaleLowerCase();
const matches = (value) => !query.value.trim() || text(value).includes(text(query.value.trim()));
const filteredCharacters = computed(() => characters.value.filter((item) => matches(`${item.canonical_name} ${aliases(item.aliases_json)}`)));
const filteredEvents = computed(() => events.value.filter((item) => matches(`${item.title} ${item.description}`)));
const filteredRelations = computed(() => relations.value.filter((item) => matches(`${item.subject_id} ${item.relation_type} ${item.object_id}`)));
const filteredClues = computed(() => clues.value.filter((item) => matches(`${item.title} ${item.original_text} ${item.possible_meaning}`)));
const characterFacts = (id) => facts.value.filter((item) => item.entity_id === id && item.state === "active");
function toggleCharacter(id) {
  if (expandedCharacters.has(id)) expandedCharacters.delete(id);
  else expandedCharacters.add(id);
}
function aliases(value) { try { return JSON.parse(value || "[]").join("、"); } catch { return ""; } }
function displayValue(value) { try { const parsed = JSON.parse(value); return Array.isArray(parsed) ? parsed.join("、") : typeof parsed === "object" ? JSON.stringify(parsed) : parsed; } catch { return value; } }
function reviewText(value) { try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; } }
async function load() {
  if (!bookId.value) return;
  loading.value = true; error.value = "";
  try {
    const [characterRows, eventRows, relationRows, clueRows, reviewRows] = await Promise.all([
      api.get(`/books/${bookId.value}/knowledge/characters`), api.get(`/books/${bookId.value}/knowledge/events`),
      api.get(`/books/${bookId.value}/knowledge/relations`), api.get(`/books/${bookId.value}/knowledge/clues`),
      api.get(`/books/${bookId.value}/knowledge/reviews`),
    ]);
    characters.value = characterRows; events.value = eventRows; relations.value = relationRows; clues.value = clueRows; reviews.value = reviewRows;
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
async function removeCharacter(row) { await remove(`/books/${bookId.value}/knowledge/characters/${row.id}`, "确认移除这个人物？"); }
async function removeFact(row) { await remove(`/books/${bookId.value}/knowledge/facts/${row.id}`, "确认删除这个事实版本？"); }
async function removeEvent(row) { await remove(`/books/${bookId.value}/knowledge/events/${row.id}`, "确认删除这个事件？"); }
async function removeRelation(row) { await remove(`/books/${bookId.value}/knowledge/relations/${row.id}`, "确认删除这条关系？"); }
async function removeClue(row) { await remove(`/books/${bookId.value}/knowledge/clues/${row.id}`, "确认删除这个线索？"); }
async function remove(path, message) {
  try { await ElMessageBox.confirm(message, "确认操作", { type: "warning" }); await api.delete(path); ElMessage.success("已更新知识库"); await load(); }
  catch (err) { if (err !== "cancel" && err !== "close") report(err); }
}
async function verifyClue(row) { try { await api.post(`/books/${bookId.value}/knowledge/clues/${row.id}/verify`); ElMessage.success("线索已标记为已验证"); await load(); } catch (err) { report(err); } }
async function resolveReview(row, action) { try { await api.post(`/books/${bookId.value}/knowledge/reviews/${row.id}/resolve`, { action }); ElMessage.success("审核状态已更新"); await load(); } catch (err) { report(err); } }
function openCharacterFacts(row) { tab.value = "characters"; query.value = row.canonical_name; }
function exportData() { const data = JSON.stringify({ characters: characters.value, facts: facts.value, events: events.value, relations: relations.value, clues: clues.value }, null, 2); const blob = new Blob([data], { type: "application/json" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "knowledge.json"; link.click(); URL.revokeObjectURL(link.href); }
watch(() => workspace.selectedId, (value) => { bookId.value = value || ""; load(); }, { immediate: true });
</script>

<style scoped>
.knowledge-summary-head { display:flex; justify-content:space-between; gap:24px; align-items:end; margin:24px 0 12px; }
.knowledge-summary-head h1 { margin:4px 0 8px; }
.knowledge-metrics { display:flex; gap:18px; flex-wrap:wrap; color:#718078; }
.knowledge-metrics strong { display:block; color:#1d4d42; font-size:24px; }
.knowledge-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }
.knowledge-card { padding:18px; border:1px solid #dfe8e2; border-radius:12px; background:#fff; margin:12px 0; }
.card-heading,.card-actions,.relation-record,.review-row,.character-collapsed-row { display:flex; justify-content:space-between; align-items:center; gap:12px; }
.character-collapsed-row { cursor:pointer; min-height:54px; }
.character-title h2 { margin:0; font-size:18px; }
.character-title p { margin:4px 0 0; }
.character-meta { display:flex; align-items:center; gap:10px; white-space:nowrap; }
.frequency { color:#477568; font-size:13px; }
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
.quote-text { padding:12px; background:#f6faf7; border-left:3px solid #82ad9d; color:#4d6258; }
.review-row p { white-space:pre-wrap; max-width:700px; color:#53645c; }
@media (max-width:700px) { .knowledge-summary-head { display:block; } .knowledge-metrics { margin-top:16px; } .fact-row,.review-row { display:block; } .fact-actions { margin-top:8px; } }
</style>
