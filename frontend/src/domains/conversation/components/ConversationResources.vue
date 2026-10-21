<template>
  <div class="conversation-resources">
    <el-button text :icon="Collection" @click="openSources()">来源 <small v-if="sourceList.length">{{ sourceList.length }}</small></el-button>
    <el-button text :icon="Memo" @click="showMemories = true">记忆 <el-tag v-if="failedJobs.length" size="small" type="warning">{{ failedJobs.length }}</el-tag></el-button>
    <el-tooltip content="会话设置" placement="top"><el-button text :icon="Setting" aria-label="会话设置" :disabled="disabled" @click="openSettings" /></el-tooltip>
  </div>
  <el-drawer v-model="showSources" title="本轮参考来源" size="min(100vw, 480px)" append-to-body>
    <el-empty v-if="!sourceList.length" description="此轮没有检索材料" />
    <article v-for="item in sourceList" :key="item.id" class="conversation-reference">
      <strong>{{ item.title }}</strong>
      <small v-if="item.chapter_no">第 {{ item.chapter_no }} 章 · {{ item.chapter_title }}</small>
      <p>{{ item.quote || item.content }}</p>
      <el-button v-if="item.chapter_id" plain size="small" :icon="Reading" @click="readSource(item)">查看原文</el-button>
      <small v-if="item.chapter_id && !validCitation(item)">位置未核验，不生成高亮</small>
    </article>
  </el-drawer>
  <ChapterReader v-model="showReader" :book-id="readerSource?.book_id" :chapter-id="readerSource?.chapter_id"
    :citation="readerSource && validCitation(readerSource) ? readerSource : null" />
  <el-drawer v-model="showMemories" title="当前分支记忆" size="min(100vw, 520px)" append-to-body>
    <div class="memory-toolbar">
      <el-button plain :icon="Plus" :disabled="disabled" @click="editMemory()">添加记忆</el-button>
      <el-tooltip content="刷新记忆" placement="top"><el-button text :icon="Refresh" aria-label="刷新记忆" @click="loadMemories" /></el-tooltip>
    </div>
    <div v-for="job in failedJobs" :key="job.id" class="memory-warning" role="status">
      <span>回复已保存，记忆更新失败：{{ job.error }}</span>
      <el-button size="small" text :disabled="disabled" @click="retryJob(job)">重试提炼</el-button>
    </div>
    <p v-if="activeJobs.length" class="muted" role="status">正在更新记忆…</p>
    <el-empty v-if="!memoryData.items.length" description="此分支暂无记忆" />
    <article v-for="item in memoryData.items" :key="item.memory_id" class="conversation-reference memory-item" :class="{ 'is-deleted': item.deleted }">
      <div class="memory-heading"><strong>{{ item.memory_key }}</strong><el-tag size="small" effect="plain">{{ categories[item.category] }}</el-tag><el-tag v-if="item.deleted" size="small" type="info">已删除</el-tag><el-icon v-else-if="item.locked" aria-label="人工锁定"><Lock /></el-icon></div>
      <p>{{ item.content }}</p>
      <small>{{ item.origin === 'manual' ? '人工版本' : '自动提炼' }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</small>
      <div class="memory-actions">
        <el-button v-if="!item.deleted" text size="small" :icon="EditPen" :disabled="disabled" @click="editMemory(item)">编辑</el-button>
        <el-button v-if="!item.deleted" text size="small" :icon="Delete" :disabled="disabled" @click="deleteMemory(item)">删除</el-button>
        <el-button text size="small" :icon="RefreshLeft" :disabled="disabled" @click="undoMemory(item)">撤销此版本</el-button>
      </div>
    </article>
  </el-drawer>
  <el-dialog v-model="showEditor" :title="editing ? '编辑记忆' : '添加记忆'" width="min(92vw, 480px)" append-to-body>
    <el-form label-position="top" @submit.prevent="saveMemory">
      <el-form-item label="类型"><el-select v-model="memoryForm.category"><el-option v-for="(label, key) in categories" :key="key" :label="label" :value="key" /></el-select></el-form-item>
      <el-form-item label="事项名"><el-input v-model="memoryForm.key" maxlength="120" /></el-form-item>
      <el-form-item label="记忆内容"><el-input v-model="memoryForm.content" type="textarea" :rows="5" maxlength="1500" /></el-form-item>
      <el-checkbox v-model="memoryForm.locked">人工锁定，不允许自动覆盖</el-checkbox>
      <div class="dialog-actions"><el-button @click="showEditor = false">取消</el-button><el-button type="primary" native-type="submit" :loading="saving" :disabled="disabled || !memoryForm.key.trim() || !memoryForm.content.trim()">保存记忆</el-button></div>
    </el-form>
  </el-dialog>
  <el-drawer v-model="showSettings" title="会话设置" size="min(100vw, 420px)" append-to-body>
    <el-form label-position="top" @submit.prevent="saveSettings">
      <el-form-item label="对话模式"><el-radio-group v-model="settings.mode"><el-radio-button value="assistant">创作助手</el-radio-button><el-radio-button value="roleplay">角色扮演</el-radio-button></el-radio-group></el-form-item>
      <el-form-item label="关联作品"><el-select v-model="settings.book_id" clearable filterable :disabled="Boolean(conversation.card_id)" class="full-width"><el-option v-for="book in books" :key="book.book_id" :value="book.book_id" :label="book.title" /></el-select></el-form-item>
      <el-form-item label="作品知识检索"><el-switch v-model="settings.knowledge_enabled" aria-label="作品知识检索" /></el-form-item>
      <el-form-item label="回复后自动保存记忆"><el-switch v-model="settings.memory_enabled" aria-label="自动保存记忆" /></el-form-item>
      <el-alert title="检索当前有效作品资料，不提供章节级防剧透。自动记忆提炼会额外调用本轮模型。" type="info" :closable="false" />
      <div class="dialog-actions"><el-button type="primary" native-type="submit" :loading="saving" :disabled="disabled">保存设置</el-button></div>
    </el-form>
  </el-drawer>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { Collection, Delete, EditPen, Lock, Memo, Plus, Reading, Refresh, RefreshLeft, Setting } from "@element-plus/icons-vue";
import { api } from "../../../api/client";
import { confirmDelete, report } from "../../../lib/ui";
import ChapterReader from "../../documents/components/ChapterReader.vue";
const props = defineProps({ conversation: { type: Object, required: true }, disabled: Boolean, sources: { type: Array, default: () => [] } });
const emit = defineEmits(["updated"]);
const showSources = ref(false), showMemories = ref(false), showReader = ref(false), showEditor = ref(false), showSettings = ref(false);
const sourceList = ref([]), readerSource = ref(null), books = ref([]), saving = ref(false), editing = ref(null);
const memoryData = ref({ items: [], jobs: [] });
const memoryForm = reactive({ category: "experience", key: "", content: "", locked: true, source_ids: [] });
const settings = reactive({ mode: "assistant", book_id: null, knowledge_enabled: true, memory_enabled: true });
const categories = { scene: "场景", experience: "经历", relationship: "关系", promise: "承诺", open_item: "未完成" };
const failedJobs = computed(() => memoryData.value.jobs.filter(j => j.status === "failed"));
const activeJobs = computed(() => memoryData.value.jobs.filter(j => ["queued", "running"].includes(j.status)));
let memoryEpoch = 0, poll;
function validCitation(item) { return Number.isInteger(item.start) && Number.isInteger(item.end) && item.end > item.start; }
function openSources(items) { sourceList.value = items || props.sources; showSources.value = true; }
function readSource(item) { readerSource.value = item; showReader.value = true; }
defineExpose({ openSources });
async function loadMemories() {
  clearTimeout(poll);
  const epoch = ++memoryEpoch, id = props.conversation.id;
  try {
    const result = await api.get(`/conversations/${id}/memories`);
    if (epoch !== memoryEpoch || props.conversation.id !== id) return;
    memoryData.value = result;
    if (activeJobs.value.length) poll = setTimeout(loadMemories, 1200);
  } catch (err) { if (epoch === memoryEpoch) report(err); }
}
function editMemory(item) {
  editing.value = item || null;
  Object.assign(memoryForm, { category: item?.category || "experience", key: item?.memory_key || "",
    content: item?.content || "", locked: item?.origin === "manual" ? Boolean(item.locked) : true, source_ids: item?.source_ids || [] });
  showEditor.value = true;
}
function accept(result) { memoryData.value = result; if (result.conversation) emit("updated", result.conversation); }
async function saveMemory() {
  if (saving.value || props.disabled) return;
  saving.value = true;
  try {
    const path = `/conversations/${props.conversation.id}/memories`;
    const payload = { ...memoryForm, expected_version: editing.value?.id || null };
    accept(editing.value ? await api.put(`${path}/${editing.value.memory_id}`, payload) : await api.post(path, payload));
    showEditor.value = false;
  } catch (err) { report(err); } finally { saving.value = false; }
}
async function deleteMemory(item) {
  if (!await confirmDelete(`删除记忆“${item.memory_key}”？删除只影响当前分支，可撤销。`)) return;
  try { accept(await api.delete(`/conversations/${props.conversation.id}/memories/${item.memory_id}`)); } catch (err) { report(err); }
}
async function undoMemory(item) {
  try { accept(await api.post(`/conversations/${props.conversation.id}/memories/${item.memory_id}/undo`)); } catch (err) { report(err); }
}
async function retryJob(job) {
  try { await api.post(`/conversations/${props.conversation.id}/memory-jobs/${job.id}/retry`); await loadMemories(); } catch (err) { report(err); }
}
async function openSettings() {
  Object.assign(settings, { mode: props.conversation.mode, book_id: props.conversation.book_id,
    knowledge_enabled: Boolean(props.conversation.knowledge_enabled), memory_enabled: Boolean(props.conversation.memory_enabled) });
  showSettings.value = true;
  try { books.value = (await api.get("/books")).books || []; } catch (err) { report(err); }
}
async function saveSettings() {
  if (saving.value || props.disabled) return;
  saving.value = true;
  try {
    const id = props.conversation.id;
    await api.patch(`/conversations/${id}`, { ...settings, book_id: settings.book_id || null });
    emit("updated", await api.get(`/conversations/${id}`)); showSettings.value = false;
  } catch (err) { report(err); } finally { saving.value = false; }
}
watch(() => [props.conversation.id, props.conversation.active_leaf_id], loadMemories, { immediate: true });
watch(() => props.sources, value => { if (!showSources.value) sourceList.value = value; }, { immediate: true });
watch(() => props.conversation.id, () => { showEditor.value = false; showSettings.value = false; showSources.value = false; showMemories.value = false; });
onBeforeUnmount(() => { memoryEpoch++; clearTimeout(poll); });
</script>

<style scoped>
.conversation-resources, .memory-heading, .memory-toolbar, .memory-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.conversation-resources .el-button + .el-button { margin-left: 0; }
.conversation-resources small { margin-left: 5px; }
.conversation-reference { border-bottom: 1px solid var(--pw-border); padding: 16px 0; overflow-wrap: anywhere; }
.conversation-reference strong { font-size: 14px; }
.conversation-reference small { display: block; color: #7b867f; margin: 6px 0; font-size: 12px; }
.conversation-reference p { white-space: pre-wrap; line-height: 1.8; font-size: 13px; }
.memory-heading strong { margin-right: auto; }
.is-deleted { opacity: .65; }
.memory-warning { margin: 12px 0; color: #a45c26; font-size: 13px; overflow-wrap: anywhere; }
.dialog-actions { margin-top: 20px; }
</style>
