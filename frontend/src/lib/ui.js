import { onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
export const report = (error) => ElMessage.error(error.message || "操作失败");
export const statusText = (status) => ({
  ready: "待解析", parsed: "已解析", processing: "处理中", pending: "排队中",
  running: "执行中", completed: "已完成", completed_with_warnings: "已完成（有警告）", failed: "失败", cancelled: "已取消",
}[status] || status);
export const statusType = (status) => ({
  completed: "success", completed_with_warnings: "warning", parsed: "success", failed: "danger", pending: "warning", running: "warning", processing: "warning",
}[status] || "info");
export const dateText = (value) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-";
export async function confirmDelete(message) {
  try {
    await ElMessageBox.confirm(message, "确认删除", { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" });
    return true;
  } catch { return false; }
}
export function usePolling(callback, delay = 4000) {
  let timer;
  let running = false;
  let active = true;
  const refresh = async () => {
    if (running || !active) return;
    running = true;
    try { await callback(); } catch (error) { if (active) report(error); }
    finally { running = false; }
  };
  onMounted(() => { refresh(); timer = setInterval(refresh, delay); });
  onUnmounted(() => { active = false; clearInterval(timer); });
  return refresh;
}
