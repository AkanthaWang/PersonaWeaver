<template>
  <div class="page-wrap">
    <div class="page-head">
      <div>
        <h3 class="page-title">角色卡中心</h3>
        <p class="page-subtitle">浏览 card 表中的角色卡模板，支持按书籍、类型和关键词筛选。</p>
      </div>
      <span class="pill-tag">Card Center</span>
    </div>

    <el-card class="panel-card">
      <div class="filter-row">
        <el-select v-model="selectedBookId" class="book-select" placeholder="筛选书籍" clearable @change="onBookChange">
          <el-option
            v-for="book in books"
            :key="book.book_id"
            :label="`${book.book_name} · ${book.book_id}`"
            :value="book.book_id"
          />
        </el-select>

        <el-select v-model="typeFilter" class="type-select" placeholder="筛选类型" clearable>
          <el-option label="character" value="character" />
          <el-option label="item" value="item" />
          <el-option label="location" value="location" />
          <el-option label="plot" value="plot" />
        </el-select>

        <el-input v-model="keyword" placeholder="搜索名称/简介" class="keyword-input" clearable />
        <el-button :loading="loading" @click="refreshCards">刷新</el-button>
      </div>
    </el-card>

    <el-card class="panel-card">
      <div class="metric-grid">
        <div class="metric-item">
          <div class="metric-label">卡片总数</div>
          <div class="metric-value">{{ filteredCards.length }}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">character</div>
          <div class="metric-value">{{ typeStats.character }}</div>
        </div>
        <div class="metric-item">
          <div class="metric-label">item/location/plot</div>
          <div class="metric-value">{{ typeStats.other }}</div>
        </div>
      </div>
    </el-card>

    <el-empty v-if="!loading && filteredCards.length === 0" description="暂无符合条件的角色卡" />

    <el-row v-else :gutter="16" v-loading="loading">
      <el-col v-for="item in filteredCards" :key="item.id" :xs="24" :sm="12" :md="8">
        <el-card class="card-item">
          <div class="card-topline">
            <div class="card-title">{{ item.name || "未命名" }}</div>
            <el-tag size="small" effect="plain">{{ item.type || "character" }}</el-tag>
          </div>

          <div class="card-book">{{ bookNameById(item.book_id) }}</div>
          <div class="card-intro">{{ item.intro || "暂无简介" }}</div>

          <div class="card-fields">
            <!-- <div class="field-row">
              <span class="field-label">card_id</span>
              <span class="field-value">{{ item.card_id || item.id || "-" }}</span>
            </div>
            <div class="field-row">
              <span class="field-label">book_id</span>
              <span class="field-value">{{ item.book_id || "-" }}</span>
            </div>
            <div class="field-row">
              <span class="field-label">prompt_id</span>
              <span class="field-value">{{ item.prompt_id || "-" }}</span>
            </div> -->
            <div class="field-row">
              <span class="field-label">创建于</span>
              <span class="field-value">{{ formatDateTime(item.created_at) }}</span>
            </div>
            <div class="field-row">
              <span class="field-label">更新于</span>
              <span class="field-value">{{ formatDateTime(item.updated_at || item.created_at) }}</span>
            </div>
          </div>

          <!-- <div class="card-actions">
            <el-button text type="primary" :disabled="!item.content_local_url" @click="openUrl(item.content_local_url)">
              本地目录
            </el-button>
            <el-button text type="primary" :disabled="!item.content_oss_url" @click="openUrl(item.content_oss_url)">
              OSS 目录
            </el-button>
          </div> -->
        </el-card>
      </el-col>
    </el-row>
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

const keyword = ref("");
const typeFilter = ref("");
const loading = ref(false);
const cards = ref([]);
const books = ref([]);
const selectedBookId = ref(appStateStore.appState.current_book_id ?? "");

const filteredCards = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  const selectedType = String(typeFilter.value || "").toLowerCase();

  return cards.value.filter((item) => {
    const byBook = selectedBookId.value ? item.book_id === selectedBookId.value : true;
    const byType = selectedType ? String(item.type || "").toLowerCase() === selectedType : true;
    const content = `${item.name || ""} ${item.intro || ""}`.toLowerCase();
    const byText = text ? content.includes(text) : true;
    return byBook && byType && byText;
  });
});

const typeStats = computed(() => {
  let character = 0;
  let other = 0;
  for (const item of filteredCards.value) {
    if (String(item.type || "").toLowerCase() === "character") {
      character += 1;
    } else {
      other += 1;
    }
  }
  return { character, other };
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

async function loadCards() {
  loading.value = true;
  try {
    const res = await api.getCardList(selectedBookId.value || null, settingsStore.settings);
    cards.value = Array.isArray(res?.cards) ? res.cards : [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "获取角色卡失败");
  } finally {
    loading.value = false;
  }
}

function onBookChange(bookId) {
  const selected = books.value.find((item) => item.book_id === bookId);
  appStateStore.patchAppState({
    current_book_id: bookId || "",
    current_book_name: selected?.book_name ?? "",
  });
  void loadCards();
}

function bookNameById(bookId) {
  const matched = books.value.find((item) => item.book_id === bookId);
  return matched?.book_name || bookId || "未知书籍";
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

function refreshCards() {
  return loadCards();
}

onMounted(async () => {
  await loadBooks();
  await loadCards();
});
</script>

<style scoped>
.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.book-select {
  width: min(100%, 320px);
}

.type-select {
  width: min(100%, 160px);
}

.keyword-input {
  width: min(100%, 280px);
}

.card-item {
  margin-bottom: 16px;
  border: 1px solid #dce8f4;
  background: linear-gradient(180deg, #ffffff 0%, #f9fcff 100%);
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    border-color 180ms ease;
}

.card-item:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 28px rgba(22, 53, 84, 0.12);
  border-color: #c8ddf5;
}

.card-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  color: var(--nw-title);
  font-size: 15px;
  font-weight: 700;
  word-break: break-all;
}

.card-book {
  margin-top: 8px;
  color: var(--nw-muted);
  font-size: 13px;
}

.card-intro {
  margin-top: 8px;
  color: var(--nw-text);
  font-size: 13px;
  line-height: 1.5;
  min-height: 40px;
}

.card-meta {
  margin-top: 8px;
  color: var(--nw-muted);
  font-size: 12px;
}

.card-fields {
  margin-top: 10px;
  padding: 8px;
  border: 1px solid #e2edf7;
  border-radius: 10px;
  background: #fcfeff;
}

.field-row {
  display: grid;
  grid-template-columns: 78px 1fr;
  gap: 8px;
  align-items: start;
  font-size: 12px;
  color: var(--nw-muted);
}

.field-row + .field-row {
  margin-top: 5px;
}

.field-label {
  color: #4f6a83;
  font-weight: 600;
}

.field-value {
  color: #31485f;
  word-break: break-all;
}

.card-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
