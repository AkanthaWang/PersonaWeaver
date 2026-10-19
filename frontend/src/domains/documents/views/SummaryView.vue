<template>
  <header class="page-header"><div><h1>作品资料</h1><p class="muted">已提取 {{ coverage.length }} / {{ workspace.selected?.chapter_count || 0 }} 个章节 · 版本 {{ revision }}</p><p v-if="coverage.length" class="coverage">覆盖章节：{{ formatCoverage(coverage) }}</p></div><BookPicker /></header>
  <div class="toolbar"><el-input v-model="query" placeholder="搜索名称或资料" :prefix-icon="Search" clearable /><el-button :icon="Refresh" :loading="loading" @click="load" aria-label="刷新资料" /><el-button :icon="Connection" :loading="rebuilding" :disabled="!coverage.length || resolving" @click="rebuild">整理已有资料</el-button><el-button :icon="Download" :disabled="!summaries.length" @click="exportData">导出资料</el-button></div>
  <div class="chapter-filter">
    <el-select v-model="sourceChapter" clearable filterable placeholder="全部来源章节" aria-label="来源章节"><el-option v-for="number in coverage" :key="number" :label="`第 ${number} 章`" :value="number" /></el-select>
    <span class="muted">{{ kind === 'storyline_events' ? '按章节与原文先后排列' : `${visible.length} 份档案` }}</span>
  </div>
  <div class="review-bar"><el-checkbox v-model="reviewOnly">仅待确认人物／实体</el-checkbox><span class="muted">待确认 {{ pendingCount }} 项</span></div>
  <el-collapse v-if="warnings.length || pendingResolutions.length" class="knowledge-warnings">
    <el-collapse-item title="待核实问题与失效归并" name="warnings">
      <p v-for="(warning, index) in warnings" :key="index">{{ warning.chapter_title }} · {{ warning.subject }}：{{ warning.query }}</p>
      <div v-for="decision in pendingResolutions" :key="decision.id" class="review-bar"><span>原归并来源已变化 · {{ decision.action === 'merge' ? '合并' : '拆分' }} · {{ decision.created_at }}</span><el-button :icon="Close" text :disabled="resolving" @click="dismiss(decision.id)">忽略</el-button></div>
    </el-collapse-item>
  </el-collapse>
  <el-tabs v-model="kind">
    <el-tab-pane v-for="tab in tabs" :key="tab.key" :name="tab.key" :label="`${tab.label} (${entries(tab.key).length})`" />
  </el-tabs>
  <section v-loading="loading">
    <el-empty v-if="!visible.length && !loading" :description="workspace.selectedId ? '暂无资料' : '尚未选择作品'" />
    <div v-if="kind === 'storyline_events'" class="story-timeline">
      <section v-for="group in timeline" :key="group.chapter_no" class="timeline-chapter">
        <h2><span class="chapter-marker">{{ Number.isFinite(group.chapter_no) && group.chapter_no < Number.MAX_SAFE_INTEGER ? `第 ${group.chapter_no} 章` : '未标注章节' }}</span>{{ group.title }}</h2>
        <article v-for="entry in group.entries" :key="entry.entity_id || entry.name" class="timeline-event">
          <div class="event-heading"><h3>{{ entry.name }}</h3><el-tag v-if="entry.type" size="small" effect="plain">{{ entry.type }}</el-tag><el-tag v-if="entry.time" size="small" type="info">{{ entry.time }}</el-tag></div>
          <p class="event-description">{{ overview(entry) || '暂无描述' }}</p>
          <div v-if="entry.involved_characters?.length" class="entity-tags"><el-tag v-for="name in entry.involved_characters" :key="name" size="small" type="info">{{ name }}</el-tag></div>
          <div class="form-actions"><el-button :icon="View" @click="openDetail(entry)">查看</el-button><el-button v-if="entry.evidence?.[0]?.sources?.[0]" :icon="Reading" text @click="openSource(entry.evidence[0].sources[0])">查看原文</el-button></div>
        </article>
      </section>
    </div>
    <div v-else class="asset-grid">
      <article v-for="entry in visible" :key="entry.entity_id || entry.name" class="asset-item">
        <h3>{{ entry.name }} <el-tag v-if="entry.needs_review" size="small" type="warning">待确认</el-tag></h3><p class="excerpt">{{ overview(entry) || '暂无简介' }}</p>
        <div class="entity-tags"><el-tag v-if="entry.identity || entry.type" size="small" effect="plain">{{ entry.identity || entry.type }}</el-tag><el-tag v-if="entry.owner" size="small" type="info">归属：{{ entry.owner }}</el-tag></div>
        <span class="muted">{{ entry.evidence?.length || 0 }} 条章节依据<span v-if="firstChapter(entry) < Number.MAX_SAFE_INTEGER"> · 第 {{ firstChapter(entry) }}<template v-if="entry.last_chapter && entry.last_chapter !== firstChapter(entry)">—{{ entry.last_chapter }}</template> 章</span></span>
        <div class="form-actions"><el-button :icon="View" @click="openDetail(entry)">查看</el-button><el-button v-if="kind === 'characters'" :icon="User" @click="createCard(entry)">创建角色卡</el-button></div>
      </article>
    </div>
  </section>
  <el-drawer :model-value="Boolean(detail)" :title="detail?.name" size="min(100vw, 720px)" append-to-body @close="detail = null">
    <section v-if="detail?.synthesis?.length" class="synthesis">
      <h2>综合档案 <el-tag size="small" effect="plain">模型归纳</el-tag></h2>
      <div v-for="(paragraph, index) in detail.synthesis" :key="index"><p>{{ paragraph.text }}</p><div class="fact-links"><el-button v-for="id in paragraph.fact_ids" :key="id" text :icon="Link" @click="scrollToFact(id)">{{ factLabel(id) }}</el-button></div></div>
    </section>
    <section v-else-if="detail" class="synthesis"><h2>{{ kind === 'storyline_events' ? '事件经过' : '资料概览' }}</h2><p>{{ overview(detail) || '暂无简介' }}</p></section>
    <dl class="detail-fields"><template v-for="[key, value] in fields(detail).filter(([key]) => !['summary', 'description'].includes(key))" :key="key"><dt>{{ labels[key] || key }}</dt><dd>{{ format(value) }}</dd></template></dl>
    <section v-if="changes.length" class="entity-history">
      <h2>按章变化</h2>
      <el-timeline><el-timeline-item v-for="(change, index) in changes" :key="index" :timestamp="change.chapter || `第 ${change.chapter_no} 章`" placement="top">
        <strong>{{ labels[change.field] }}</strong><p>{{ format(change.value) }}</p><el-button v-for="id in change.fact_ids" :key="id" text :icon="Link" @click="scrollToFact(id)">查看依据</el-button>
      </el-timeline-item></el-timeline>
    </section>
    <div v-if="detail?.entity_id" class="resolution-controls">
      <el-select v-model="mergeTarget" filterable placeholder="选择要合并的实体" aria-label="选择要合并的实体"><el-option v-for="entry in mergeCandidates" :key="entry.entity_id" :label="`${entry.name} · ${entry.identity || entry.evidence?.[0]?.chapter || ''}`" :value="entry.entity_id" /></el-select>
      <el-button :icon="Connection" :disabled="!mergeTarget || resolving" @click="resolve('merge')">合并</el-button>
      <el-button :icon="Scissor" :disabled="!selectedFacts.length || selectedFacts.length >= (detail.source_ids?.length || 0) || resolving" @click="resolve('split')">拆分选中来源</el-button>
    </div>
    <h2 class="spaced">按章事实与原文依据</h2>
    <el-collapse v-model="expandedFacts">
    <el-collapse-item v-for="(item, index) in evidence" :key="item.fact_id || index" :name="item.fact_id || index" :title="`${item.chapter || '章节依据'} · ${index + 1}`">
    <section :id="`fact-${item.fact_id}`" class="evidence">
      <div class="review-bar"><el-checkbox v-if="item.fact_id" v-model="selectedFacts" :value="item.fact_id" :aria-label="`选择来源 ${index + 1}`" /><h3>{{ item.chapter }}</h3></div>
      <dl class="detail-fields"><template v-for="[key, value] in fields(item)" :key="key"><dt>{{ labels[key] || key }}</dt><dd>{{ format(value) }}</dd></template></dl>
      <div v-for="(source, sourceIndex) in item.sources || []" :key="sourceIndex" class="source-quote">
        <blockquote>{{ source.quote }}</blockquote><el-button text :icon="Reading" @click="openSource(source)">{{ source.chapter_title }} · 查看原文</el-button>
      </div>
      <el-button v-if="!item.sources?.length && item.chapter_id" text :icon="Reading" @click="openSource({ chapter_id: item.chapter_id })">查看章节</el-button>
    </section>
    </el-collapse-item>
    </el-collapse>
  </el-drawer>
  <ChapterReader v-model="showReader" :book-id="workspace.selectedId" :citation="citation" :chapter-id="citation?.chapter_id" :title="workspace.selected?.title" />
  <el-dialog :model-value="Boolean(cardEntry)" title="创建角色卡" width="min(92vw, 440px)" @close="cardEntry = null">
    <el-form @submit.prevent="submitCard"><el-form-item label="角色卡名称"><el-input v-model="cardName" maxlength="100" /></el-form-item></el-form>
    <template #footer><el-button @click="cardEntry = null">取消</el-button><el-button type="primary" :icon="User" :loading="creating" :disabled="!cardName.trim()" @click="submitCard">创建角色卡</el-button></template>
  </el-dialog>
</template>
<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Refresh, Download, View, User, Reading, Connection, Scissor, Link, Close } from "@element-plus/icons-vue";
import ChapterReader from "../components/ChapterReader.vue";
import { formatCoverage } from "../coverage";
import { changesFor, filterEntries, firstChapter, orderedEvidence, overview, timelineGroups } from "../knowledge";
import BookPicker from "../../../components/BookPicker.vue";
import { api, saveBlob } from "../../../api/client";
import { useWorkspaceStore } from "../../../stores/workspace";
import { report } from "../../../lib/ui";
const workspace = useWorkspaceStore(), summaries = ref([]), coverage = ref([]), loading = ref(false), query = ref(""), kind = ref("characters"), detail = ref(null);
const revision = ref(0), pendingCount = ref(0), reviewOnly = ref(false), warnings = ref([]), pendingResolutions = ref([]);
const mergeTarget = ref(""), selectedFacts = ref([]), resolving = ref(false), showReader = ref(false), citation = ref(null);
const cardEntry = ref(null), cardName = ref(""), creating = ref(false);
const sourceChapter = ref(null), rebuilding = ref(false), expandedFacts = ref([]);
const tabs = [{ key: "characters", label: "角色" }, { key: "storyline_events", label: "剧情" }, { key: "items", label: "物品" }, { key: "world_locations", label: "世界与地点" }];
const labels = { summary: "简介", description: "描述", identity: "身份", appearance: "外貌", personality: "性格", speech: "台词", relationships: "关系", key_events: "关键经历", involved_characters: "相关角色", aliases: "称谓与别名", behavior: "行为", state_changes: "状态变化", time: "时间", owner: "归属", significance: "作用", type: "类型", related_characters: "相关角色" };
const entries = (type) => summaries.value.find((summary) => summary.type === type)?.content || [];
const visible = computed(() => filterEntries(entries(kind.value), { query: query.value, reviewOnly: reviewOnly.value, chapter: sourceChapter.value ?? null }));
const timeline = computed(() => timelineGroups(visible.value));
const evidence = computed(() => orderedEvidence(detail.value));
const changes = computed(() => changesFor(detail.value));
const mergeCandidates = computed(() => entries(kind.value).filter((entry) => entry.entity_id && entry.entity_id !== detail.value?.entity_id));
const fields = (entry) => Object.entries(entry || {}).filter(([key, value]) => labels[key] && value && (!Array.isArray(value) || value.length));
const format = (value) => typeof value === "string" ? value : Array.isArray(value) ? value.map(format).join("\n") :
  value?.target_name ? `${value.target_name}：${value.relation}` : JSON.stringify(value, null, 2);
let generation = 0;
async function load() {
  const bookId = workspace.selectedId, current = ++generation;
  summaries.value = []; coverage.value = []; detail.value = null; pendingCount.value = 0; warnings.value = []; pendingResolutions.value = []; showReader.value = false; cardEntry.value = null;
  loading.value = false; revision.value = 0;
  if (!bookId) return;
  loading.value = true;
  try {
    const result = await api.get("/summaries", { params: { book_id: bookId } });
    if (current === generation) { summaries.value = result.summaries; coverage.value = result.coverage || []; revision.value = result.revision; pendingCount.value = result.pending_count; warnings.value = result.warnings || []; pendingResolutions.value = result.pending_resolutions || []; if (!coverage.value.includes(sourceChapter.value)) sourceChapter.value = null; }
  } catch (error) { report(error); } finally { if (current === generation) loading.value = false; }
}
function createCard(entry) { cardEntry.value = entry; cardName.value = entry.name; }
async function submitCard() {
  if (creating.value || !cardEntry.value) return;
  creating.value = true;
  try { const entry = cardEntry.value; await api.post("/cards", { book_id: workspace.selectedId, name: cardName.value, source_entity_id: entry.entity_id || null, intro: overview(entry).slice(0, 4000) }); cardEntry.value = null; ElMessage.success("角色卡已创建"); }
  catch (error) { report(error); } finally { creating.value = false; }
}
function openDetail(entry) { detail.value = entry; selectedFacts.value = []; mergeTarget.value = ""; expandedFacts.value = [orderedEvidence(entry)[0]?.fact_id || 0]; }
function openSource(source) { citation.value = source; showReader.value = true; }
async function scrollToFact(id) { if (!expandedFacts.value.includes(id)) expandedFacts.value.push(id); await nextTick(); document.getElementById(`fact-${id}`)?.scrollIntoView({ block: "start", behavior: "smooth" }); }
function factLabel(id) { const fact = detail.value?.evidence?.find((item) => item.fact_id === id); return fact?.chapter || "事实依据"; }
async function resolve(action) {
  const entry = detail.value, target = mergeCandidates.value.find((item) => item.entity_id === mergeTarget.value);
  try { await ElMessageBox.confirm(action === "merge" ? `确认将“${entry.name}”与“${target?.name}”合并？` : "确认将选中的来源拆分为独立实体？", "确认归并修改", { type: "warning", confirmButtonText: "确定", cancelButtonText: "取消", customClass: "knowledge-confirm" }); }
  catch { return; }
  resolving.value = true;
  try {
    await api.post(`/books/${workspace.selectedId}/entity-resolutions`, { revision: revision.value, action,
      source_ids: action === "split" ? selectedFacts.value : entry.source_ids,
      other_source_ids: action === "merge" ? target.source_ids : [] });
    await load(); ElMessage.success("资料归并已更新");
  } catch (error) { report(error); } finally { resolving.value = false; }
}
async function dismiss(id) {
  resolving.value = true;
  try { await api.delete(`/books/${workspace.selectedId}/entity-resolutions/${id}`, { params: { revision: revision.value } }); await load(); }
  catch (error) { report(error); } finally { resolving.value = false; }
}
async function rebuild() {
  if (!workspace.selectedId || rebuilding.value) return;
  const bookId = workspace.selectedId;
  rebuilding.value = true;
  try {
    await api.post(`/books/${bookId}/rebuild-knowledge`, null, { params: { revision: revision.value } });
    if (bookId === workspace.selectedId) { await load(); ElMessage.success("已有资料已整理"); }
  } catch (error) { report(error); } finally { rebuilding.value = false; }
}
function exportData() { saveBlob(new Blob([JSON.stringify(summaries.value, null, 2)], { type: "application/json;charset=utf-8" }), `${workspace.selected?.title || '资料'}.json`); }
watch(() => workspace.selectedId, load);
watch(kind, () => { detail.value = null; });
onMounted(async () => { try { await workspace.refresh(); await load(); } catch (error) { report(error); } });
</script>
<style scoped>
.coverage { max-width: 700px; overflow-wrap: anywhere; font-size: 12px; color: #718078; }
.asset-item { border-radius: 8px; }
.chapter-filter { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin: 14px 0; }
.chapter-filter .el-select { width: 200px; max-width: 100%; }
.entity-tags, .event-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.entity-tags .el-tag, .event-heading .el-tag { max-width: 100%; height: auto; white-space: normal; overflow-wrap: anywhere; }
.timeline-chapter { padding: 12px 0 20px; }
.timeline-chapter > h2 { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 16px; overflow-wrap: anywhere; }
.chapter-marker { font-size: 12px; font-weight: 500; color: #487567; }
.timeline-event { position: relative; border-left: 2px solid #d4e2dc; padding: 0 0 24px 24px; margin-left: 6px; }
.timeline-event::before { content: ""; position: absolute; width: 8px; height: 8px; border-radius: 50%; background: #548f7e; left: -5px; top: 12px; }
.event-heading h3 { overflow-wrap: anywhere; }
.event-description, .entity-history p { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.8; margin: 4px 0 12px; }
.entity-history { margin: 24px 0; }
.entity-history .el-timeline { padding-left: 4px; margin-top: 20px; }
.story-timeline { max-width: 1000px; }
.review-bar, .fact-links { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.review-bar { margin: 10px 0; }
.knowledge-warnings { margin: 12px 0; }
.synthesis { border-bottom: 1px solid #dde5e0; padding-bottom: 16px; margin-bottom: 20px; }
.synthesis p { line-height: 1.9; overflow-wrap: anywhere; margin: 16px 0 4px; }
h2 { font-size: 18px; } h3 { font-size: 15px; margin: 8px 0; }
.resolution-controls { display: flex; flex-wrap: wrap; gap: 8px; padding: 18px 0; border-block: 1px solid #dde5e0; }
.resolution-controls .el-select { width: min(100%, 260px); }
.evidence { scroll-margin-top: 12px; overflow-wrap: anywhere; }
.evidence:target { background: #f3f7f4; }
.source-quote blockquote { margin: 12px 0 2px; padding: 10px 14px; border-left: 3px solid #548f7e; background: #f2f6f4; white-space: pre-wrap; }
.source-quote .el-button { max-width: 100%; height: auto; white-space: normal; text-align: left; }
.detail-fields dd { white-space: pre-wrap; overflow-wrap: anywhere; }
:global(.el-message-box.knowledge-confirm) { width: min(420px, calc(100vw - 32px)); border-radius: 8px; }
</style>
