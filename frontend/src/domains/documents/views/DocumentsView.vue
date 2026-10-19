<template>
  <header class="page-header">
    <div><h1>作品库</h1><p class="muted">{{ workspace.books.length }} 部作品</p></div>
    <el-button type="primary" :icon="Upload" @click="openUpload">上传作品</el-button>
  </header>
  <div class="toolbar"><el-input v-model="query" placeholder="搜索作品或作者" :prefix-icon="Search" clearable /><el-button :icon="Refresh" :loading="workspace.loading" @click="refresh" aria-label="刷新作品" /></div>
  <el-table :data="filtered" empty-text="暂无作品" row-key="book_id">
    <el-table-column label="作品" min-width="210"><template #default="{ row }"><strong>{{ row.title }}</strong><div class="muted">{{ row.author || "作者未填写" }} · {{ row.source_type.toUpperCase() }}</div><div v-if="row.err_message" class="error-text">{{ row.err_message }}</div></template></el-table-column>
    <el-table-column label="状态" width="105"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
    <el-table-column prop="chapter_count" label="章节" width="80" />
    <el-table-column label="进度" min-width="130"><template #default="{ row }"><el-progress :percentage="row.progress" :status="row.status === 'failed' ? 'exception' : undefined" /></template></el-table-column>
    <el-table-column label="添加时间" width="175"><template #default="{ row }">{{ dateText(row.created_at) }}</template></el-table-column>
    <el-table-column label="操作" width="300" fixed="right"><template #default="{ row }"><div class="icon-actions">
      <el-tooltip content="查看章节"><el-button :icon="Reading" circle :disabled="!row.chapter_count" aria-label="查看章节" @click="openChapters(row)" /></el-tooltip>
      <el-tooltip content="解析章节"><el-button :icon="Document" circle :disabled="row.status === 'processing'" aria-label="解析章节" @click="parse(row)" /></el-tooltip>
      <el-tooltip content="提取作品资料"><el-button :icon="MagicStick" circle :disabled="row.status === 'processing'" aria-label="提取作品资料" @click="openExtract(row)" /></el-tooltip>
      <el-tooltip content="查看任务"><el-button :icon="Tickets" circle aria-label="查看任务" @click="openTask(row)" /></el-tooltip>
      <el-tooltip content="查看资料"><el-button :icon="Collection" circle aria-label="查看资料" @click="workspace.selectedId = row.book_id; router.push('/summary')" /></el-tooltip>
      <el-tooltip content="下载源文件"><el-button :icon="Download" circle aria-label="下载源文件" @click="downloadBook(row)" /></el-tooltip>
      <el-tooltip content="删除作品"><el-button :icon="Delete" circle type="danger" plain :disabled="row.status === 'processing'" aria-label="删除作品" @click="remove(row)" /></el-tooltip>
    </div></template></el-table-column>
  </el-table>
  <el-dialog v-model="showUpload" title="上传作品" width="500px" :close-on-click-modal="!uploading" :before-close="closeUpload">
    <el-form label-position="top" @submit.prevent="submitUpload">
      <el-form-item label="源文件（单个文件最大 20 MB）"><input ref="fileInput" type="file" multiple accept=".txt,.md,.epub,.pdf,.docx" @change="selectFiles" /></el-form-item>
      <div v-if="files.length" class="muted upload-selection">{{ files.length === 1 ? file.name : `已选择 ${files.length} 个文件` }}</div>
      <template v-if="files.length <= 1">
        <el-form-item label="作品名称"><el-input v-model="metadata.title" maxlength="200" :placeholder="file?.name || '未命名作品'" /></el-form-item>
        <el-form-item label="作者"><el-input v-model="metadata.author" maxlength="200" /></el-form-item>
        <el-form-item label="语言"><el-select v-model="metadata.language"><el-option label="中文" value="zh-CN" /><el-option label="英语" value="en" /></el-select></el-form-item>
      </template>
      <div v-if="batchResults.length" class="upload-results" role="status"><div v-for="item in batchResults" :key="item.filename" class="upload-result"><span>{{ item.filename }}</span><span :class="item.error ? 'error-text' : 'success-text'">{{ item.error || "上传成功" }}</span></div></div>
      <el-button type="primary" :icon="Upload" native-type="submit" :loading="uploading" :disabled="!files.length">上传</el-button>
    </el-form>
  </el-dialog>
  <el-dialog :model-value="Boolean(extractBook)" title="提取作品资料" width="min(92vw, 530px)" :close-on-click-modal="!starting" :show-close="!starting" :close-on-press-escape="!starting" @close="extractBook = null">
    <h3>{{ extractBook?.title }}</h3>
    <p>提取模型：{{ extractionModel?.model?.name || extractionModel?.message || '加载中' }}</p>
    <p class="muted">已覆盖章节：{{ formatCoverage(coverage) }}</p>
    <el-form label-position="top" class="spaced">
      <el-form-item label="提取范围"><el-radio-group v-model="range"><el-radio-button value="all">全部章节</el-radio-button><el-radio-button value="limited">前 N 章</el-radio-button><el-radio-button value="interval">连续区间</el-radio-button></el-radio-group></el-form-item>
      <el-form-item v-if="range === 'limited'" label="章节数"><el-input-number v-model="limit" :min="1" :max="Math.min(extractBook?.chapter_count || 1000, 1000)" /></el-form-item>
      <div v-if="range === 'interval'" class="extraction-range"><el-form-item label="起始章节"><el-input-number v-model="chapterStart" :min="1" :max="extractBook?.chapter_count || 100000" /></el-form-item><el-form-item label="结束章节"><el-input-number v-model="chapterEnd" :min="chapterStart || 1" :max="extractBook?.chapter_count || 100000" /></el-form-item></div>
      <el-form-item label="强制重算选定章节"><el-switch v-model="force" aria-label="强制重算选定章节" /></el-form-item>
    </el-form>
    <div v-if="scope" class="scope-preview" role="status"><strong>第 {{ scope.from }}–{{ scope.to }} 章 · 共 {{ scope.count }} 章</strong><span>尚未覆盖 {{ scope.uncovered }} 章 · 已覆盖 {{ scope.covered }} 章</span><el-tag v-if="force" type="warning" effect="plain">选定范围全部重新计算</el-tag><el-tag v-else type="info" effect="plain">复用有效检查点</el-tag></div>
    <p v-else-if="extractBook?.chapter_count" class="error-text" role="alert">请选择有效的章节范围</p>
    <template #footer><el-button :disabled="starting" @click="extractBook = null">取消</el-button><el-button type="primary" :icon="MagicStick" :disabled="extractionModel?.status !== 'healthy' || (Boolean(extractBook?.chapter_count) && !scope)" :loading="starting" @click="extract">开始提取</el-button></template>
  </el-dialog>
  <ChapterReader v-model="showChapters" :book-id="chapterBook?.book_id" :title="chapterBook?.title" />
  <TaskDetail v-model="showTask" :task-id="taskId" @changed="refresh" />
</template>
<script setup>
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Upload, Search, Refresh, Reading, Document, MagicStick, Collection, Download, Delete, Tickets } from "@element-plus/icons-vue";
import ChapterReader from "../components/ChapterReader.vue";
import { formatCoverage } from "../coverage";
import { extractionScope } from "../extraction";
import TaskDetail from "../../workflow/components/TaskDetail.vue";
import { api, upload, uploadBatch, download } from "../../../api/client";
import { useWorkspaceStore } from "../../../stores/workspace";
import { usePolling, report, confirmDelete, statusText, statusType, dateText } from "../../../lib/ui";
const workspace = useWorkspaceStore(), router = useRouter();
const query = ref(""), showUpload = ref(false), uploading = ref(false), files = ref([]), fileInput = ref(null), batchResults = ref([]);
const file = computed(() => files.value[0] || null);
const metadata = reactive({ title: "", author: "", language: "zh-CN" });
const filtered = computed(() => workspace.books.filter((book) => `${book.title} ${book.author}`.toLowerCase().includes(query.value.toLowerCase())));
const refresh = usePolling(() => workspace.refresh());
const extractBook = ref(null), range = ref("all"), limit = ref(null), starting = ref(false);
const showChapters = ref(false), chapterBook = ref(null);
const chapterStart = ref(1), chapterEnd = ref(1), force = ref(false), coverage = ref([]), extractionModel = ref(null);
const showTask = ref(false), taskId = ref("");
const scope = computed(() => extractionScope(extractBook.value?.chapter_count, {
  range: range.value, limit: limit.value, start: chapterStart.value, end: chapterEnd.value, coverage: coverage.value,
}));
let extractGeneration = 0;
async function openExtract(book) {
  const current = ++extractGeneration;
  extractBook.value = book; range.value = "all"; limit.value = 1; chapterStart.value = 1; chapterEnd.value = book.chapter_count || 1; force.value = false; extractionModel.value = null; coverage.value = [];
  try {
    const [selection, data] = await Promise.all([api.get("/settings/selection"), api.get("/summaries", { params: { book_id: book.book_id } })]);
    if (current === extractGeneration) { extractionModel.value = selection.statuses.extraction; coverage.value = data.coverage || []; }
  } catch (error) { report(error); }
}
async function openTask(book) {
  try {
    const result = await api.get("/tasks", { params: { book_id: book.book_id } });
    if (!result.tasks.length) { ElMessage.info("暂无任务"); return; }
    taskId.value = result.tasks[0].id; showTask.value = true;
  } catch (error) { report(error); }
}
function openUpload() { batchResults.value = []; showUpload.value = true; }
function closeUpload(done) { if (!uploading.value) done(); }
function selectFiles(event) { files.value = Array.from(event.target.files || []); batchResults.value = []; if (files.value.length > 1) { metadata.title = ""; metadata.author = ""; } }
function resetUploadSelection(keepResults = false) { files.value = []; if (!keepResults) batchResults.value = []; if (fileInput.value) fileInput.value.value = ""; }
async function submitUpload() {
  if (!files.value.length || uploading.value) return;
  if (files.value.length === 1 && file.value.size > 20 * 1024 * 1024) { report(new Error("文件不能超过 20 MB")); return; }
  uploading.value = true;
  try {
    if (files.value.length === 1) { const book = await upload("/books", file.value, metadata); await workspace.refresh(); workspace.selectedId = book.book_id; showUpload.value = false; resetUploadSelection(); metadata.title = ""; metadata.author = ""; ElMessage.success("上传成功"); }
    else { const result = await uploadBatch(files.value); batchResults.value = result.items || []; resetUploadSelection(true); await workspace.refresh(); if (result.failed) ElMessage.warning(`已上传 ${result.succeeded} 个，${result.failed} 个失败`); else ElMessage.success(`成功上传 ${result.succeeded} 个作品`); }
  } catch (error) { report(error); } finally { uploading.value = false; }
}
async function parse(book) { try { await api.post(`/books/${book.book_id}/parse`); await refresh(); ElMessage.success("解析任务已创建"); } catch (error) { report(error); } }
async function extract() {
  if (starting.value || !extractBook.value || (extractBook.value.chapter_count && !scope.value)) return;
  starting.value = true;
  try {
    const result = await api.post("/extract", { book_id: extractBook.value.book_id, force: force.value,
      max_chapters: range.value === "limited" ? limit.value || 1 : null,
      chapter_start: range.value === "interval" ? chapterStart.value : null,
      chapter_end: range.value === "interval" ? chapterEnd.value : null });
    extractBook.value = null; taskId.value = result.task_id; showTask.value = true; await refresh();
    ElMessage.success("提取任务已创建");
  } catch (error) { report(error); } finally { starting.value = false; }
}
async function remove(book) { if (!await confirmDelete(`删除《${book.title}》及其章节、资料和角色卡？此操作不可恢复。`)) return; try { await api.delete(`/books/${book.book_id}`); await refresh(); } catch (error) { report(error); } }
async function downloadBook(book) { try { await download(`/books/${book.book_id}/source`, book.file_name); } catch (error) { report(error); } }
function openChapters(book) { chapterBook.value = book; showChapters.value = true; }
</script>
<style scoped>
.extraction-range { display: flex; flex-wrap: wrap; gap: 16px; }
.scope-preview { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; border-top: 1px solid var(--pw-border); padding-top: 16px; font-size: 13px; }
.scope-preview strong, .scope-preview > span { width: 100%; }
</style>
