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
      <div class="character-tags">
        <span v-if="characterIdentity(character)" class="character-tag">身份 · {{ characterIdentity(character) }}</span>
        <span v-if="character.first_chapter" class="character-tag">第 {{ character.first_chapter }} 章登场</span>
        <span class="character-tag">{{ relationsOf(character).length }} 位关联人物</span>
      </div>
      <section class="character-profile">
        <p class="character-profile-label">档案描述</p>
        <p class="character-intro" :class="{ placeholder: !characterIntro(character) }">{{ characterIntro(character) || '暂无档案描述，打开详情可根据已有事实生成。' }}</p>
      </section>
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
      <span class="muted">{{ groupedRelations.length }} 组关系 · {{ characterNameCount }} 位人物</span>
    </div>

    <div v-show="relationView === 'graph'" class="relation-graph-wrap">
      <el-empty v-if="!filteredCharacters.length" description="暂无人物资料" />
      <div v-show="filteredCharacters.length" ref="graphEl" class="relation-graph">
        <div v-if="filteredRelations.length" class="relation-graph-legend">
          <span v-for="item in relationLegend" :key="item.key"><i :style="{ backgroundColor: item.color }" />{{ item.label }}</span>
        </div>
      </div>
      <p v-if="filteredCharacters.length" class="graph-hint muted">圆形头像为人物；无关系人物会单独陈列。拖拽节点可调整位置，滚轮缩放画布，拖拽空白处平移。</p>
    </div>

    <div v-show="relationView === 'list'">
      <el-empty v-if="!filteredRelations.length" description="暂无人物关系" />
      <article v-for="relation in groupedRelations" :key="relation.id" class="relation-record">
        <div class="relation-pair">
          <strong>{{ characterName(relation.subject_id) }}</strong>
          <span class="muted">与</span>
          <strong>{{ characterName(relation.object_id) }}</strong>
          <span class="relation-labels" :title="relationDirections(relation)">{{ relation.labels.join('、') }}</span>
        </div>
        <el-button link type="danger" @click="removeRelationGroup(relation)">删除</el-button>
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

  <el-drawer v-model="detailOpen" :title="detail?.canonical_name || '人物详情'" size="660px" class="character-drawer">
    <template v-if="detail">
      <div class="drawer-profile">
        <img class="drawer-avatar" :src="characterAvatarUrl(detail.canonical_name)" :alt="`${detail.canonical_name}头像`" />
        <div class="drawer-profile-content">
          <p class="drawer-profile-kicker">人物档案</p>
          <h2 class="drawer-profile-name">{{ detail.canonical_name }}</h2>
          <p class="drawer-profile-alias">{{ aliases(detail.aliases_json) || '暂无别名' }}</p>
          <div class="drawer-profile-meta">
            <el-tag size="small" :type="detail.state === 'active' ? 'success' : 'info'">{{ detail.state }}</el-tag>
            <span><strong>{{ detail.frequency || 0 }}</strong> 次出现</span>
            <span v-if="detail.first_chapter">第 {{ detail.first_chapter }} 章登场</span>
          </div>
        </div>
      </div>
      <section class="drawer-section profile-description">
        <div class="section-heading">
          <h3>档案描述</h3>
          <el-button link type="primary" :loading="synthesisBusy" @click="regenerateProfile">{{ detailProfile ? '重新生成' : '生成档案描述' }}</el-button>
        </div>
        <p v-if="detailProfile" class="profile-text">{{ detailProfile }}</p>
        <p v-else class="profile-empty">暂无档案描述，可根据已有事实生成约 200 字的整体介绍。</p>
      </section>
      <section class="drawer-section profile-facts">
        <div><span>身份</span><strong>{{ detailIdentity || '暂无记录' }}</strong></div>
        <div><span>登场章节</span><strong>{{ detail.first_chapter ? `第 ${detail.first_chapter} 章` : '暂无记录' }}</strong></div>
        <div><span>活跃至</span><strong>{{ detail.last_chapter ? `第 ${detail.last_chapter} 章` : '暂无记录' }}</strong></div>
        <div><span>出现次数</span><strong>{{ detail.frequency || 0 }} 次</strong></div>
        <div><span>关联人物</span><strong>{{ detailRelations.length }} 位</strong></div>
        <div><span>状态</span><strong>{{ detail.state || '暂无记录' }}</strong></div>
      </section>
      <section class="drawer-section">
        <div class="section-heading"><h3>人物大事</h3><span class="muted">{{ detailMilestones.length }} 项</span></div>
        <el-empty v-if="!detailMilestones.length" :image-size="50" description="暂无重要经历" />
        <ol v-else class="milestone-list">
          <li v-for="milestone in visibleMilestones" :key="milestone.id">
            <p>{{ clip(milestone.text, 90) }}</p>
            <div class="milestone-chapters">
              <el-button v-if="milestone.chapters[0]?.chapter_id" link type="primary" :title="milestone.chapters[0].chapter_title || ''" @click="openMilestoneChapter(milestone.chapters[0])">
                {{ milestone.chapters[0].chapter_no != null ? `第 ${milestone.chapters[0].chapter_no} 章` : milestone.chapters[0].chapter_title || '相关章节' }}
              </el-button>
              <span v-else-if="milestone.chapters[0]">
                {{ milestone.chapters[0].chapter_no != null ? `第 ${milestone.chapters[0].chapter_no} 章` : milestone.chapters[0].chapter_title }}
              </span>
              <span v-else>章节未标注</span>
            </div>
          </li>
        </ol>
        <el-button v-if="detailMilestones.length > 6" link type="primary" @click="milestonesExpanded = !milestonesExpanded">
          {{ milestonesExpanded ? '收起' : `展开其余 ${detailMilestones.length - 6} 项` }}
        </el-button>
      </section>
      <section v-if="detailRelations.length" class="drawer-section">
        <h3>人物关系</h3>
        <div class="detail-relation-list">
          <button
            v-for="relation in detailRelations"
            :key="relation.id"
            type="button"
            class="detail-relation"
            :title="relationDirections(relation)"
            @click="openRelatedCharacter(relation)"
          >
            <img :src="characterAvatarUrl(characterName(relatedId(relation)))" alt="" />
            <strong>{{ characterName(relatedId(relation)) }}</strong>
            <span class="relation-labels">{{ relation.labels.join('、') }}</span>
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
      </section>
    </template>
    <template #footer>
      <div v-if="detail" class="drawer-actions">
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
import { ArrowRight, Download, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Graph } from "@antv/g6";
import BookPicker from "../../../components/BookPicker.vue";
import ChapterReader from "../components/ChapterReader.vue";
import { api } from "../../../api/client.js";
import { useWorkspaceStore } from "../../../stores/workspace.js";
import { report } from "../../../lib/ui.js";
import { characterAvatarUrl } from "../../../lib/avatar.js";
import { characterMilestones, groupRelations, relationLabel } from "../characterPresentation.js";

const workspace = useWorkspaceStore();
const router = useRouter();
const bookId = ref(""), tab = ref("characters"), query = ref(""), loading = ref(false), error = ref("");
const characters = ref([]), facts = ref([]), events = ref([]), relations = ref([]), clues = ref([]), reviews = ref([]);
const cards = ref([]), cardBusy = ref("");
const factsLoading = reactive({}), showReader = ref(false), citation = ref(null);
const detail = ref(null), detailOpen = ref(false);
const synthesisBusy = ref(false);
const milestonesExpanded = ref(false);
const chapters = ref([]), collapsedChapters = reactive(new Set());
const relationView = ref("graph"), graphEl = ref(null);
let relationGraph = null;
const RELATION_STYLES = {
  friendly: { label: "友好 / 合作", color: "#4d9b73" },
  hostile: { label: "敌对 / 冲突", color: "#c96b61" },
  kinship: { label: "亲属 / 师徒", color: "#b28a42" },
  neutral: { label: "其他关系", color: "#718b9d" },
};
const characterName = (id) => characters.value.find((item) => item.id === id)?.canonical_name || id;
const characterNameCount = computed(() => filteredCharacters.value.length);
const relationCategory = (type) => {
  const value = String(type || "");
  if (/朋友|同伴|同盟|合作|友好|盟友|救助|保护|喜欢|爱慕/.test(value)) return "friendly";
  if (/敌|仇|冲突|对立|背叛|欺骗|追捕|杀|战/.test(value)) return "hostile";
  if (/父|母|兄|弟|姐|妹|亲属|夫妻|师|徒|家人/.test(value)) return "kinship";
  return "neutral";
};
const relationColor = (type) => RELATION_STYLES[relationCategory(type)].color;
const relationLegend = computed(() => {
  const used = new Set(filteredRelations.value.map((item) => relationCategory(item.relation_type)));
  return Object.entries(RELATION_STYLES)
    .filter(([key]) => used.has(key))
    .map(([key, value]) => ({ key, ...value }));
});
const text = (value) => String(value || "").toLocaleLowerCase();
const matches = (value) => !query.value.trim() || text(value).includes(text(query.value.trim()));
const filteredCharacters = computed(() => {
  const related = new Set(groupedRelations.value.flatMap((item) => [item.subject_id, item.object_id]));
  return characters.value.filter((item) =>
    matches(`${item.canonical_name} ${aliases(item.aliases_json)}`) || related.has(item.id));
});
const filteredEvents = computed(() => events.value.filter((item) => matches(`${item.title} ${item.description}`)));
const filteredRelations = computed(() => relations.value.filter((item) =>
  matches(`${characterName(item.subject_id)} ${item.relation_type} ${relationLabel(item.relation_type)} ${characterName(item.object_id)}`)));
const allGroupedRelations = computed(() => groupRelations(relations.value));
const groupedRelations = computed(() => {
  const matched = new Set(filteredRelations.value.map((item) => item.id));
  return allGroupedRelations.value.filter((group) => group.records.some((item) => matched.has(item.id)));
});
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
const PROFILE_LIMIT = 220;
const clip = (value, limit = 140) => {
  const flat = String(value || "").replace(/\s+/g, " ").trim();
  return flat.length > limit ? `${flat.slice(0, limit)}…` : flat;
};
function factIntro(character, limit) {
  if (!character) return "";
  const values = ["summary", "identity", "personality", "appearance"].flatMap((type) => characterFacts(character.id)
    .filter((fact) => fact.fact_type === type)
    .map((fact) => displayValue(fact.value_json)));
  return clip([...new Set(values.filter(Boolean))].join(" "), limit);
}
function profileParagraphs(character) {
  const texts = (character?.synthesis || []).map((item) => item.text).filter(Boolean);
  if (!texts.length) return [];
  return [texts[0]];
}
function characterIntro(character) {
  const paragraphs = profileParagraphs(character);
  if (!paragraphs.length) return clip(factIntro(character, 400), PROFILE_LIMIT);
  return clip(paragraphs.join(" "), PROFILE_LIMIT);
}
function characterIdentity(character) {
  const identity = characterFacts(character.id).find((fact) => fact.fact_type === "identity");
  return identity ? clip(displayValue(identity.value_json), 60) : "";
}
function relationsOf(character) {
  return allGroupedRelations.value.filter((item) => item.subject_id === character.id || item.object_id === character.id);
}
function relationDirections(group) {
  return [...new Set(group.records.map((item) =>
    `${characterName(item.subject_id)} → ${characterName(item.object_id)}：${relationLabel(item.relation_type)}`))].join("\n");
}
const relatedId = (group) => group.subject_id === detail.value?.id ? group.object_id : group.subject_id;
function openRelatedCharacter(group) {
  const character = characters.value.find((item) => item.id === relatedId(group));
  if (character) openDetail(character);
}
async function regenerateProfile() {
  if (!detail.value || synthesisBusy.value || !bookId.value) return;
  synthesisBusy.value = true;
  try {
    const result = await api.post(`/books/${bookId.value}/knowledge/characters/${detail.value.id}/synthesize`);
    detail.value.synthesis = result.synthesis || [];
    detail.value.synthesis_status = result.synthesis_status || "ready";
    ElMessage.success("档案描述已更新");
  } catch (err) { report(err); } finally { synthesisBusy.value = false; }
}
const detailProfile = computed(() => (detail.value ? characterIntro(detail.value) : ""));
const detailFacts = computed(() => (detail.value ? characterFacts(detail.value.id) : []));
const detailMilestones = computed(() => (detail.value
  ? characterMilestones(detail.value, facts.value, chapters.value) : []));
const visibleMilestones = computed(() =>
  milestonesExpanded.value ? detailMilestones.value : detailMilestones.value.slice(0, 6));
const detailIdentity = computed(() => {
  const identity = detailFacts.value.find((fact) => fact.fact_type === "identity");
  return identity ? clip(displayValue(identity.value_json), 80) : "";
});
const detailRelations = computed(() => (detail.value
  ? relationsOf(detail.value)
  : []));
const cardFor = (name) => cards.value.find((card) => card.name === name);
function openDetail(character) {
  detail.value = character;
  milestonesExpanded.value = false;
  detailOpen.value = true;
}
function openMilestoneChapter(chapter) {
  citation.value = { chapter_id: chapter.chapter_id };
  showReader.value = true;
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
  const visibleIds = new Set(filteredRelations.value.flatMap((item) => [item.subject_id, item.object_id]));
  const nodes = filteredCharacters.value.map((item) => ({
    id: item.id,
    style: {
      src: characterAvatarUrl(item.canonical_name),
      labelText: item.canonical_name,
      size: Math.min(72, 48 + Math.sqrt(item.frequency || 0) * 4),
      radius: 999,
      stroke: "#ffffff",
      lineWidth: 4,
      labelPlacement: "bottom",
      labelFill: "#1d3b33",
      labelFontSize: 12,
      labelFontWeight: 650,
      cursor: "pointer",
    },
    states: visibleIds.has(item.id) ? [] : ["isolated"],
  }));
  const nodeIds = new Set(nodes.map((item) => item.id));
  const edges = groupedRelations.value.filter((item) => nodeIds.has(item.subject_id) && nodeIds.has(item.object_id)).map((item) => ({
    id: item.id,
    source: item.subject_id,
    target: item.object_id,
    states: [],
    style: {
      labelText: item.labels.join("、"),
      stroke: relationColor(item.labels.join("、")),
      lineWidth: 1.6,
      lineDash: relationCategory(item.labels.join("、")) === "hostile" ? [7, 4] : undefined,
      endArrow: false,
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
    node: { type: "image" },
    layout: { type: "force", preventOverlap: true, nodeSize: 64, linkDistance: 180, collideStrength: 0.9 },
    behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
  });
  await relationGraph.render();
  relationGraph.fitView();
  relationGraph.on("node:click", (event) => {
    const id = event.target?.id || event.item?.id;
    const row = characters.value.find((item) => item.id === id);
    if (row) openDetail(row);
  });
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
    await nextTick();
    await renderRelationGraph();
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
async function removeEvent(row) { await remove(`/books/${bookId.value}/knowledge/events/${row.id}`, "确认删除这个事件？"); }
async function removeRelationGroup(group) {
  try {
    await ElMessageBox.confirm(
      `确认删除${characterName(group.subject_id)}与${characterName(group.object_id)}之间的全部 ${group.records.length} 条关系？`,
      "删除关系", { type: "warning" });
  } catch { return; }
  try {
    const results = await Promise.allSettled(group.records.map((item) =>
      api.delete(`/books/${bookId.value}/knowledge/relations/${item.id}`)));
    const failed = results.find((result) => result.status === "rejected");
    if (failed) report(failed.reason);
    else ElMessage.success("关系已删除");
  } finally { await load(); }
}
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
watch([filteredCharacters, filteredRelations], () => renderRelationGraph());
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
.character-intro { margin:0; color:#48605a; line-height:1.75; display:block; overflow:visible; }
.character-intro.placeholder { color:#93a49c; }
.character-tags { display:flex; flex-wrap:wrap; gap:6px; }
.character-tag { padding:2px 9px; border-radius:999px; background:#f2f8f5; border:1px solid #e2efe9; color:#4c6d61; font-size:11px; }
.character-profile { padding-top:10px; border-top:1px dashed #e8f0ec; }
.character-profile-label { margin:0 0 4px; font-size:11px; color:#8ba79c; }
.character-actions { display:flex; justify-content:flex-end; gap:8px; }
.drawer-profile { display:flex; align-items:center; gap:16px; padding:6px 0 16px; border-bottom:1px solid #edf1ee; }
.drawer-avatar { width:76px; height:76px; flex:0 0 76px; border-radius:18px; object-fit:cover; background:#e7f2ee; border:2px solid #cfe6dc; box-shadow:0 6px 18px rgba(41,85,69,.12); }
.drawer-profile-content { min-width:0; }
.drawer-profile-kicker { margin:0; font-size:11px; color:#8ba79c; }
.drawer-profile-name { margin:2px 0 0; font-size:22px; color:#1d4d42; overflow-wrap:anywhere; }
.drawer-profile-alias { margin:4px 0 8px; color:#6d857b; font-size:13px; overflow-wrap:anywhere; }
.drawer-profile-meta { display:flex; align-items:center; gap:16px; flex-wrap:wrap; font-size:13px; color:#4d6b60; }
.drawer-profile-meta strong { color:#1d4d42; }
.drawer-section { margin-top:18px; }
.drawer-section h3 { margin:0 0 8px; font-size:15px; color:#22453c; }
.section-heading { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:8px; }
.section-heading h3 { margin:0; }
.profile-description { padding:16px 0; border-bottom:1px solid #e3efe9; }
.profile-text { margin:0; color:#3f5750; line-height:1.85; font-size:14px; overflow-wrap:anywhere; }
.profile-empty { margin:0; color:#8ba29a; font-size:13px; }
.profile-facts { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.profile-facts > div { min-width:0; padding:10px 0; border-bottom:1px solid #e7efeb; }
.profile-facts span { display:block; margin-bottom:3px; color:#8da59c; font-size:11px; }
.profile-facts strong { display:block; color:#24463c; font-size:13px; font-weight:600; overflow-wrap:anywhere; }
.milestone-list { margin:0; padding:0; list-style:none; }
.milestone-list li { display:flex; align-items:baseline; justify-content:space-between; flex-wrap:wrap; gap:4px 12px; padding:10px 0 10px 12px; border-left:2px solid #d6e5df; border-bottom:1px solid #edf1ee; }
.milestone-list p { flex:1 1 240px; margin:0; color:#3f5750; font-size:13px; line-height:1.7; overflow-wrap:anywhere; }
.milestone-chapters { display:flex; flex-wrap:wrap; gap:6px 12px; color:#8b9892; font-size:11px; }
.milestone-chapters .el-button { margin:0; font-size:11px; }
.detail-relation-list { display:grid; }
.detail-relation { display:grid; grid-template-columns:32px minmax(60px,1fr) minmax(0,1.5fr) 16px; align-items:center; gap:10px; width:100%; padding:12px 0; border:0; border-bottom:1px solid #edf1ee; background:transparent; text-align:left; color:#31584c; cursor:pointer; }
.detail-relation:hover { background:#f5faf7; }
.detail-relation:focus-visible { outline:2px solid #4d9b73; outline-offset:2px; }
.detail-relation img { width:32px; height:32px; object-fit:cover; border-radius:50%; background:#e7f2ee; }
.detail-relation strong { font-size:13px; overflow-wrap:anywhere; }
.detail-relation .el-icon { color:#8ca399; }
.relation-labels { color:#61788b; font-size:12px; line-height:1.7; overflow-wrap:anywhere; }
.relation-pair { display:flex; align-items:center; gap:10px; flex-wrap:wrap; min-width:0; overflow-wrap:anywhere; }
.drawer-actions { display:flex; justify-content:flex-end; gap:8px; padding:12px 0 0; background:#fff; border-top:1px solid #edf1ee; }
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
.review-row { padding:10px 0; border-top:1px solid #edf1ee; }
.card-actions { margin-top:14px; justify-content:flex-end; }
.relation-record { padding:14px 0; border-bottom:1px solid #edf1ee; }
.relation-panel { padding:18px; }
.relation-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:8px; }
.relation-graph { position:relative; width:100%; height:560px; overflow:hidden; border-radius:10px; background:radial-gradient(circle at 50% 42%,#ffffff 0%,#f7fbf9 68%,#eef5f1 100%); border:1px solid #e6efea; }
.relation-graph-legend { position:absolute; top:12px; right:12px; z-index:2; display:flex; gap:10px; flex-wrap:wrap; max-width:300px; padding:8px 10px; border:1px solid #e0ebe5; border-radius:8px; background:rgba(255,255,255,.9); color:#60766b; font-size:11px; box-shadow:0 5px 16px rgba(39,48,42,.06); }
.relation-graph-legend span { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }
.relation-graph-legend i { width:16px; height:3px; border-radius:3px; }
.graph-hint { margin:8px 0 0; font-size:12px; }
.relation-graph-wrap { margin-top:8px; }
.quote-text { padding:12px; background:#f6faf7; border-left:3px solid #82ad9d; color:#4d6258; }
.review-row p { white-space:pre-wrap; max-width:700px; color:#53645c; }
@media (max-width:700px) {
  .knowledge-summary-head { display:block; }
  .knowledge-metrics { margin-top:16px; }
  .knowledge-grid { grid-template-columns:minmax(0,1fr); }
  .character-collapsed-row { flex-wrap:wrap; }
  .character-actions,.drawer-actions { flex-wrap:wrap; }
  .drawer-actions .el-button { margin-left:0; }
  .review-row { display:block; }
}
</style>
