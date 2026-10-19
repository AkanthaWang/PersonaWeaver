<template>
  <el-drawer :model-value="modelValue" title="提取任务" size="min(100vw, 780px)" append-to-body @close="$emit('update:modelValue', false)">
    <section v-if="task" v-loading="loading" class="task-detail">
      <div class="task-heading"><el-tag :type="statusType(task.status)">{{ statusText(task.status) }}</el-tag><span>{{ stages[task.stage] || task.stage }}</span><span>复用 {{ task.reused_units || 0 }} 项</span></div>
      <el-progress :percentage="task.progress" :status="task.status === 'failed' ? 'exception' : task.status === 'completed_with_warnings' ? 'warning' : undefined" />
      <p>{{ task.current_step }}</p>
      <p v-if="task.error_message" class="error-text">{{ task.error_message }}</p>
      <div class="task-heading">
        <el-button v-if="active && task.task_type === 'extract'" :icon="Close" :disabled="Boolean(task.cancel_requested) || acting" @click="act('cancel')">{{ task.cancel_requested ? '正在取消' : '取消任务' }}</el-button>
        <el-button v-if="['failed','cancelled','completed_with_warnings'].includes(task.status) && task.task_type === 'extract'" :icon="RefreshRight" :loading="acting" @click="act('retry')">续跑</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load" aria-label="刷新任务" />
      </div>
      <h3>处理明细</h3>
      <el-table :data="units" max-height="480" empty-text="暂无检查点">
        <el-table-column label="阶段" width="90"><template #default="{ row }">{{ stages[row.kind] || row.kind }}</template></el-table-column>
        <el-table-column prop="unit_key" label="分段" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100"><template #default="{ row }">{{ unitStates[row.status] || statusText(row.status) }}</template></el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="160" show-overflow-tooltip />
      </el-table>
    </section>
  </el-drawer>
</template>
<script setup>
import { computed, ref, watch } from "vue";
import { Close, Refresh, RefreshRight } from "@element-plus/icons-vue";
import { api } from "../../../api/client";
import { report, statusText, statusType, usePolling } from "../../../lib/ui";
const props = defineProps({ modelValue: Boolean, taskId: String });
const emit = defineEmits(["update:modelValue", "changed"]);
const task = ref(null), units = ref([]), loading = ref(false), acting = ref(false), currentId = ref("");
const stages = { extract: "章节提取", lookup: "受控补查", merge: "事实归并", synthesis: "人物综合", publish: "资料发布", completed: "已完成" };
const unitStates = { reused: "已复用", skipped: "已跳过", cancelled: "已取消" };
const active = computed(() => ["pending", "running"].includes(task.value?.status));
let generation = 0;
async function load() {
  if (!props.modelValue || !currentId.value) return;
  const current = ++generation;
  loading.value = true;
  try {
    const [result, detail] = await Promise.all([api.get(`/tasks/${currentId.value}`), api.get(`/tasks/${currentId.value}/units`)]);
    if (current !== generation) return;
    if (task.value && task.value.status !== result.status) emit("changed");
    task.value = result; units.value = detail.units;
  } catch (error) { if (current === generation) report(error); }
  finally { if (current === generation) loading.value = false; }
}
async function act(action) {
  acting.value = true;
  try {
    const result = await api.post(`/tasks/${currentId.value}/${action}`);
    if (action === "retry") { currentId.value = result.task_id; task.value = null; }
    await load(); emit("changed");
  } catch (error) { report(error); }
  finally { acting.value = false; }
}
watch(() => [props.modelValue, props.taskId], () => {
  generation++; currentId.value = props.taskId; task.value = null; units.value = []; load();
}, { immediate: true });
usePolling(() => { if (active.value) return load(); }, 2000);
</script>
<style scoped>
.task-detail { min-width: 0; overflow-wrap: anywhere; }
.task-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 12px 0; }
h3 { font-size: 16px; margin: 24px 0 12px; }
</style>
