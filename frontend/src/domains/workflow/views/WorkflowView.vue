<template>
  <header class="page-header page-header-compact dashboard-header"><div class="header-actions"><RouterLink to="/upload" class="button-primary"><el-icon><Upload /></el-icon>添加作品</RouterLink><el-button class="button-quiet" :icon="Refresh" :loading="loading" @click="refresh">刷新</el-button></div></header>
  <section class="metrics metrics-new"><div><span class="metric-label"><i class="metric-icon ink" />作品</span><strong>{{ workspace.books.length }}</strong><small>已加入工作区</small></div><div><span class="metric-label"><i class="metric-icon pages" />章节</span><strong>{{ workspace.books.reduce((sum, book) => sum + book.chapter_count, 0) }}</strong><small>已解析文本</small></div><div><span class="metric-label"><i class="metric-icon people" />角色卡</span><strong>{{ cards }}</strong><small>可直接对话</small></div><div><span class="metric-label"><i class="metric-icon pulse" />执行中</span><strong>{{ tasks.filter((task) => ['pending','running'].includes(task.status)).length }}</strong><small>后台工作流</small></div></section>
  <div class="dashboard-grid">
    <section class="section-band activity-panel">
      <div class="section-heading"><div><p class="eyebrow">WORKFLOW</p><h2>最近任务</h2></div><RouterLink to="/upload">查看作品库 <el-icon><ArrowRight /></el-icon></RouterLink></div>
      <el-table :data="tasks" empty-text="暂无任务，从作品库上传一本作品开始" :max-height="390">
        <el-table-column prop="book_title" label="作品" min-width="170" show-overflow-tooltip />
        <el-table-column label="类型" width="90"><template #default="{ row }"><span class="table-type">{{ row.task_type === 'parse' ? '文本解析' : '资料提取' }}</span></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="进度" min-width="160"><template #default="{ row }"><el-progress :percentage="row.progress" :status="row.status === 'failed' ? 'exception' : row.status === 'completed_with_warnings' ? 'warning' : undefined" /></template></el-table-column>
        <el-table-column prop="current_step" label="当前步骤" min-width="210" show-overflow-tooltip />
        <el-table-column label="详情" width="64" fixed="right"><template #default="{ row }"><el-tooltip content="查看任务"><el-button :icon="Tickets" circle aria-label="查看任务" @click="taskId = row.id; showTask = true" /></el-tooltip></template></el-table-column>
      </el-table>
    </section>
    <aside class="quick-panel"><p class="eyebrow">QUICK START</p><h2>从哪里开始？</h2><p class="muted">把原始文本变成可检索、可对话的角色与世界资料。</p><RouterLink to="/upload" class="quick-item"><span class="quick-number">01</span><span><strong>导入一部作品</strong><small>支持 TXT、Markdown、EPUB、PDF、DOCX</small></span><el-icon><ArrowRight /></el-icon></RouterLink><RouterLink to="/summary" class="quick-item"><span class="quick-number">02</span><span><strong>查看提取资料</strong><small>浏览角色、剧情、物品和地点</small></span><el-icon><ArrowRight /></el-icon></RouterLink><RouterLink to="/chat" class="quick-item"><span class="quick-number">03</span><span><strong>开始角色对话</strong><small>用角色卡保持设定一致</small></span><el-icon><ArrowRight /></el-icon></RouterLink></aside>
  </div>
  <section class="section-band log-panel"><div class="section-heading"><div><p class="eyebrow">ACTIVITY</p><h2>执行日志</h2></div></div><el-empty v-if="!logs.length" description="暂无日志" :image-size="60" /><div v-for="log in logs.slice(0, 6)" :key="log.id" class="log-row"><time>{{ dateText(log.created_at) }}</time><span class="log-dot" :class="log.level" /><span>{{ log.message }}</span></div></section>
  <TaskDetail v-model="showTask" :task-id="taskId" @changed="refresh" />
</template>
<script setup>
import { ref } from "vue";
import { RouterLink } from "vue-router";
import { Refresh, Upload, ArrowRight, Tickets } from "@element-plus/icons-vue";
import TaskDetail from "../components/TaskDetail.vue";
import { api } from "../../../api/client";
import { useWorkspaceStore } from "../../../stores/workspace";
import { usePolling, statusText, statusType, dateText } from "../../../lib/ui";
const workspace = useWorkspaceStore();
const tasks = ref([]), logs = ref([]), cards = ref(0), loading = ref(false);
const showTask = ref(false), taskId = ref("");
const refresh = usePolling(async () => {
  loading.value = true;
  try {
    await workspace.refresh();
    const [taskResult, logResult, cardResult] = await Promise.all([api.get("/tasks"), api.get("/task-logs"), api.get("/cards")]);
    tasks.value = taskResult.tasks; logs.value = logResult.logs; cards.value = cardResult.cards.length;
  } finally { loading.value = false; }
}, 5000);
</script>
