<template>
  <header class="page-header page-header-compact">
    <el-button type="primary" :icon="Plus" :disabled="!workspace.selectedId" @click="openEditor()">新建角色卡</el-button>
    <el-button type="success" :icon="Connection" @click="goToRelationshipGraph">人物关系图谱</el-button>
  </header>
  <div class="toolbar"><BookPicker /><el-input v-model="query" placeholder="搜索角色" :prefix-icon="Search" clearable /><el-button :icon="Refresh" :loading="loading" @click="load" /></div>
  <section v-loading="loading">
    <el-empty v-if="!visible.length && !loading" description="暂无角色卡" />
    <div class="asset-grid">
      <article v-for="card in visible" :key="card.id" class="asset-item">
        <h3>{{ card.name }}</h3><p class="excerpt">{{ card.intro || card.content.replace(/[#*]/g, '').slice(0, 100) }}</p><p class="muted">{{ dateText(card.updated_at) }}</p>
        <div class="icon-actions">
          <el-tooltip content="编辑角色卡"><el-button :icon="Edit" circle aria-label="编辑角色卡" @click="openEditor(card)" /></el-tooltip>
          <el-tooltip content="查看角色卡"><el-button :icon="View" circle aria-label="查看角色卡" @click="preview = card" /></el-tooltip>
          <el-tooltip content="开始角色对话"><el-button :icon="ChatDotRound" circle aria-label="开始角色对话" @click="startChat(card)" /></el-tooltip>
          <el-tooltip content="导出 Markdown"><el-button :icon="Download" circle aria-label="导出角色卡" @click="exportCard(card)" /></el-tooltip>
          <el-tooltip content="删除角色卡"><el-button :icon="Delete" circle type="danger" plain aria-label="删除角色卡" @click="remove(card)" /></el-tooltip>
        </div>
      </article>
    </div>
  </section>
  <el-dialog v-model="editing" :title="form.id ? '编辑角色卡' : '新建角色卡'" width="740px" :close-on-click-modal="false">
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item label="名称"><el-input v-model="form.name" maxlength="100" required /></el-form-item>
      <el-form-item label="简介"><el-input v-model="form.intro" type="textarea" :rows="2" maxlength="4000" /></el-form-item>
      <el-form-item label="角色卡正文"><el-input v-model="form.content" type="textarea" :rows="14" maxlength="50000" /></el-form-item>
      <el-button type="primary" :icon="Check" native-type="submit" :loading="saving">保存</el-button>
    </el-form>
  </el-dialog>
  <el-drawer :model-value="Boolean(preview)" :title="preview?.name" size="700px" @close="preview = null"><pre class="document-text">{{ preview?.content }}</pre></el-drawer>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Plus, Search, Refresh, Edit, View, ChatDotRound, Download, Delete, Check, Connection } from "@element-plus/icons-vue";
import BookPicker from "../../../components/BookPicker.vue";
import { api, download } from "../../../api/client";
import { useWorkspaceStore } from "../../../stores/workspace";
import { report, confirmDelete, dateText } from "../../../lib/ui";
const workspace = useWorkspaceStore(), router = useRouter();
const cards = ref([]), loading = ref(false), query = ref(""), editing = ref(false), saving = ref(false), preview = ref(null);
const form = reactive({ id: "", name: "", intro: "", content: "", book_id: "" });
const visible = computed(() => cards.value.filter((card) => `${card.name} ${card.intro}`.toLowerCase().includes(query.value.toLowerCase())));
let generation = 0;
async function load() {
  const bookId = workspace.selectedId, current = ++generation;
  cards.value = [];
  if (!bookId) return;
  loading.value = true;
  try { const result = await api.get("/cards", { params: { book_id: bookId } }); if (current === generation) cards.value = result.cards; }
  catch (error) { report(error); } finally { if (current === generation) loading.value = false; }
}
function openEditor(card) {
  Object.assign(form, { id: "", name: "", intro: "", content: "", book_id: workspace.selectedId }, card || {});
  editing.value = true;
}
async function save() {
  if (!form.name.trim() || saving.value) return;
  saving.value = true;
  try {
    const payload = { book_id: form.book_id, name: form.name, intro: form.intro, content: form.content };
    if (form.id) await api.patch(`/cards/${form.id}`, payload); else await api.post("/cards", payload);
    editing.value = false; await load(); ElMessage.success("已保存");
  } catch (error) { report(error); } finally { saving.value = false; }
}
async function remove(card) {
  if (!await confirmDelete(`删除角色卡“${card.name}”？已有对话会保留。`)) return;
  try { await api.delete(`/cards/${card.id}`); await load(); } catch (error) { report(error); }
}
async function exportCard(card) { try { await download(`/cards/${card.id}/export`, `${card.name}.md`); } catch (error) { report(error); } }
async function startChat(card) {
  try { const conversation = await api.post("/conversations", { card_id: card.id, title: card.name }); router.push({ path: "/chat", query: { conversation: conversation.id } }); }
  catch (error) { report(error); }
}
watch(() => workspace.selectedId, load);
onMounted(async () => { try { await workspace.refresh(); await load(); } catch (error) { report(error); } });

function goToRelationshipGraph() {
  router.push('/characters/relationships');
}
</script>
