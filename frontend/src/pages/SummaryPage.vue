<template>
  <div class="summary-page">
    <div class="page-head">
      <div>
        <h3 class="page-title">Summary</h3>
        <p class="page-subtitle">角色总表 / 物品总表 / 剧情时间线 / 世界观</p>
      </div>
      <span class="pill-tag">Summary</span>
    </div>

    <el-card class="panel-card">
      <div class="toolbar-row">
        <el-space direction="vertical" alignment="start" class="book-picker-wrap">
          <span class="toolbar-label">当前书籍</span>
          <el-select v-model="selectedBookId" class="book-select" placeholder="选择书籍" @change="onBookChange">
            <el-option
              v-for="book in books"
              :key="book.book_id"
              :label="`${book.book_name} · ${book.book_id}`"
              :value="book.book_id"
            />
          </el-select>
        </el-space>

        <el-button :loading="loading" @click="refreshCurrentBook">刷新 Summary</el-button>
      </div>
    </el-card>

    <el-card class="panel-card">
      <el-empty v-if="!selectedBookId" description="请先选择书籍" />

      <el-tabs v-else v-model="activeType" class="summary-tabs">
        <el-tab-pane v-for="typeKey in summaryTypeOrder" :key="typeKey" :name="typeKey">
          <template #label>
            <span>{{ summaryLabel(typeKey) }}</span>
            <span class="tab-count">{{ summaryCount(typeKey) }}</span>
          </template>

          <section class="summary-section">
            <div class="section-head">
              <div>
                <h4 class="section-title">{{ summaryLabel(typeKey) }}</h4>
                <p class="section-subtitle">{{ summaryDescription(typeKey) }}</p>
              </div>
              <span class="section-pill">{{ summaryCount(typeKey) }} 条</span>
            </div>

            <el-empty v-if="summaryItems(typeKey).length === 0" description="暂无内容" />

            <div v-else class="summary-list" v-loading="loading && summaryItems(typeKey).length > 0">
              <el-card v-for="item in summaryItems(typeKey)" :key="item.id" class="summary-record-card" shadow="never">
                <div v-if="isStructuredType(typeKey)" class="record-body">
                  <div v-if="getContentState(item).loading" class="state-box">正在从 OSS 加载 JSON 内容...</div>
                  <el-empty v-else-if="getContentState(item).error" :description="getContentState(item).error" />
                  <div v-else class="entry-grid">
                    <el-card v-for="(entry, index) in getContentState(item).entries" :key="`${item.id}-${index}`" class="entry-card" shadow="never">
                      <div class="entry-topline">
                        <div class="entry-title">{{ entry.name || `条目 ${index + 1}` }}</div>
                        <span class="entry-badge" v-if="typeKey === 'characters'">角色卡</span>
                      </div>

                      <div class="entry-summary" :class="{ 'clamp-lines': !isEntryExpanded(item, index) }">
                        {{ entry.summary || "暂无简介" }}
                      </div>

                      <div v-if="typeKey === 'characters'" class="entry-compact-fields">
                        <div v-if="entry.identity" class="compact-row">
                          <span class="compact-label">身份</span>
                          <span class="compact-value">{{ entry.identity }}</span>
                        </div>
                        <div v-if="entry.appearance" class="compact-row">
                          <span class="compact-label">外观</span>
                          <span class="compact-value">{{ entry.appearance }}</span>
                        </div>
                        <div v-if="entry.personality" class="compact-row">
                          <span class="compact-label">性格</span>
                          <span class="compact-value">{{ entry.personality }}</span>
                        </div>
                      </div>

                      <div v-if="entry.details.length > 0 && isEntryExpanded(item, index)" class="entry-details">
                        <div v-for="detail in entry.details" :key="detail.key" class="detail-row">
                          <span class="detail-label">{{ detail.label }}</span>
                          <span class="detail-value">{{ detail.value }}</span>
                        </div>
                      </div>

                      <div class="entry-actions">
                        <div class="entry-toggle-row">
                          <el-button
                            class="entry-toggle"
                            text
                            circle
                            :title="isEntryExpanded(item, index) ? '收起详情' : '展开详情'"
                            :aria-label="isEntryExpanded(item, index) ? '收起详情' : '展开详情'"
                            @click="toggleEntryDetails(item, index)"
                          >
                            <el-icon>
                              <ArrowUp v-if="isEntryExpanded(item, index)" />
                              <ArrowDown v-else />
                            </el-icon>
                          </el-button>
                        </div>

                        <div v-if="typeKey === 'characters'" class="entry-action-row">
                          <el-button
                            class="entry-action-button"
                            size="small"
                            type="primary"
                            plain
                            :loading="extractingKey === entryKey(item, index)"
                            :disabled="extractingKey === entryKey(item, index)"
                            @click="startDetailedCharacterExtract(item, entry, index)"
                          >
                            提取角色
                          </el-button>
                          <el-button
                            class="entry-action-button"
                            size="small"
                            type="primary"
                            plain
                            :disabled="!entry.summary_oss_url"
                            @click="openUrl(entry.summary_oss_url)"
                          >
                            下载角色
                          </el-button>
                        </div>
                      </div>
                    </el-card>
                  </div>
                </div>

                <div v-else class="record-body markdown-body">
                  <div v-if="getContentState(item).loading" class="state-box">正在从 OSS 加载 Markdown 内容...</div>
                  <el-empty v-else-if="getContentState(item).error" :description="getContentState(item).error" />
                  <MarkdownRender v-else class="summary-markdown" :content="getContentState(item).markdown" :typewriter="false" />
                </div>
              </el-card>
            </div>
          </section>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ArrowDown, ArrowUp } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { MarkdownRender } from "vue-renderer-markdown";
import "vue-renderer-markdown/index.css";
import { api } from "../api/client";
import { summaryNameByType } from "../api/core";
import { useAppStateStore } from "../stores/appState";
import { useSettingsStore } from "../stores/settings";

defineOptions({
  name: "SummaryPage",
});

const summaryTypeOrder = ["characters", "items", "storyline_events", "world_locations"];
const summaryDescriptions = {
  characters: "角色总表（核心角色）",
  items: "物品总表 （包含武器、防具、道具等）",
  storyline_events: "剧情时间线信息",
  world_locations: "世界观与地点信息的信息",
};
const structuredTypes = new Set(["characters", "items"]);

const settingsStore = useSettingsStore();
const appStateStore = useAppStateStore();

const books = ref([]);
const summaries = ref([]);
const contentStates = ref({});
const expandedMap = ref({});
const loading = ref(false);
const extractingKey = ref("");
const selectedBookId = ref(appStateStore.appState.current_book_id ?? "");
const activeType = ref(summaryTypeOrder[0]);

function summaryLabel(typeKey) {
  return summaryNameByType(typeKey) || typeKey;
}

function summaryDescription(typeKey) {
  return summaryDescriptions[typeKey] || "从 OSS 读取并展示该类型的 summary 内容。";
}

function summaryItems(typeKey) {
  return summaries.value.filter((item) => item.type === typeKey);
}

function summaryCount(typeKey) {
  return summaryItems(typeKey).length;
}

function isStructuredType(typeKey) {
  return structuredTypes.has(typeKey);
}

function entryKey(summaryItem, index) {
  return `${summaryItem.summary_id || summaryItem.id || "summary"}:${index}`;
}

function isEntryExpanded(summaryItem, index) {
  return Boolean(expandedMap.value[entryKey(summaryItem, index)]);
}

function toggleEntryDetails(summaryItem, index) {
  const key = entryKey(summaryItem, index);
  expandedMap.value = {
    ...expandedMap.value,
    [key]: !expandedMap.value[key],
  };
}

function ensureContentState(summaryItem) {
  const summaryId = summaryItem.summary_id || summaryItem.id;
  if (!summaryId) {
    return null;
  }

  if (!contentStates.value[summaryId]) {
    contentStates.value[summaryId] = {
      loading: false,
      error: "",
      entries: [],
      markdown: "",
    };
  }

  return contentStates.value[summaryId];
}

function getContentState(summaryItem) {
  return ensureContentState(summaryItem) || {
    loading: false,
    error: "",
    entries: [],
    markdown: "",
  };
}

function summarizeRecord(record, index) {
  const source = record && typeof record === "object" ? record : { name: String(record || "") };
  const ignoredKeys = new Set([
    "name",
    "summary",
    "identity",
    "appearance",
    "personality",
    "summary_local_url",
    "summary_oss_url",
  ]);

  const detailMap = [];
  for (const [key, value] of Object.entries(source)) {
    if (ignoredKeys.has(key)) {
      continue;
    }
    const normalized = normalizePrimitive(value);
    if (!normalized) {
      continue;
    }
    detailMap.push({
      key,
      label: humanizeFieldName(key),
      value: normalized,
    });
  }

  return {
    name: normalizePrimitive(source.name) || `条目 ${index + 1}`,
    summary: normalizePrimitive(source.summary),
    identity: normalizePrimitive(source.identity),
    appearance: normalizePrimitive(source.appearance),
    personality: normalizePrimitive(source.personality),
    summary_local_url: normalizePrimitive(source.summary_local_url),
    summary_oss_url: normalizePrimitive(source.summary_oss_url),
    details: detailMap,
  };
}

function humanizeFieldName(fieldName) {
  return String(fieldName || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function normalizePrimitive(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizePrimitive(item)).filter(Boolean).join("、");
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value).trim();
}

function normalizeJsonEntries(parsed) {
  let source = parsed;
  if (source && typeof source === "object" && !Array.isArray(source)) {
    if (Array.isArray(source.items)) {
      source = source.items;
    } else if (Array.isArray(source.data)) {
      source = source.data;
    } else if (Array.isArray(source.list)) {
      source = source.list;
    } else if (Array.isArray(source.records)) {
      source = source.records;
    } else {
      source = [source];
    }
  }

  if (!Array.isArray(source)) {
    return [];
  }

  return source
    .map((record, index) => summarizeRecord(record, index))
    .filter((item) => item.name || item.summary || item.details.length > 0);
}

async function loadBooks() {
  try {
    const res = await api.getBooks(settingsStore.settings);
    books.value = Array.isArray(res?.books) ? res.books : [];

    if (!selectedBookId.value && books.value.length > 0) {
      selectedBookId.value = books.value[0].book_id;
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "获取书籍失败");
  }
}

async function loadSummaries(bookId) {
  if (!bookId) {
    summaries.value = [];
    contentStates.value = {};
    expandedMap.value = {};
    return;
  }

  loading.value = true;
  try {
    const res = await api.getSummaryList(bookId, settingsStore.settings);
    summaries.value = Array.isArray(res?.summaries) ? res.summaries : [];
    contentStates.value = {};
    expandedMap.value = {};

    if (summaries.value.length > 0) {
      activeType.value = summaryTypeOrder.find((typeKey) => summaryItems(typeKey).length > 0) || summaries.value[0].type || summaryTypeOrder[0];
      await loadSummaryContents(summaries.value);
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载 Summary 失败");
  } finally {
    loading.value = false;
  }
}

async function loadSummaryContents(summaryList) {
  await Promise.allSettled(summaryList.map((summaryItem) => loadSummaryContent(summaryItem)));
}

async function loadSummaryContent(summaryItem) {
  const state = ensureContentState(summaryItem);
  if (!state) {
    return;
  }

  state.loading = true;
  state.error = "";
  state.entries = [];
  state.markdown = "";

  try {
    const sourceUrl = String(summaryItem.content_oss_url || "").trim();
    if (!sourceUrl) {
      throw new Error("缺少 OSS 内容地址");
    }

    const response = await fetch(sourceUrl, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`OSS 拉取失败 (${response.status})`);
    }

    const rawText = await response.text();
    if (isStructuredType(summaryItem.type)) {
      const parsed = tryParseJson(rawText);
      const entries = normalizeJsonEntries(parsed);
      if (entries.length === 0) {
        throw new Error("JSON 内容为空或格式不符合预期");
      }
      state.entries = entries;
    } else {
      state.markdown = normalizeMarkdownText(rawText);
      if (!state.markdown) {
        throw new Error("Markdown 内容为空");
      }
    }
  } catch (error) {
    state.error = error instanceof Error ? error.message : "加载 OSS 内容失败";
  } finally {
    state.loading = false;
  }
}

function tryParseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function normalizeMarkdownText(text) {
  const lines = String(text || "")
    .replace(/^\uFEFF/, "")
    .trim()
    .split(/\r?\n/);
  const firstContentIndex = lines.findIndex((line) => line.trim());
  if (firstContentIndex >= 0 && /^#{1,6}\s+/.test(lines[firstContentIndex].trim())) {
    lines.splice(firstContentIndex, 1);
  }
  return lines.join("\n").trim();
}

function onBookChange(bookId) {
  const selected = books.value.find((item) => item.book_id === bookId);
  appStateStore.patchAppState({
    current_book_id: bookId,
    current_book_name: selected?.book_name ?? bookId,
  });
  void loadSummaries(bookId);
}

function refreshCurrentBook() {
  return loadSummaries(selectedBookId.value);
}

function openUrl(url) {
  if (!url) {
    return;
  }

  const raw = String(url).trim();
  if (!raw) {
    return;
  }

  if (/^https?:\/\//i.test(raw)) {
    window.open(raw, "_blank", "noopener,noreferrer");
    return;
  }

  ElMessage.info(raw);
}

async function startDetailedCharacterExtract(summaryItem, entry, index) {
  const characterName = String(entry?.name || "").trim();
  if (!characterName) {
    ElMessage.warning("缺少角色名称");
    return;
  }

  const key = entryKey(summaryItem, index);
  extractingKey.value = key;
  try {
    const payload = {
      book_id: selectedBookId.value,
      run_summary: false,
      run_card: true,
      card_character_name: characterName,
    };

    const res = await api.startExtractTask(payload, settingsStore.settings);
    appStateStore.patchAppState({
      current_task_id: res?.task_id,
      current_book_id: selectedBookId.value,
      current_book_name: books.value.find((item) => item.book_id === selectedBookId.value)?.book_name || selectedBookId.value,
    });
    ElMessage.success(res?.status === "started" ? `已开始精细提取：${characterName}` : `已提交提取任务：${characterName}`);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提交提取失败");
  } finally {
    extractingKey.value = "";
  }
}

onMounted(async () => {
  await loadBooks();
  await loadSummaries(selectedBookId.value);
});
</script>

<style scoped>
.summary-page {
  display: grid;
  gap: 16px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.page-title {
  margin: 0;
  font-size: 22px;
  color: #11314a;
}

.page-subtitle {
  margin: 6px 0 0;
  color: #6b8198;
}

.pill-tag {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: #1f5ea6;
  background: #eaf4ff;
}

.panel-card {
  border-radius: 14px;
}

.toolbar-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.book-picker-wrap {
  align-items: flex-start;
}

.book-select {
  min-width: 280px;
}

.toolbar-label {
  color: #6b8198;
  font-size: 12px;
}

.summary-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background-color: #dce8f4;
}

.tab-count {
  margin-left: 6px;
  padding: 2px 7px;
  border-radius: 999px;
  background: #eef5ff;
  color: #1f5ea6;
  font-size: 12px;
}

.summary-section {
  display: grid;
  gap: 12px;
  padding-top: 8px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.section-title {
  margin: 0;
  font-size: 18px;
  color: #11314a;
}

.section-subtitle {
  margin: 6px 0 0;
  color: #6b8198;
}

.section-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f3f8ff;
  color: #1f5ea6;
  font-size: 12px;
}

.summary-list {
  display: grid;
  gap: 12px;
}

.summary-record-card {
  border: 1px solid #dce8f4;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f9fcff 100%);
}

.record-body {
  min-height: 60px;
}

.state-box {
  padding: 16px;
  border-radius: 10px;
  background: #f7fbff;
  color: #5c738c;
  font-size: 13px;
}

.entry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 8px;
}

.entry-card {
  height: 205px;
  border: 1px solid #e2edf7;
  border-radius: 10px;
  background: #ffffff;
  display: flex;
  flex-direction: column;
}

.entry-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  padding: 7px 10px;
}

.entry-topline {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.entry-title {
  font-size: 16px;
  font-weight: 700;
  color: #11314a;
  word-break: break-all;
}

.entry-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef5ff;
  color: #1f5ea6;
  font-size: 12px;
  white-space: nowrap;
}

.entry-summary {
  color: #31485f;
  line-height: 1.36;
  white-space: pre-wrap;
  overflow: hidden;
  font-size: 15px;
}

.clamp-lines {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.entry-compact-fields {
  display: grid;
  gap: 3px;
  overflow: auto;
}

.compact-row {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: 8px;
  font-size: 13px;
}

.compact-label {
  color: #4f6a83;
  font-weight: 600;
}

.compact-value {
  color: #31485f;
  word-break: break-all;
}

.entry-details {
  display: grid;
  gap: 6px;
  overflow: auto;
  padding-top: 4px;
  border-top: 1px dashed #dce8f4;
}

.detail-row {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 8px;
  align-items: start;
  font-size: 13px;
}

.detail-label {
  color: #4f6a83;
  font-weight: 600;
}

.detail-value {
  color: #31485f;
  word-break: break-all;
}

.entry-actions {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 3px;
  align-items: stretch;
}

.entry-action-row {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.entry-action-button {
  min-width: 92px;
  font-size: 13px;
}

.entry-toggle-row {
  display: flex;
  justify-content: center;
  line-height: 1;
}

.entry-toggle {
  width: 22px;
  height: 22px;
  min-height: 22px;
  padding: 0;
  color: #4f6a83;
}

.markdown-body {
  border: 1px solid #e2edf7;
  border-radius: 12px;
  padding: 16px;
  background: #ffffff;
}

.summary-markdown :deep(.markdown-renderer) {
  color: #31485f;
}

.summary-markdown :deep(h1),
.summary-markdown :deep(h2),
.summary-markdown :deep(h3),
.summary-markdown :deep(h4) {
  color: #11314a;
}

.summary-markdown :deep(code) {
  background: #edf4fb;
}

@media (max-width: 720px) {
  .book-select {
    min-width: 220px;
  }

  .detail-row {
    grid-template-columns: 1fr;
  }
}
</style>
