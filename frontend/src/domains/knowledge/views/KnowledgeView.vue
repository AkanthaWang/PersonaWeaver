<template>
  <header class="page-header page-header-compact">
    <div><p class="eyebrow">KNOWLEDGE BASE</p><h1>知识库</h1></div>
    <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
  </header>
  <section class="toolbar">
    <el-select v-model="bookId" placeholder="选择作品" filterable @change="load">
      <el-option v-for="book in workspace.books" :key="book.book_id" :label="book.title" :value="book.book_id" />
    </el-select>
    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="人物" name="characters" />
      <el-tab-pane label="事件" name="events" />
      <el-tab-pane label="关系" name="relations" />
      <el-tab-pane label="伏笔" name="clues" />
      <el-tab-pane label="待审核" name="reviews" />
    </el-tabs>
  </section>
  <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" />
  <el-table v-loading="loading" :data="rows" empty-text="暂无知识记录">
    <el-table-column v-if="tab === 'characters'" prop="canonical_name" label="人物" min-width="160" />
    <el-table-column v-if="tab === 'characters'" label="别名" min-width="200"><template #default="{ row }">{{ aliases(row.aliases_json) }}</template></el-table-column>
    <el-table-column v-if="tab === 'events'" prop="title" label="事件" min-width="180" />
    <el-table-column v-if="tab === 'events'" prop="description" label="描述" min-width="300" show-overflow-tooltip />
    <el-table-column v-if="tab === 'relations'" label="关系" min-width="300"><template #default="{ row }">{{ row.subject_id }} → {{ row.relation_type }} → {{ row.object_id }}</template></el-table-column>
    <el-table-column v-if="tab === 'clues'" prop="title" label="线索" min-width="180" />
    <el-table-column v-if="tab === 'clues'" prop="state" label="状态" width="130" />
    <el-table-column v-if="tab === 'reviews'" prop="review_type" label="审核类型" width="140" />
    <el-table-column v-if="tab === 'reviews'" prop="payload_json" label="内容" min-width="360" show-overflow-tooltip />
    <el-table-column v-if="tab === 'reviews'" label="操作" width="180" fixed="right">
      <template #default="{ row }">
        <el-button size="small" type="success" @click="resolve(row, 'approve')">通过</el-button>
        <el-button size="small" type="danger" @click="resolve(row, 'reject')">拒绝</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { ref, watch } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { api } from "../../../api/client.js";
import { useWorkspaceStore } from "../../../stores/workspace.js";
import { report } from "../../../lib/ui.js";

const workspace = useWorkspaceStore();
const bookId = ref(workspace.selectedId), tab = ref("characters");
const rows = ref([]), loading = ref(false), error = ref("");
const aliases = (value) => { try { return JSON.parse(value || "[]").join("、"); } catch { return ""; } };
async function load() {
  if (!bookId.value) return;
  loading.value = true; error.value = "";
  try {
    rows.value = await api.get(`/books/${bookId.value}/knowledge/${tab.value}`);
  } catch (err) { error.value = err.message; } finally { loading.value = false; }
}
async function resolve(row, action) {
  try {
    await api.post(`/books/${bookId.value}/knowledge/reviews/${row.id}/resolve`, { action });
    await load();
  } catch (err) { report(err); }
}
watch(() => workspace.selectedId, (value) => { bookId.value = value; load(); }, { immediate: true });
</script>
