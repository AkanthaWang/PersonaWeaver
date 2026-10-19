<template>
  <header class="page-header page-header-compact"><BookPicker /></header>
  <div class="toolbar"><el-input v-model="query" placeholder="搜索名称或资料" :prefix-icon="Search" clearable /><el-button :icon="Refresh" :loading="loading" @click="load" aria-label="刷新资料" /><el-button :icon="Connection" :loading="rebuilding" :disabled="!coverage.length || resolving" @click="rebuild">整理已有资料</el-button><el-button :icon="Download" :disabled="!summaries.length" @click="exportData">导出资料</el-button></div>
  <div class="chapter-filter">
    <el-select v-model="sourceChapter" clearable filterable placeholder="全部来源章节" aria-label="来源章节"><el-option v-for="number in coverage" :key="number" :label="`第 ${number} 章`" :value="number" /></el-select>
    <span class="muted">{{ resultCount }} 项结果</span>
  </div>
  <div class="review-bar"><el-checkbox v-model="reviewOnly">仅待确认人物／实体</el-checkbox><span class="muted">待确认 {{ pendingCount }} 项</span></div>
  <el-collapse v-if="warnings.length || pendingResolutions.length" class="knowledge-warnings">
    <el-collapse-item title="待核实问题与失效归并" name="warnings">
      <p v-for="(warning, index) in warnings" :key="index">{{ warning.chapter_title }} · {{ warning.subject }}：{{ warning.query }}</p>
      <div v-for="decision in pendingResolutions" :key="decision.id" class="review-bar"><span>原归并来源已变化 · {{ decision.action === 'merge' ? '合并' : '拆分' }} · {{ decision.created_at }}</span><el-button :icon="Close" text :disabled="resolving" @click="dismiss(decision.id)">忽略</el-button></div>
    </el-collapse-item>
  </el-collapse>
  <el-tabs v-model="viewMode" class="view-tabs">
    <el-tab-pane name="profiles" label="资料档案" />
    <el-tab-pane name="relations" label="人物关系图" />
    <el-tab-pane name="timeline" label="事件时间线" />
    <el-tab-pane name="locations" label="场景地图" />
  </el-tabs>
  <section v-if="viewMode === 'relations'" class="visual-panel relation-panel" v-loading="loading">
    <div class="visual-heading"><h2>人物关系图</h2><el-tag effect="plain">{{ relationEdges.length }} 条关系</el-tag></div>
    <el-empty v-if="!relationNodes.length" description="暂无明确人物关系" />
    <div v-else ref="relationCanvas" class="relation-canvas" @wheel.prevent="zoomGraph" @pointerdown="startPan">
      <svg :viewBox="relationNodes.length <= 6 ? '270 70 360 380' : '0 0 900 520'" role="img" aria-label="人物关系图">
        <defs><marker id="relation-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#77988c" /></marker></defs>
        <g :transform="`translate(${graphPan.x} ${graphPan.y}) scale(${graphZoom})`">
          <g v-for="edge in relationEdges" :key="edge.id">
            <path :d="edgePath(edge)" class="relation-line" marker-end="url(#relation-arrow)" />
            <text :x="edgeLabel(edge).x" :y="edgeLabel(edge).y" class="relation-label">{{ edge.relation }}</text>
          </g>
          <g v-for="node in relationNodes" :key="node.id" class="relation-node" :class="{ focused: focusedCharacter === node.id, unresolved: !node.entry }" role="button" tabindex="0" :aria-label="nodeLabel(node)" @pointerdown.stop="startDrag($event, node)" @click.stop="openCharacter(node, true)" @keydown.enter.prevent="openCharacter(node)" @keydown.space.prevent="openCharacter(node)">
            <title>{{ nodeLabel(node) }}</title>
            <circle :cx="node.x" :cy="node.y" r="34" />
            <text :x="node.x" :y="node.y + 5">{{ node.name.length > 4 ? `${node.name.slice(0, 3)}…` : node.name }}</text>
          </g>
        </g>
      </svg>
      <div class="graph-controls" @pointerdown.stop><el-tooltip content="缩小"><el-button :icon="ZoomOut" size="small" :disabled="graphZoom <= 0.55" aria-label="缩小关系图" @click.stop="setZoom(graphZoom / 1.2)" /></el-tooltip><span>{{ Math.round(graphZoom * 100) }}%</span><el-tooltip content="放大"><el-button :icon="ZoomIn" size="small" :disabled="graphZoom >= 2.4" aria-label="放大关系图" @click.stop="setZoom(graphZoom * 1.2)" /></el-tooltip><el-tooltip content="重置布局"><el-button :icon="Refresh" size="small" aria-label="重置布局" @click.stop="resetGraph" /></el-tooltip></div>
    </div>
    <p v-if="graph.nodes.length > relationNodes.length" class="muted">当前展示 {{ relationNodes.length }} / {{ graph.nodes.length }} 个人物，可筛选章节或搜索人物。</p>
    <div class="relation-legend"><article v-for="edge in relationEdges" :key="`${edge.id}-legend`" class="relation-record"><span>{{ edge.fromName }} → {{ edge.toName }}<strong>{{ edge.relation }}</strong><small v-if="edge.relationCount > 1">多层关系：{{ edge.relations.join(" / ") }}</small></span><el-tag v-if="edge.ambiguous" type="warning" size="small">同名待确认</el-tag><el-button v-if="edge.sources.length" :icon="Reading" text @click="openSource(edge.sources[0])">{{ edge.sources[0].chapter_title }} · 查看原文</el-button><span v-else class="muted">暂无定位依据</span></article></div>
  </section>
  <section v-else-if="viewMode === 'timeline'" class="visual-panel" v-loading="loading">
    <div class="visual-heading"><h2>故事线</h2><el-tag effect="plain">{{ visibleStorylines.length || filteredEvents.length }} 条</el-tag></div>
    <div v-if="visibleStorylines.length" class="story-timeline">
      <article v-for="line in visibleStorylines" :key="line.storyline_id" class="timeline-event">
        <div class="event-heading"><h3>{{ line.title }}</h3><el-tag size="small" effect="plain">{{ line.stage_count || line.stages.length }} 个阶段</el-tag></div>
        <p class="event-description">{{ line.summary }}</p>
        <p class="muted">覆盖章节：{{ line.chapters.map((chapter) => `第 ${chapter} 章`).join("、") }}</p>
        <el-collapse>
          <el-collapse-item :title="`展开主要阶段（${line.stage_count || line.stages.length} 个）`">
            <article v-for="stage in line.stages.slice(0, 4)" :key="stage.stage_id" class="timeline-event">
              <h4>{{ stage.title }}</h4><p class="event-description">{{ stage.summary }}</p>
              <el-button :icon="View" @click="openDetail(eventById(stage.event_id))">查看依据</el-button>
            </article>
          </el-collapse-item>
        </el-collapse>
      </article>
    </div>
    <div v-else-if="storylineStatus === 'pending'" class="muted">故事线尚未整理，当前按事件展示。</div>
    <div v-else-if="timeline.length" class="story-timeline">
      <section v-for="group in timeline" :key="group.chapter_no" class="timeline-chapter">
        <h2><span class="chapter-marker">{{ Number.isFinite(group.chapter_no) && group.chapter_no < Number.MAX_SAFE_INTEGER ? `第 ${group.chapter_no} 章` : '未标注章节' }}</span>{{ group.title }}</h2>
        <article v-for="entry in group.entries" :key="entry.entity_id || entry.name" class="timeline-event">
          <div class="event-heading"><h3>{{ entry.name }}</h3><el-tag v-if="entry.time" size="small" type="info">{{ entry.time }}</el-tag></div>
          <p class="event-description">{{ overview(entry) || '暂无描述' }}</p>
          <div v-if="entry.involved_characters?.length" class="entity-tags"><el-tag v-for="name in entry.involved_characters" :key="name" size="small" type="info">{{ name }}</el-tag></div>
          <el-button :icon="View" @click="openDetail(entry)">查看依据</el-button>
        </article>
      </section>
    </div>
    <el-empty v-else description="暂无事件时间线" />
  </section>
  <section v-else-if="viewMode === 'locations'" class="visual-panel" v-loading="loading">
    <div class="visual-heading"><h2>场景地图</h2><el-tag effect="plain">{{ locationEntries.length }} 个地点</el-tag></div>
    <el-empty v-if="!locationEntries.length" description="暂无地点资料" />
    <div v-else>
      <section v-for="group in locationGroups" :key="group.category" class="location-category">
      <div class="visual-heading"><h3>{{ group.category }}</h3><el-tag effect="plain">{{ group.entries.length }} 项</el-tag></div>
      <div class="location-map">
      <article v-for="(entry, index) in group.entries" :key="entry.entity_id || entry.name" class="location-card">
        <span class="location-pin">{{ index + 1 }}</span><h3>{{ entry.name }}</h3><p>{{ overview(entry) || '暂无场景描述' }}</p>
        <div class="entity-tags"><el-tag v-if="entry.owner" size="small" type="info">归属：{{ entry.owner }}</el-tag><el-tag v-for="name in entry.related_characters?.slice(0, 3) || []" :key="name" size="small" effect="plain">{{ name }}</el-tag></div>
        <el-button :icon="View" @click="openDetail(entry)">查看地点</el-button>
      </article>
    </div>
      </section>
    </div>
  </section>
  <template v-else>
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
        <span class="muted">出现 {{ entry.frequency || entry.evidence?.length || 0 }} 次 · {{ entry.evidence?.length || 0 }} 条章节依据<span v-if="firstChapter(entry) < Number.MAX_SAFE_INTEGER"> · 第 {{ firstChapter(entry) }}<template v-if="entry.last_chapter && entry.last_chapter !== firstChapter(entry)">—{{ entry.last_chapter }}</template> 章</span></span>
        <div class="form-actions"><el-button :icon="View" @click="openDetail(entry)">查看</el-button><el-button v-if="kind === 'characters'" :icon="User" @click="createCard(entry)">创建角色卡</el-button></div>
      </article>
    </div>
  </section>
  </template>
  <el-drawer :model-value="Boolean(detail)" :title="detail?.name" size="min(100vw, 720px)" append-to-body @close="detail = null">
    <section v-if="detail?.synthesis?.length" class="synthesis">
      <h2>综合档案 <el-tag size="small" effect="plain">模型归纳</el-tag></h2>
      <div v-for="(paragraph, index) in detail.synthesis" :key="index"><p>{{ paragraph.text }}</p><div class="fact-links"><el-button v-for="id in paragraph.fact_ids" :key="id" text :icon="Link" @click="scrollToFact(id)">{{ factLabel(id) }}</el-button></div></div>
    </section>
    <section v-else-if="detail" class="synthesis"><h2>{{ detailKind === 'storyline_events' ? '事件经过' : '资料概览' }}</h2><p>{{ overview(detail) || '暂无简介' }}</p></section>
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
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Search, Refresh, Download, View, User, Reading, Connection, Scissor, Link, Close, ZoomIn, ZoomOut } from "@element-plus/icons-vue";
import ChapterReader from "../components/ChapterReader.vue";
import { formatCoverage } from "../coverage";
import { changesFor, filterEntries, firstChapter, orderedEvidence, overview, relationGraph, timelineGroups, worldGroups } from "../knowledge";
import BookPicker from "../../../components/BookPicker.vue";
import { api, saveBlob } from "../../../api/client";
import { useWorkspaceStore } from "../../../stores/workspace";
import { report } from "../../../lib/ui";
const workspace = useWorkspaceStore(), summaries = ref([]), coverage = ref([]), loading = ref(false), query = ref(""), kind = ref("characters"), viewMode = ref("profiles"), detail = ref(null);
const revision = ref(0), pendingCount = ref(0), reviewOnly = ref(false), warnings = ref([]), pendingResolutions = ref([]);
const storylines = ref([]), storylineStatus = ref("pending");
const mergeTarget = ref(""), selectedFacts = ref([]), resolving = ref(false), showReader = ref(false), citation = ref(null);
const cardEntry = ref(null), cardName = ref(""), creating = ref(false);
const sourceChapter = ref(null), rebuilding = ref(false), expandedFacts = ref([]);
const tabs = [{ key: "characters", label: "角色" }, { key: "storyline_events", label: "剧情" }, { key: "items", label: "物品" }, { key: "world_locations", label: "世界与地点" }];
const labels = { summary: "简介", description: "描述", identity: "身份", appearance: "外貌", personality: "性格", speech: "台词", relationships: "关系", key_events: "关键经历", involved_characters: "相关角色", aliases: "称谓与别名", behavior: "行为", state_changes: "状态变化", time: "时间", owner: "归属", significance: "作用", type: "类型", related_characters: "相关角色" };
const entries = (type) => summaries.value.find((summary) => summary.type === type)?.content || [];
const filters = computed(() => ({
  query: query.value, reviewOnly: reviewOnly.value, chapter: sourceChapter.value ?? null,
}));
const visible = computed(() => filterEntries(entries(kind.value), filters.value));
const filteredEvents = computed(() => filterEntries(entries("storyline_events"), filters.value));
const timeline = computed(() => timelineGroups(filteredEvents.value));
const eventById = (id) => entries("storyline_events").find((entry) => entry.entity_id === id) || {};
const visibleStorylines = computed(() => storylines.value.filter((line) => {
  const events = line.stages.map((stage) => eventById(stage.event_id));
  const term = query.value.trim().toLocaleLowerCase();
  return (!term || JSON.stringify(line).toLocaleLowerCase().includes(term))
    && (sourceChapter.value == null || events.some((event) => filterEntries([event], filters.value).length));
}));
const characterEntries = computed(() => entries("characters"));
const locationEntries = computed(() => filterEntries(entries("world_locations"), filters.value));
const locationGroups = computed(() => worldGroups(entries("world_locations"), filters.value));
const graph = computed(() => relationGraph(characterEntries.value, filters.value));
const resultCount = computed(() => viewMode.value === "relations" ? graph.value.nodes.length :
  viewMode.value === "locations" ? locationEntries.value.length : viewMode.value === "timeline" ? filteredEvents.value.length : visible.value.length);
const graphNodes = ref([]);
const graphPan = reactive({ x: 0, y: 0 });
const graphZoom = ref(1);
const relationCanvas = ref(null);
const focusedCharacter = ref("");
let animationFrame = 0, dragState = null, panState = null, suppressClickUntil = 0;
const relationNodes = computed(() => graphNodes.value);
const relationEdges = computed(() => {
  const known = new Set(relationNodes.value.map((node) => node.id));
  return graph.value.edges.filter((edge) => known.has(edge.from) && known.has(edge.to));
});
const nodePosition = (id) => relationNodes.value.find((node) => node.id === id) || { x: 0, y: 0 };
const nodeLabel = (node) => `${node.name} · ${node.entry?.identity || (node.ambiguous ? "同名待确认" : node.entry ? `第 ${firstChapter(node.entry)} 章` : "暂无人物档案")}`;
const detailKind = computed(() => detail.value?.kind || tabs.find((tab) => entries(tab.key).includes(detail.value))?.key || kind.value);
const evidence = computed(() => orderedEvidence(detail.value));
const changes = computed(() => changesFor(detail.value));
const mergeCandidates = computed(() => entries(detailKind.value).filter((entry) => entry.entity_id && entry.entity_id !== detail.value?.entity_id));
const fields = (entry) => Object.entries(entry || {}).filter(([key, value]) => labels[key] && value && (!Array.isArray(value) || value.length));
const format = (value) => typeof value === "string" ? value : Array.isArray(value) ? value.map(format).join("\n") :
  value?.target_name ? `${value.target_name}：${value.relation}` : JSON.stringify(value, null, 2);
function resetGraph() {
  endDrag(); endPan();
  const nodes = graph.value.nodes.slice(0, 40);
  graphNodes.value = nodes.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(nodes.length, 1) - Math.PI / 2;
    return { ...node, x: 450 + Math.cos(angle) * (nodes.length <= 6 ? 120 : 250), y: 260 + Math.sin(angle) * (nodes.length <= 6 ? 100 : 150), vx: 0, vy: 0, fixed: false };
  });
  graphPan.x = 0; graphPan.y = 0; graphZoom.value = 1; focusedCharacter.value = "";
  startSimulation();
}
function startSimulation() {
  cancelAnimationFrame(animationFrame);
  let iterations = 0;
  const tick = () => {
    if (!graphNodes.value.length || viewMode.value !== "relations") return;
    const nodes = graphNodes.value;
    nodes.forEach((node, index) => {
      if (node.fixed) return;
      let forceX = (450 - node.x) * 0.002, forceY = (260 - node.y) * 0.002;
      nodes.forEach((other, otherIndex) => {
        if (index === otherIndex) return;
        const dx = node.x - other.x, dy = node.y - other.y;
        const distance = Math.max(Math.hypot(dx, dy), 1);
        if (distance < 150) {
          const force = (150 - distance) / distance * 0.08;
          forceX += dx * force; forceY += dy * force;
        }
      });
      relationEdges.value.filter((edge) => edge.from === node.id || edge.to === node.id).forEach((edge) => {
        const other = nodePosition(edge.from === node.id ? edge.to : edge.from);
        const dx = other.x - node.x, dy = other.y - node.y;
        const distance = Math.max(Math.hypot(dx, dy), 1);
        const force = (distance - 180) * 0.0008;
        forceX += dx * force; forceY += dy * force;
      });
      node.vx = (node.vx + forceX) * 0.88; node.vy = (node.vy + forceY) * 0.88;
      node.x = Math.min(860, Math.max(40, node.x + node.vx));
      node.y = Math.min(480, Math.max(40, node.y + node.vy));
    });
    if (++iterations < 240) animationFrame = requestAnimationFrame(tick);
  };
  animationFrame = requestAnimationFrame(tick);
}
function graphPoint(event) {
  const svg = relationCanvas.value?.querySelector("svg"), matrix = svg?.getScreenCTM();
  if (!matrix) return { x: 450, y: 260 };
  const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
  return { x: (point.x - graphPan.x) / graphZoom.value, y: (point.y - graphPan.y) / graphZoom.value };
}
function startDrag(event, node) {
  if (event.button !== 0) return;
  dragState = { node, offset: graphPoint(event), startX: event.clientX, startY: event.clientY, moved: false };
  node.fixed = true;
  focusedCharacter.value = node.id;
  window.addEventListener("pointermove", moveDrag);
  window.addEventListener("pointerup", endDrag, { once: true });
  window.addEventListener("pointercancel", endDrag, { once: true });
}
function moveDrag(event) {
  if (!dragState) return;
  if (Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY) > 4) dragState.moved = true;
  const point = graphPoint(event);
  dragState.node.x += point.x - dragState.offset.x;
  dragState.node.y += point.y - dragState.offset.y;
  dragState.offset = point;
}
function endDrag() {
  if (dragState?.moved) suppressClickUntil = performance.now() + 200;
  if (dragState) dragState.node.fixed = false;
  dragState = null;
  window.removeEventListener("pointermove", moveDrag);
  window.removeEventListener("pointerup", endDrag);
  window.removeEventListener("pointercancel", endDrag);
}
function startPan(event) {
  if (event.button !== 0 || event.target.closest(".relation-node")) return;
  panState = { point: graphPoint(event) };
  window.addEventListener("pointermove", movePan);
  window.addEventListener("pointerup", endPan, { once: true });
  window.addEventListener("pointercancel", endPan, { once: true });
}
function movePan(event) {
  if (!panState) return;
  const point = graphPoint(event);
  graphPan.x += (point.x - panState.point.x) * graphZoom.value;
  graphPan.y += (point.y - panState.point.y) * graphZoom.value;
}
function endPan() {
  panState = null;
  window.removeEventListener("pointermove", movePan);
  window.removeEventListener("pointerup", endPan);
  window.removeEventListener("pointercancel", endPan);
}
function setZoom(value, point = { x: (450 - graphPan.x) / graphZoom.value, y: (260 - graphPan.y) / graphZoom.value }) {
  const zoom = Math.min(2.4, Math.max(0.55, value)), previous = graphZoom.value;
  graphPan.x += point.x * (previous - zoom); graphPan.y += point.y * (previous - zoom);
  graphZoom.value = zoom;
}
function zoomGraph(event) { setZoom(graphZoom.value * (event.deltaY > 0 ? 0.9 : 1.1), graphPoint(event)); }
function edgePath(edge) {
  const from = nodePosition(edge.from), to = nodePosition(edge.to);
  const dx = to.x - from.x, dy = to.y - from.y, distance = Math.max(Math.hypot(dx, dy), 1);
  const start = { x: from.x + dx / distance * 37, y: from.y + dy / distance * 37 };
  const end = { x: to.x - dx / distance * 41, y: to.y - dy / distance * 41 };
  const bend = edgeBend(edge);
  return `M ${start.x} ${start.y} Q ${(from.x + to.x) / 2 - dy * bend} ${(from.y + to.y) / 2 + dx * bend} ${end.x} ${end.y}`;
}
function edgeBend(edge) { return 0.14 + relationEdges.value.filter((item) => item.from === edge.from && item.to === edge.to).findIndex((item) => item.id === edge.id) * 0.16; }
function edgeLabel(edge) {
  const from = nodePosition(edge.from), to = nodePosition(edge.to), bend = edgeBend(edge) / 2;
  return { x: (from.x + to.x) / 2 - (to.y - from.y) * bend, y: (from.y + to.y) / 2 + (to.x - from.x) * bend - 5 };
}
let generation = 0;
async function load() {
  const bookId = workspace.selectedId, current = ++generation;
  summaries.value = []; coverage.value = []; detail.value = null; pendingCount.value = 0; warnings.value = []; pendingResolutions.value = []; storylines.value = []; storylineStatus.value = "pending"; showReader.value = false; cardEntry.value = null;
  loading.value = false; revision.value = 0;
  if (!bookId) return;
  loading.value = true;
  try {
    const result = await api.get("/summaries", { params: { book_id: bookId } });
    if (current === generation) { summaries.value = result.summaries; coverage.value = result.coverage || []; revision.value = result.revision; pendingCount.value = result.pending_count; warnings.value = result.warnings || []; pendingResolutions.value = result.pending_resolutions || []; storylines.value = result.storylines || []; storylineStatus.value = result.storyline_status || "pending"; if (!coverage.value.includes(sourceChapter.value)) sourceChapter.value = null; }
  } catch (error) { if (current === generation) report(error); } finally { if (current === generation) loading.value = false; }
}
function createCard(entry) { cardEntry.value = entry; cardName.value = entry.name; }
async function submitCard() {
  if (creating.value || !cardEntry.value) return;
  creating.value = true;
  try { const entry = cardEntry.value; await api.post("/cards", { book_id: workspace.selectedId, name: cardName.value, source_entity_id: entry.entity_id || null, intro: overview(entry).slice(0, 4000) }); cardEntry.value = null; ElMessage.success("角色卡已创建"); }
  catch (error) { report(error); } finally { creating.value = false; }
}
function openDetail(entry) { detail.value = entry; selectedFacts.value = []; mergeTarget.value = ""; expandedFacts.value = [orderedEvidence(entry)[0]?.fact_id || 0]; }
function openCharacter(node, pointer = false) { if (pointer && performance.now() < suppressClickUntil) return; focusedCharacter.value = node.id; if (node.entry) openDetail(node.entry); }
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
watch([graph, viewMode], () => { if (viewMode.value === "relations") resetGraph(); else { cancelAnimationFrame(animationFrame); endDrag(); endPan(); } });
onMounted(async () => { try { await workspace.refresh(); await load(); } catch (error) { report(error); } });
onBeforeUnmount(() => {
  cancelAnimationFrame(animationFrame);
  endDrag(); endPan();
});
</script>
<style scoped>
.coverage { max-width: 700px; overflow-wrap: anywhere; font-size: 12px; color: #718078; }
.view-tabs { margin-top: 18px; }
.visual-panel { min-height: 260px; padding: 18px 0 8px; }
.visual-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }
.visual-heading h2 { margin: 0 0 6px; }
.relation-canvas { position: relative; overflow: hidden; border: 1px solid #dce8e2; border-radius: 8px; background: #fafcfb; cursor: grab; touch-action: none; }
.relation-canvas:active { cursor: grabbing; }
.relation-canvas > svg { display: block; width: 100%; height: 420px; }
.relation-line { stroke: #9abaae; stroke-width: 1.5; fill: none; }
.relation-label { fill: #557567; font-size: 12px; text-anchor: middle; paint-order: stroke; stroke: #fafcfb; stroke-width: 4px; }
.relation-node { cursor: pointer; }
.relation-node circle { fill: #548f7e; stroke: #e5f0eb; stroke-width: 5; transition: fill .15s ease; }
.relation-node:hover circle { fill: #326c5b; }
.relation-node.focused circle { fill: #d47a56; stroke: #fff1e8; }
.relation-node:focus-visible circle { stroke: #286fa7; }
.relation-node.unresolved circle { fill: #7b8492; stroke-dasharray: 4 3; }
.relation-node text { fill: #fff; font-size: 15px; text-anchor: middle; pointer-events: none; }
.graph-controls { display: flex; justify-content: flex-end; align-items: center; gap: 8px; padding: 8px 12px; border-top: 1px solid #dce8e2; background: #fff; color: #557567; font-size: 12px; }
.relation-legend { margin-top: 12px; max-height: 320px; overflow-y: auto; }
.relation-record { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 10px 0; border-bottom: 1px solid var(--pw-border); font-size: 13px; overflow-wrap: anywhere; }
.relation-record strong { margin-left: 12px; color: #487567; }
.relation-record .el-button { max-width: 100%; height: auto; white-space: normal; text-align: left; }
.location-map { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; padding: 12px 0 24px; background-image: linear-gradient(#e7f0eb 1px, transparent 1px), linear-gradient(90deg, #e7f0eb 1px, transparent 1px); background-size: 36px 36px; }
.location-card { position: relative; min-height: 140px; min-width: 0; padding: 20px 18px 16px 22px; border: 1px solid #cfdfd7; border-radius: 8px; background: #fff; }
.location-card h3 { margin-top: 0; }
.location-card p { line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.location-pin { position: absolute; top: -9px; left: -9px; display: grid; place-items: center; width: 25px; height: 25px; border-radius: 50%; color: #fff; background: #d47a56; font-size: 12px; }
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
@media (max-width: 600px) { .relation-canvas > svg { height: 320px; } }
</style>
