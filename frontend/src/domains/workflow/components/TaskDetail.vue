<template>
  <el-drawer :model-value="modelValue" title="提取任务" size="min(100vw, 780px)" append-to-body @close="$emit('update:modelValue', false)">
    <section v-if="task" v-loading="loading" class="task-detail">
      <div class="task-heading"><el-tag :type="statusType(task.status)">{{ statusText(task.status) }}</el-tag><span>{{ stages[task.stage] || task.stage }}</span><span>复用 {{ task.reused_units || 0 }} 项</span></div>
      <el-progress :percentage="task.progress" :status="task.status === 'failed' ? 'exception' : task.status === 'completed_with_warnings' ? 'warning' : undefined" />
      <p>{{ task.current_step }}</p>
      <p v-if="task.error_message" class="error-text">{{ task.error_message }}</p>
      <div class="task-stats" aria-label="动作统计"><span>完成 <strong>{{ counts.completed }}</strong></span><span>复用 <strong>{{ counts.reused }}</strong></span><span>执行中 <strong>{{ counts.pending }}</strong></span><span>异常 <strong>{{ counts.issues }}</strong></span></div>
      <div class="task-heading">
        <el-button v-if="active && task.task_type === 'extract'" :icon="Close" :disabled="Boolean(task.cancel_requested) || acting" @click="act('cancel')">{{ task.cancel_requested ? '正在取消' : '取消任务' }}</el-button>
        <el-button v-if="['failed','cancelled','completed_with_warnings'].includes(task.status) && task.task_type === 'extract'" :icon="RefreshRight" :loading="acting" @click="act('retry')">续跑</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="load" aria-label="刷新任务" />
      </div>
      <div class="task-heading"><h3>处理明细</h3><el-checkbox v-model="issuesOnly">仅异常动作</el-checkbox></div>
      <el-table :data="visibleUnits" max-height="480" :empty-text="issuesOnly ? '暂无异常动作' : '暂无检查点'">
        <el-table-column label="阶段" width="90"><template #default="{ row }">{{ stages[row.kind] || row.kind }}</template></el-table-column>
        <el-table-column label="章节 / 分段" min-width="180" show-overflow-tooltip><template #default="{ row }"><strong>{{ row.chapter_title || (row.kind === 'synthesis' ? '资料综合' : '恢复决策') }}</strong><div class="muted">{{ unitLabel(row) }}</div></template></el-table-column>
        <el-table-column prop="fact_count" label="事实" width="65" />
        <el-table-column label="状态" width="90" fixed="right"><template #default="{ row }">{{ unitStates[row.status] || statusText(row.status) }}</template></el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="160" show-overflow-tooltip />
      </el-table>
      <el-button v-if="['completed','completed_with_warnings'].includes(task.status) && task.task_type === 'extract'" class="result-link" type="primary" :icon="Collection" @click="openResults">查看提取资料</el-button>
    </section>
  </el-drawer>
</template>
<script setup>
import { computed, ref, watch } from "vue";
import { Close, Collection, Refresh, RefreshRight } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import { useWorkspaceStore } from "../../../stores/workspace";
import { api } from "../../../api/client";
import { report, statusText, statusType, usePolling } from "../../../lib/ui";
const props = defineProps({ modelValue: Boolean, taskId: String });
const emit = defineEmits(["update:modelValue", "changed"]);
const router = useRouter(), workspace = useWorkspaceStore(), issuesOnly = ref(false);
const task = ref(null), units = ref([]), loading = ref(false), acting = ref(false), currentId = ref("");
const stages = { extract: "章节提取", lookup: "受控补查", agent: "恢复决策", merge: "事实归并", synthesis: "资料综合", publish: "资料发布", completed: "已完成" };
const unitStates = { reused: "已复用", skipped: "已跳过", cancelled: "已取消" };
const active = computed(() => ["pending", "running"].includes(task.value?.status));
const isIssue = (unit) => ["failed", "skipped", "cancelled"].includes(unit.status);
const visibleUnits = computed(() => issuesOnly.value ? units.value.filter(isIssue) : units.value);
const counts = computed(() => ({
  completed: units.value.filter((unit) => unit.status === "completed").length,
  reused: units.value.filter((unit) => unit.status === "reused").length,
  pending: units.value.filter((unit) => ["running", "pending"].includes(unit.status)).length,
  issues: units.value.filter(isIssue).length,
}));
function unitLabel(unit) {
  const key = unit.unit_key.replace(/(?::retry)+$/, "");
  if (unit.kind === "agent") return { retry: "重新执行", split: "拆分后重试", skip: "跳过当前动作" }[unit.recovery_tool] || "评估恢复方案";
  if (unit.kind === "synthesis") {
    const batch = key.match(/:(\d+)$/);
    return key.endsWith(":overview") ? "整合分批档案" : batch ? `第 ${Number(batch[1]) + 1} 批综合` : "生成综合档案";
  }
  const match = key.match(/:(\d+):(\d+)$/);
  if (match && unit.kind === "extract") return `字符 ${Number(match[1]) + 1}–${match[2]}`;
  if (unit.kind === "lookup") return `第 ${Number(key.split(":").at(-1)) + 1} 轮补查`;
  return stages[unit.kind] || unit.kind;
}
function openResults() { workspace.selectedId = task.value.book_id; emit("update:modelValue", false); router.push("/summary"); }
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
  generation++; currentId.value = props.taskId; task.value = null; units.value = []; issuesOnly.value = false; load();
}, { immediate: true });
usePolling(() => { if (active.value) return load(); }, 2000);
</script>
<style scoped>
.task-detail { min-width: 0; overflow-wrap: anywhere; }
.task-heading { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 12px 0; }
h3 { font-size: 16px; margin: 24px 0 12px; }
.task-stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border-block: 1px solid var(--pw-border); padding: 14px 0; gap: 8px; font-size: 13px; color: var(--pw-ink-soft); }
.task-stats strong { display: block; font-size: 20px; color: var(--pw-ink); margin-top: 4px; }
.task-heading h3 { margin: 8px auto 8px 0; }
.result-link { margin-top: 16px; }
</style>
