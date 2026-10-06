<template>
  <div class="page-wrap">
    <el-card class="panel-card hero-card">
      <div class="hero-shell">
        <div class="hero-copy">
          <span class="hero-kicker">Upload Pipeline</span>
          <h3 class="page-title hero-title">文件上传与处理</h3>
          <p class="page-subtitle hero-subtitle">把文件上传到 OSS，再按任务状态追踪提取、解析和完成结果。</p>
        </div>
        <div class="hero-summary">
          <div class="hero-stat">
            <span class="hero-stat-label">未处理</span>
            <strong>{{ pendingUploads.length }}</strong>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-label">进行中</span>
            <strong>{{ processingUploads.length }}</strong>
          </div>
          <div class="hero-stat">
            <span class="hero-stat-label">已完成</span>
            <strong>{{ finishedUploads.length }}</strong>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="panel-card">
      <el-form label-position="top" @submit.prevent>
        <el-row>
          <el-col :span="24">
            <el-form-item label="书名">
              <el-input v-model="bookName" placeholder="可选，不填则使用文件名" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="作者（可选）">
              <el-input v-model="author" placeholder="可不填" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="语言（可选）">
              <el-select v-model="language" clearable placeholder="请选择语言" style="width: 100%">
                <el-option label="中文（zh-CN）" value="zh-CN" />
                <el-option label="英文（en）" value="en" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row>
          <el-col :span="24">
            <el-form-item>
              <div class="upload-stack">
                <div class="upload-action-row">
                  <el-upload
                    ref="uploadRef"
                    :auto-upload="false"
                    :limit="1"
                    :on-change="onFileChange"
                    :on-exceed="onFileExceed"
                    :show-file-list="false"
                  >
                    <el-button type="primary" plain>选择文件</el-button>
                  </el-upload>
                  <el-button type="primary" :loading="uploading" @click="startUpload">开始上传</el-button>
                  <div class="upload-hint upload-hint-inline">支持 epub / txt / pdf / image，source_type 会自动识别。</div>
                </div>

                <div class="selected-file-row">
                  <span class="selected-file-label">已选择文件：</span>
                  <span class="selected-file-name" :title="selectedFileName || '未选择文件'">{{ selectedFileName || "未选择文件" }}</span>
                </div>
              </div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <el-card class="panel-card">
      <template #header>
        <div class="section-header">
          <div>
            <div class="section-title">未处理任务</div>
            <div class="section-desc">等待提取的文件，直接从这里开始处理。</div>
          </div>
          <el-button :loading="loadingUploads" @click="loadUploads">刷新列表</el-button>
        </div>
      </template>

      <el-empty v-if="pendingUploads.length === 0" description="暂无未处理任务" />

      <div v-else class="task-list">
        <div v-for="item in pendingUploads" :key="item.book_id" class="task-item">
          <div class="task-topline">
            <div class="task-title-wrap">
              <div class="task-name-row">
                <div class="task-name" :title="item.book_name">{{ item.book_name || item.book_id }}</div>
                <el-tag class="status-tag status-tag-pending" effect="light" round>
                  {{ item.status || '待解析' }}
                </el-tag>
              </div>
              <div class="task-meta task-meta-inline">文件：{{ item.file_name || item.book_name || item.book_id }}</div>
            </div>

            <div class="task-actions">
              <el-button text type="primary" :disabled="!item.file_url" @click="openFile(item.file_url)">
                文件下载
              </el-button>

              <el-button
                type="primary"
                size="small"
                :loading="extractingBookId === item.book_id"
                @click="extractBook(item)"
              >
                进行提取
              </el-button>
            </div>
          </div>

          <div class="task-details">
            <div class="task-meta">文件：{{ item.file_name || item.book_name || item.book_id }}</div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="panel-card">
      <template #header>
        <div class="section-header">
          <div>
            <div class="section-title">进行中任务</div>
            <div class="section-desc">正在解析或提取中的任务，带有进度反馈。</div>
          </div>
          <span class="section-chip">{{ processingUploads.length }} 个进行中</span>
        </div>
      </template>

      <el-empty v-if="processingUploads.length === 0" description="暂无进行中任务" />

      <div v-else class="task-list">
        <div v-for="item in processingUploads" :key="item.book_id" class="task-item">
          <div class="task-topline">
            <div class="task-title-wrap">
              <div class="task-name-row">
                <div class="task-name" :title="item.book_name">{{ item.book_name || item.book_id }}</div>
                <el-tag class="status-tag status-tag-processing" effect="light" round>解析中</el-tag>
              </div>
            </div>
            <div class="task-actions">
              <el-button text type="primary" :disabled="!item.file_url" @click="openFile(item.file_url)">文件下载</el-button>
              <el-button type="primary" size="small" :loading="extractingBookId === item.book_id" @click="extractBook(item)">进行提取</el-button>
            </div>
          </div>
          <div class="task-details">
            <div class="task-meta">文件：{{ item.file_name || item.book_name || item.book_id }}</div>
            <div class="progress-box">
              <el-progress :percentage="item.progress ?? 0" :status="item.status === '失败' ? 'exception' : undefined" />
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <el-card class="panel-card">
      <template #header>
        <div class="section-header">
          <div>
            <div class="section-title">处理完任务</div>
            <div class="section-desc">已完成的文件可以直接重新下载。</div>
          </div>
          <span class="section-chip section-chip-success">{{ finishedUploads.length }} 个已完成</span>
        </div>
      </template>

      <el-empty v-if="finishedUploads.length === 0" description="暂无已完成任务" />

      <div v-else class="task-list">
        <div v-for="item in finishedUploads" :key="item.book_id" class="task-item">
          <div class="task-topline">
            <div class="task-title-wrap">
              <div class="task-name-row">
                <div class="task-name" :title="item.book_name">{{ item.book_name || item.book_id }}</div>
                <el-tag class="status-tag status-tag-done" effect="light" round>已完成</el-tag>
              </div>
            </div>
            <div class="task-actions">
              <el-button text type="primary" :disabled="!item.file_url" @click="openFile(item.file_url)">文件下载</el-button>
            </div>
          </div>
          <div class="task-details">
            <div class="task-meta">上传文件：{{ item.file_name || item.book_name || item.book_id }}</div>
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

const bookName = ref("");
const author = ref("");
const language = ref("");
const selectedFile = ref(null);
const selectedFileName = ref("");
const uploadRef = ref(null);
const uploading = ref(false);
const loadingUploads = ref(false);
const extractingBookId = ref("");
const uploads = ref([]);

const pendingUploads = computed(() => uploads.value.filter((item) => item.status === "待解析"));
const processingUploads = computed(() => uploads.value.filter((item) => item.status === "解析中"));
const finishedUploads = computed(() => uploads.value.filter((item) => item.status === "已完成"));

function onFileChange(file) {
  selectedFile.value = file.raw ?? null;
  selectedFileName.value = file?.name || file?.raw?.name || "";
}

function onFileExceed(files) {
  const nextFile = Array.isArray(files) && files.length > 0 ? files[0] : null;
  if (!nextFile) {
    return;
  }

  selectedFile.value = nextFile;
  selectedFileName.value = nextFile.name || "";

  // 超过 limit=1 时，手动替换上传组件内部列表，确保 UI 和状态一致。
  if (uploadRef.value?.clearFiles) {
    uploadRef.value.clearFiles();
  }
  if (uploadRef.value?.handleStart) {
    uploadRef.value.handleStart(nextFile);
  }
}

async function startUpload() {
  if (!selectedFile.value) {
    ElMessage.error("请先选择文件");
    return;
  }

  uploading.value = true;
  try {
    const pickedName = bookName.value || selectedFile.value.name;
    const res = await api.uploadFile(selectedFile.value, pickedName, settingsStore.settings, {
      author: author.value,
      language: language.value,
    });

    appStateStore.patchAppState({
      current_task_id: res.task_id,
      current_book_id: res.book_id,
      current_book_name: pickedName,
    });

    await loadUploads();
    ElMessage.success("上传成功，已创建任务");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function loadUploads() {
  loadingUploads.value = true;
  try {
    const res = await api.getBooks(settingsStore.settings);
    uploads.value = Array.isArray(res?.books) ? res.books : [];
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载任务失败");
  } finally {
    loadingUploads.value = false;
  }
}

async function extractBook(item) {
  const bookId = item?.book_id;
  if (!bookId) {
    ElMessage.warning("无效的书籍记录");
    return;
  }

  extractingBookId.value = bookId;
  try {
    const res = await api.startExtractTask(
      {
        book_id: bookId,
        run_summary: true,
        run_card: false,
      },
      settingsStore.settings,
    );

    appStateStore.patchAppState({
      current_task_id: res.task_id,
      current_book_id: bookId,
      current_book_name: item?.book_name || bookId,
    });

    ElMessage.success(res.message || "提取任务已创建");
    await loadUploads();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提取失败");
  } finally {
    extractingBookId.value = "";
  }
}

function openFile(fileUrl) {
  if (!fileUrl) {
    ElMessage.warning("暂无可下载文件");
    return;
  }

  window.open(fileUrl, "_blank", "noopener,noreferrer");
}

onMounted(() => {
  loadUploads();
});
</script>

<style scoped>
.task-row {
  margin-bottom: 12px;
}

.meta-label {
  color: #6b7280;
  font-size: 13px;
}

.meta-value {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 600;
}

.upload-hint {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.upload-action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: nowrap;
}

.upload-hint-inline {
  margin-top: 0;
  white-space: nowrap;
}

.upload-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.selected-file-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 7px 10px;
  border-radius: 10px;
  background: rgba(47, 125, 212, 0.06);
}

.selected-file-label {
  color: #6b7280;
  font-size: 13px;
  flex-shrink: 0;
}

.selected-file-name {
  color: #1f2937;
  font-size: 13px;
  line-height: 1.45;
  word-break: break-all;
}

.pending-head {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.task-item {
  padding: 16px 18px;
  border: 1px solid rgba(34, 71, 110, 0.08);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(249, 252, 255, 0.96) 100%);
  box-shadow: 0 10px 24px rgba(22, 45, 72, 0.06);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}

.task-item:hover {
  transform: translateY(-2px);
  border-color: rgba(47, 125, 212, 0.18);
  box-shadow: 0 16px 30px rgba(22, 45, 72, 0.09);
}

.hero-card {
  overflow: hidden;
  position: relative;
  border: 1px solid rgba(47, 125, 212, 0.14);
  background:
    radial-gradient(circle at top right, rgba(47, 125, 212, 0.12), transparent 34%),
    linear-gradient(135deg, #ffffff 0%, #f8fbff 55%, #f3fbf7 100%);
}

.hero-card::after {
  content: "";
  position: absolute;
  inset: auto -40px -40px auto;
  width: 170px;
  height: 170px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(47, 125, 212, 0.12) 0%, rgba(47, 125, 212, 0) 72%);
  pointer-events: none;
}

.hero-shell {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}

.hero-copy {
  min-width: 0;
  flex: 1;
}

.hero-kicker {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(47, 125, 212, 0.1);
  color: #2563a7;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.hero-title {
  margin-top: 12px;
}

.hero-subtitle {
  max-width: 640px;
}

.hero-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(96px, 1fr));
  gap: 10px;
  flex-shrink: 0;
}

.hero-stat {
  min-width: 96px;
  padding: 14px 16px;
  border-radius: 16px;
  border: 1px solid rgba(47, 125, 212, 0.12);
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(8px);
}

.hero-stat-label {
  display: block;
  color: var(--nw-muted);
  font-size: 12px;
}

.hero-stat strong {
  display: block;
  margin-top: 6px;
  color: var(--nw-title);
  font-size: 26px;
  line-height: 1;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
}

.section-title {
  color: var(--nw-title);
  font-size: 16px;
  font-weight: 700;
}

.section-desc {
  margin-top: 4px;
  color: var(--nw-muted);
  font-size: 12px;
}

.section-chip {
  display: inline-flex;
  align-items: center;
  padding: 7px 12px;
  border-radius: 999px;
  background: #fff4df;
  color: #a56912;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.section-chip-success {
  background: #e7f8ee;
  color: #17764c;
}

.task-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.status-tag {
  border: 0;
  font-weight: 700;
}

.status-tag-pending {
  color: #946200;
  background: #fff4da;
}

.status-tag-processing {
  color: #1e5fa5;
  background: #e7f1ff;
}

.status-tag-done {
  color: #17764c;
  background: #e7f8ee;
}

.task-name {
  font-size: 14px;
  font-weight: 600;
  color: #111827;
  line-height: 1.35;
  word-break: break-all;
}

.task-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
  word-break: break-all;
}

.task-topline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.task-title-wrap {
  min-width: 0;
  flex: 1;
}

.task-details {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed rgba(30, 58, 90, 0.12);
}

.task-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.task-actions :deep(.el-button) {
  border-radius: 999px;
}

.task-actions-vertical {
  flex-direction: column;
  align-items: flex-end;
}

.progress-box {
  min-width: 220px;
}

.panel-card :deep(.el-card__header) {
  padding-bottom: 0;
  border-bottom: 0;
  background: transparent;
}

.panel-card :deep(.el-card__body) {
  padding-top: 16px;
}

.panel-card + .panel-card {
  margin-top: 2px;
}

@media (max-width: 980px) {
  .hero-shell {
    align-items: stretch;
    flex-direction: column;
  }

  .hero-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: 100%;
  }

  .task-item {
    flex-direction: column;
  }

  .task-topline {
    width: 100%;
    flex-direction: column;
  }

  .task-actions-vertical {
    align-items: flex-start;
  }

  .progress-box {
    min-width: 100%;
  }
}
</style>
