<template>
  <div class="page-wrap">
    <div class="page-head">
      <div>
        <h3 class="page-title">提取任务看板</h3>
        <p class="page-subtitle">跟踪 source_file 提取状态、异步任务进度，以及 chapter/summary 上传结果。</p>
      </div>
      <span class="pill-tag">Pipeline Board</span>
    </div>

    <el-card class="panel-card">
      <div class="board-toolbar">
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

        <div class="toolbar-meta" v-if="selectedBook">
          <div class="meta-pill">
            <span class="meta-pill-label">source_file 状态</span>
            <strong>{{ parseFlowLabel(selectedBook.status) }}</strong>
          </div>
          <div class="meta-pill">
            <span class="meta-pill-label">当前进度</span>
            <strong>{{ selectedBook.progress ?? 0 }}%</strong>
          </div>
        </div>

        <el-button :loading="loadingAll" @click="refreshCurrentBook">刷新看板</el-button>
      </div>
    </el-card>

    <el-card class="panel-card">
      <template #header>
        <div class="section-header">
          <span>任务统计（extraction_tasks）</span>
        </div>
      </template>
      <div class="metric-grid">
        <div class="metric-item">
          <div class="metric-label">chapter_extraction</div>
          <div class="metric-value">{{ taskStats.chapterExtraction }}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">summary</div>
          <div class="metric-value">{{ taskStats.summary }}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">card</div>
          <div class="metric-value">{{ taskStats.card }}</div>
        </div>
      </div>
      <div class="status-row">
        <el-tag type="info" round>等待中 {{ taskStats.pending }}</el-tag>
        <el-tag type="warning" round>进行中 {{ taskStats.running }}</el-tag>
        <el-tag type="success" round>已完成 {{ taskStats.completed }}</el-tag>
        <el-tag type="danger" round>失败 {{ taskStats.failed }}</el-tag>
      </div>
    </el-card>

    <el-card class="panel-card">
      <template #header>异步任务列表</template>
      <el-empty v-if="!selectedBookId" description="请先选择书籍" />
      <el-table v-else class="table-shell" :data="tasks" v-loading="loadingAll" stripe empty-text="暂无任务记录">
        <el-table-column prop="task_type" label="任务类型" min-width="150" />
        <el-table-column prop="status_label" label="状态" width="120" />
        <el-table-column label="进度" min-width="180">
          <template #default="scope">
            <el-progress :percentage="scope.row.progress || 0" :status="scope.row.status === 'failed' ? 'exception' : undefined" />
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" min-width="170">
          <template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误信息" min-width="220" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card class="panel-card">
      <template #header>任务日志（task_logs）</template>
      <el-empty v-if="logs.length === 0" description="暂无日志" />
      <div v-else class="log-list">
        <div v-for="item in logs" :key="item.id" class="log-item">
          <div class="log-topline">
            <el-tag size="small" effect="plain">{{ item.level }}</el-tag>
            <span class="log-time">{{ formatDateTime(item.created_at) }}</span>
          </div>
          <div class="log-message">{{ item.message || "(无消息)" }}</div>
        </div>
      </div>
    </el-card>

    <el-card class="panel-card">
      <template #header>逐章提取合并结果（chapter_extractions）</template>
      <el-empty v-if="extractions.length === 0" description="暂无逐章提取结果" />
      <el-table v-else class="table-shell" :data="extractions" stripe>
        <el-table-column prop="extractor_type" label="extractor_type" width="140" />
        <el-table-column prop="model_name" label="模型" width="140" />
        <el-table-column prop="updated_at" label="更新时间" min-width="170">
          <template #default="scope">{{ formatDateTime(scope.row.updated_at || scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="本地文件" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <el-button text type="primary" :disabled="!scope.row.book_extraction_json_local_url" @click="openUrl(scope.row.book_extraction_json_local_url)">
              打开本地路径
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="OSS 文件" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <el-button text type="primary" :disabled="!scope.row.book_extraction_json_oss_url" @click="openUrl(scope.row.book_extraction_json_oss_url)">
              打开 OSS 地址
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="panel-card">
      <template #header>Summary 文件目录</template>
      <el-empty v-if="summaries.length === 0" description="暂无 summary 记录" />
      <div v-else class="summary-grid">
        <div v-for="item in summaries" :key="item.id" class="summary-item">
          <div class="summary-title">{{ item.name || item.type }}</div>
          <div class="summary-meta">type: {{ item.type }}</div>
          <div class="summary-actions">
            <el-button text type="primary" :disabled="!item.content_local_url" @click="openUrl(item.content_local_url)">本地目录</el-button>
            <el-button text type="primary" :disabled="!item.content_oss_url" @click="openUrl(item.content_oss_url)">OSS 目录</el-button>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import { useAppStateStore } from "../stores/appState";
import { useSettingsStore } from "../stores/settings";

const settingsStore = useSettingsStore();
const appStateStore = useAppStateStore();

const books = ref([]);
const tasks = ref([]);
const logs = ref([]);
const extractions = ref([]);
const summaries = ref([]);
const loadingAll = ref(false);
const selectedBookId = ref(appStateStore.appState.current_book_id ?? "");

const selectedBook = computed(() => books.value.find((item) => item.book_id === selectedBookId.value) || null);

const taskStats = computed(() => {
  const summary = {
    chapterExtraction: 0,
    summary: 0,
    card: 0,
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
  };

  for (const task of tasks.value) {
    const type = String(task.task_type || "").toLowerCase();
    if (type === "chapter_extraction") summary.chapterExtraction += 1;
    if (type === "summary") summary.summary += 1;
    if (type === "card") summary.card += 1;

    if (task.status === "pending") summary.pending += 1;
    if (task.status === "running") summary.running += 1;
    if (task.status === "completed") summary.completed += 1;
    if (task.status === "failed") summary.failed += 1;
  }

  return summary;
});

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

async function loadBoardData(bookId) {
  if (!bookId) {
    tasks.value = [];
    logs.value = [];
    extractions.value = [];
    summaries.value = [];
    return;
  }

  loadingAll.value = true;
  try {
    const [taskRes, logRes, extractionRes, summaryRes] = await Promise.all([
      api.getExtractionTasks(bookId, settingsStore.settings),
      api.getTaskLogs(settingsStore.settings, { limit: 20 }),
      api.getChapterExtractions(bookId, settingsStore.settings),
      api.getSummaryList(bookId, settingsStore.settings),
    ]);

    tasks.value = Array.isArray(taskRes?.tasks) ? taskRes.tasks : [];
    logs.value = Array.isArray(logRes?.logs) ? logRes.logs : [];
    extractions.value = Array.isArray(extractionRes?.extractions) ? extractionRes.extractions : [];
    summaries.value = Array.isArray(summaryRes?.summaries) ? summaryRes.summaries : [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载看板数据失败");
  } finally {
    loadingAll.value = false;
  }
}

function onBookChange(bookId) {
  const selected = books.value.find((item) => item.book_id === bookId);
  appStateStore.patchAppState({
    current_book_id: bookId,
    current_book_name: selected?.book_name ?? bookId,
  });
  void loadBoardData(bookId);
}

function refreshCurrentBook() {
  return loadBoardData(selectedBookId.value);
}

function parseFlowLabel(status) {
  const normalized = String(status || "").trim();
  if (normalized === "待解析") return "未提取";
  if (normalized === "解析中") return "提取中";
  if (normalized === "已完成") return "提取完成";
  if (normalized === "失败") return "提取失败";
  return normalized || "未提取";
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) {
    return String(value);
  }
  return time.toLocaleString("zh-CN", { hour12: false });
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

onMounted(async () => {
  await loadBooks();
  if (selectedBookId.value) {
    await loadBoardData(selectedBookId.value);
  }
});
</script>

<style scoped>
.board-toolbar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.book-picker-wrap {
  min-width: min(100%, 420px);
}

.toolbar-label {
  color: var(--nw-muted);
  font-size: 12px;
}

.book-select {
  width: min(100%, 480px);
}

.toolbar-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-pill {
  padding: 8px 12px;
  border-radius: 12px;
  border: 1px solid #dce8f4;
  background: #f7fbff;
}

.meta-pill-label {
  display: block;
  color: var(--nw-muted);
  font-size: 12px;
}

.meta-pill strong {
  color: var(--nw-title);
  font-size: 14px;
}

.status-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.section-header {
  font-weight: 700;
}

.table-shell {
  border: 1px solid #dce8f4;
}

.log-list {
  display: grid;
  gap: 10px;
}

.log-item {
  border: 1px solid #dce8f4;
  border-radius: 12px;
  background: #fbfdff;
  padding: 10px 12px;
}

.log-topline {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.log-time {
  color: var(--nw-muted);
  font-size: 12px;
}

.log-message {
  margin-top: 6px;
  color: var(--nw-text);
  font-size: 13px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.summary-item {
  border-radius: 12px;
  border: 1px solid #dce8f4;
  background: #fbfdff;
  padding: 12px;
}

.summary-title {
  color: var(--nw-title);
  font-size: 14px;
  font-weight: 700;
}

.summary-meta {
  margin-top: 6px;
  color: var(--nw-muted);
  font-size: 12px;
}

.summary-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

@media (max-width: 860px) {
  .board-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
