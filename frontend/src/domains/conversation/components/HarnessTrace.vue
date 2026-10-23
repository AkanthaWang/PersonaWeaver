<template>
  <el-button text :icon="List" :disabled="!requestId" @click="open">执行记录</el-button>
  <el-drawer v-model="visible" title="本轮执行记录" size="min(100vw, 520px)" append-to-body>
    <div class="trace-summary">
      <el-tag effect="plain">{{ run?.tool_mode === 'native' ? '原生工具调用' : 'JSON 工具兼容' }}</el-tag>
      <el-tag v-if="run?.validation?.passed" type="success">一致性校验通过</el-tag>
      <el-tag v-else-if="run?.phase === 'blocked'" type="danger">未通过，未发布</el-tag>
    </div>
    <el-empty v-if="!events.length" description="暂无执行记录" />
    <ol class="trace-events">
      <li v-for="(entry, index) in events" :key="entry.seq || index">
        <strong>{{ eventLabel(entry) }}</strong>
        <small v-if="entry.created_at">{{ new Date(entry.created_at).toLocaleTimeString('zh-CN') }}</small>
        <template v-if="entry.event === 'tool'">
          <p v-if="entry.payload.arguments?.query">{{ entry.payload.arguments.query }}</p>
          <p v-if="entry.payload.arguments?.missing_question">{{ entry.payload.arguments.missing_question }}</p>
          <p v-if="entry.payload.error" class="trace-error">{{ entry.payload.error }}</p>
          <small v-else>{{ entry.payload.source_ids?.length || 0 }} 条资料{{ entry.payload.cached ? ' · 复用结果' : '' }}</small>
        </template>
        <template v-if="entry.event === 'validation'">
          <p v-for="(conflict, i) in entry.payload.conflicts || []" :key="i" class="trace-error">{{ conflict.reason }}</p>
        </template>
      </li>
    </ol>
    <div v-if="run?.usage" class="trace-usage">
      <strong>各阶段用量</strong>
      <p v-for="(usage, name) in run.usage" :key="name">{{ name }} · {{ usageLabel(usage.actual) || `输入估算 ${usage.estimated_input || 0} tokens` }}</p>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { List } from "@element-plus/icons-vue";
import { api } from "../../../api/client";
import { report } from "../../../lib/ui";
import { phaseLabel, usageLabel } from "../stream.js";
const props = defineProps({ conversationId: String, requestId: String, liveEvents: { type: Array, default: () => [] }, run: Object });
const visible = ref(false), events = ref([]);
const savedRun = ref(null), run = computed(() => savedRun.value || props.run);
const tools = { search_knowledge: "查询提取资料", search_original: "搜索原文", read_original: "读取原文" };
function eventLabel(entry) {
  if (entry.event === "phase") return phaseLabel(entry.payload.phase);
  if (entry.event === "tool") return tools[entry.payload.name] || entry.payload.name;
  return entry.payload.passed ? "一致性校验通过" : "发现设定冲突";
}
async function open() {
  visible.value = true;
  const id = props.conversationId, rid = props.requestId;
  events.value = [...props.liveEvents];
  try {
    const [result, status] = await Promise.all([
      api.get(`/conversations/${id}/generations/${rid}/trace`),
      api.get(`/conversations/${id}/generations/${rid}`),
    ]);
    if (id === props.conversationId && rid === props.requestId) {
      events.value = result.events; savedRun.value = status;
    }
  } catch (err) { report(err); }
}
watch(() => props.liveEvents.length, () => { if (visible.value) events.value = [...props.liveEvents]; });
watch(() => props.run, () => { savedRun.value = null; });
watch(() => props.conversationId, () => { visible.value = false; events.value = []; });
</script>

<style scoped>
.trace-summary { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
.trace-events { list-style: none; padding: 0; margin: 0; }
.trace-events li { padding: 12px 0 12px 16px; border-left: 2px solid var(--pw-border); border-bottom: 1px solid var(--pw-border); overflow-wrap: anywhere; }
.trace-events strong, .trace-usage strong { font-size: 13px; }
.trace-events small { display: block; margin: 5px 0; color: var(--el-text-color-secondary); }
.trace-events p, .trace-usage p { font-size: 12px; line-height: 1.6; white-space: pre-wrap; }
.trace-error { color: var(--el-color-danger); }
.trace-usage { margin-top: 20px; overflow-wrap: anywhere; }
</style>
