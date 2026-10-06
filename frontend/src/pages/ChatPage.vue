<template>
  <div class="chat-page">
    <div class="page-head chat-head">
      <div class="chat-head-line">
        <h5 class="page-title chat-head-title">LLM 交互</h5>
        <p class="page-subtitle chat-head-desc">围绕角色设定进行多轮对话，支持本地会话历史持久化。</p>
      </div>
      <span class="pill-tag">Conversation</span>
    </div>

    <div class="chat-shell">
      <div class="chat-topbar">
        <div class="topbar-left">
          <div class="chat-title-wrap">
            <h3 class="chat-title">对话窗口</h3>
          </div>
          <el-tag type="success" effect="light" class="model-tag">模型：{{ settingsStore.settings.model }}</el-tag>
        </div>
        <div class="topbar-actions">
          <div class="history-group">
            <span class="history-label">历史会话</span>
            <el-select
              v-model="activeSessionId"
              class="session-select"
              placeholder="选择会话"
              size="small"
              :disabled="pending"
            >
              <el-option
                v-for="session in sortedSessions"
                :key="session.id"
                :label="session.title"
                :value="session.id"
              />
            </el-select>
          </div>
          <el-button size="small" class="action-btn" plain :disabled="pending" @click="renameCurrentSession">重命名</el-button>
          <el-button size="small" class="action-btn" type="primary" plain :disabled="pending" @click="createNewSession">新建会话</el-button>
          <el-button size="small" class="action-btn" plain :disabled="pending" @click="clearConversation">清空当前</el-button>
        </div>
      </div>

      <div ref="messagesRef" class="chat-stream">
        <div class="stream-inner">
          <el-empty v-if="messages.length === 0 && !pending" description="开始提问吧，Enter 发送，Shift+Enter 换行" />

          <div v-for="(msg, idx) in messages" :key="`${msg.role}-${idx}`" :class="['msg-row', msg.role]">
            <div v-if="msg.role === 'assistant'" class="msg-avatar">AI</div>
            <el-avatar v-else class="msg-avatar" :src="roleAvatar">{{ userName.slice(0, 1) }}</el-avatar>
            <div class="msg-bubble">
              <MarkdownRender
                v-if="msg.role === 'assistant'"
                class="msg-content assistant-markdown"
                :content="msg.content"
                :typewriter="false"
              />
              <div v-else class="msg-content user-text">{{ msg.content }}</div>
            </div>
          </div>

          <div v-if="pending" class="msg-row assistant">
            <div class="msg-avatar">AI</div>
            <div class="msg-bubble thinking">
              <div class="msg-content">正在思考中...</div>
            </div>
          </div>
        </div>
      </div>

      <div class="composer-wrap">
        <div class="composer-card">
          <el-input
            v-model="input"
            type="textarea"
            :rows="2"
            resize="none"
            placeholder="给 AI 发送消息..."
            :disabled="pending"
            @keydown.enter="onEnter"
          />
          <div class="action-row">
            <el-text type="info" size="small">Shift + Enter 换行</el-text>
            <el-button type="primary" :loading="pending" :disabled="!input.trim()" @click="send">发送</el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api/client";
import { useSettingsStore } from "../stores/settings";
import { MarkdownRender } from "vue-renderer-markdown";
import "vue-renderer-markdown/index.css";

defineOptions({
  name: "ChatPage",
});

const CHAT_HISTORY_KEY = "novelweaver_chat_history";

const settingsStore = useSettingsStore();
const userName = computed(() => settingsStore.settings.user_name?.trim() || "用户");
const roleName = computed(() => settingsStore.settings.custom_role_name?.trim() || "助手");
const roleAvatar = computed(() => settingsStore.settings.custom_role_avatar || "");
const rolePrompt = computed(() => settingsStore.settings.custom_role_prompt?.trim() || "");

const input = ref("");
const sessions = ref(loadSessions());
const activeSessionId = ref(loadActiveSessionId(sessions.value));
const messages = ref(loadCurrentMessages(sessions.value, activeSessionId.value));
const pending = ref(false);
const messagesRef = ref(null);

const sortedSessions = computed(() =>
  [...sessions.value].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
);

watch(
  sessions,
  (next) => {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(next));
  },
  { deep: true },
);

watch(activeSessionId, (nextId) => {
  localStorage.setItem("novelweaver_chat_active_session", String(nextId || ""));
  messages.value = loadCurrentMessages(sessions.value, nextId);
  void scrollToBottom();
});

watch(
  messages,
  (next) => {
    updateActiveSession(next);
  },
  { deep: true },
);

function buildSessionTitle(text = "") {
  const trimmed = String(text || "").trim();
  if (!trimmed) return "新会话";
  return trimmed.length > 16 ? `${trimmed.slice(0, 16)}...` : trimmed;
}

function createSession() {
  const now = new Date().toISOString();
  return {
    id: `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    title: "新会话",
    messages: [],
    created_at: now,
    updated_at: now,
  };
}

function normalizeMessages(list) {
  if (!Array.isArray(list)) return [];
  return list.filter(
    (item) =>
      item &&
      (item.role === "user" || item.role === "assistant") &&
      typeof item.content === "string",
  );
}

function loadSessions() {
  try {
    const raw = localStorage.getItem(CHAT_HISTORY_KEY);
    if (!raw) {
      return [createSession()];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [createSession()];
    }

    // 兼容旧版单会话结构：[{ role, content }, ...]
    if (parsed.length > 0 && typeof parsed[0]?.role === "string") {
      const migratedMessages = normalizeMessages(parsed);
      const migrated = createSession();
      const firstUser = migratedMessages.find((item) => item.role === "user");
      migrated.title = firstUser ? buildSessionTitle(firstUser.content) : "历史会话";
      migrated.messages = migratedMessages;
      migrated.updated_at = new Date().toISOString();
      return [migrated];
    }

    const normalized = parsed
      .map((item) => ({
        id: String(item?.id || ""),
        title: String(item?.title || "新会话"),
        messages: normalizeMessages(item?.messages),
        created_at: String(item?.created_at || new Date().toISOString()),
        updated_at: String(item?.updated_at || new Date().toISOString()),
      }))
      .filter((item) => item.id);

    return normalized.length > 0 ? normalized : [createSession()];
  } catch {
    return [createSession()];
  }
}

function loadActiveSessionId(sessionList) {
  const saved = String(localStorage.getItem("novelweaver_chat_active_session") || "").trim();
  if (saved && sessionList.some((item) => item.id === saved)) {
    return saved;
  }
  return sessionList[0]?.id || createSession().id;
}

function loadCurrentMessages(sessionList, sessionId) {
  const target = sessionList.find((item) => item.id === sessionId);
  return target?.messages ? [...target.messages] : [];
}

function updateActiveSession(nextMessages) {
  const index = sessions.value.findIndex((item) => item.id === activeSessionId.value);
  if (index < 0) {
    return;
  }

  const previous = sessions.value[index];
  const firstUser = nextMessages.find((item) => item.role === "user" && String(item.content || "").trim());
  const title = previous.title === "新会话" && firstUser ? buildSessionTitle(firstUser.content) : previous.title;

  const updated = {
    ...previous,
    title,
    messages: [...nextMessages],
    updated_at: new Date().toISOString(),
  };

  sessions.value = [
    ...sessions.value.slice(0, index),
    updated,
    ...sessions.value.slice(index + 1),
  ];
}

function createNewSession() {
  const next = createSession();
  sessions.value = [next, ...sessions.value];
  activeSessionId.value = next.id;
  messages.value = [];
}

async function renameCurrentSession() {
  const current = sessions.value.find((item) => item.id === activeSessionId.value);
  if (!current) {
    ElMessage.warning("当前会话不存在");
    return;
  }

  try {
    const { value } = await ElMessageBox.prompt("请输入新的会话名称", "重命名会话", {
      confirmButtonText: "确定",
      cancelButtonText: "取消",
      inputValue: current.title || "新会话",
      inputPlaceholder: "例如：角色设定讨论",
      inputValidator: (text) => {
        if (!String(text || "").trim()) {
          return "会话名称不能为空";
        }
        if (String(text).trim().length > 30) {
          return "会话名称最多 30 个字符";
        }
        return true;
      },
    });

    const nextTitle = String(value || "").trim();
    if (!nextTitle) {
      return;
    }

    sessions.value = sessions.value.map((item) =>
      item.id === activeSessionId.value
        ? {
            ...item,
            title: nextTitle,
            updated_at: new Date().toISOString(),
          }
        : item,
    );

    ElMessage.success("会话已重命名");
  } catch {
    // 用户取消输入时不提示。
  }
}

function clearConversation() {
  messages.value = [];
}

function onEnter(event) {
  if (event.shiftKey) return;
  event.preventDefault();
  void send();
}

async function send() {
  const text = input.value.trim();
  if (!text || pending.value) return;

  const userMsg = { role: "user", content: text };
  const history = [...messages.value, userMsg];
  messages.value = history;
  input.value = "";
  pending.value = true;
  await scrollToBottom();

  try {
    const res = await api.chat(
      {
        message: text,
        history,
        model: settingsStore.settings.model,
        temperature: settingsStore.settings.temperature,
        top_p: settingsStore.settings.top_p,
        max_tokens: settingsStore.settings.max_tokens,
        context_length: settingsStore.settings.context_length,
        repetition_penalty: settingsStore.settings.repetition_penalty,
        chapter_limit: settingsStore.settings.chapter_limit,
        use_chapter_context: settingsStore.settings.use_chapter_context,
        system_prompt: rolePrompt.value || `你是${roleName.value}，请保持专业、友好、准确。`,
      },
      settingsStore.settings,
    );

    messages.value = [...messages.value, { role: "assistant", content: res.response }];
    await scrollToBottom();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "发送失败");
  } finally {
    pending.value = false;
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight;
  }
}
</script>

<style scoped>
.chat-page {
  height: calc(100% + 10px);
  min-height: 0;
  margin-bottom: -10px;
  --surface: #ffffff;
  --surface-soft: #f8fbff;
  --line: #dbe3ef;
  --text-muted: #64748b;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
}

.chat-head {
  flex: 0 0 auto;
}

.chat-head-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
}

.chat-head-title {
  margin: 0;
  flex: 0 0 auto;
}

.chat-head-desc {
  margin: 0;
  font-size: 14px;
  line-height: 1.2;
  color: #7b8794;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #f9fcff 0%, #eef4fb 100%);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.chat-topbar {
  padding: 6px 14px;
  border-bottom: 1px solid var(--line);
  background:
    radial-gradient(circle at 8% 0%, rgba(125, 211, 252, 0.18) 0%, transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.97) 0%, rgba(247, 251, 255, 0.98) 100%);
  backdrop-filter: blur(8px);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.chat-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-title-sub {
  margin: 0;
  font-size: 11px;
  color: #6b7f93;
  letter-spacing: 0.02em;
}

.model-tag {
  border-radius: 999px;
  font-weight: 600;
}

.history-group {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 8px;
  border-radius: 10px;
  border: 1px solid #d8e6f6;
  background: rgba(255, 255, 255, 0.82);
}

.history-label {
  font-size: 11px;
  font-weight: 600;
  color: #5b728a;
  white-space: nowrap;
}

.session-select {
  width: 240px;
}

.action-btn {
  min-width: 72px;
  border-radius: 10px;
}

@media (max-width: 900px) {
  .chat-topbar {
    gap: 10px;
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .topbar-left {
    width: 100%;
    justify-content: space-between;
  }

  .topbar-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .session-select {
    flex: 1;
    min-width: 180px;
  }

  .history-group {
    flex: 1;
  }
}

.role-avatar {
  border: 1px solid #c8d8ff;
}

.role-name {
  font-weight: 600;
  font-size: 12px;
}

.chat-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
}

.chat-stream {
  flex: 1;
  overflow-y: auto;
  padding: 0 14px;
  background:
    radial-gradient(circle at 8% 10%, rgba(59, 130, 246, 0.06) 0%, transparent 25%),
    radial-gradient(circle at 90% 85%, rgba(14, 165, 233, 0.08) 0%, transparent 30%),
    linear-gradient(180deg, #f9fcff 0%, #eef4fb 100%);
}

.stream-inner {
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
  padding: 22px 6px 26px;
}

.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-row.user .msg-avatar {
  order: 2;
}

.msg-row.user .msg-bubble {
  order: 1;
}

.msg-row.assistant {
  justify-content: flex-start;
}

.msg-avatar {
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: #334155;
  background: #e2e8f0;
  border: 1px solid #cbd5e1;
  box-shadow: 0 2px 8px rgba(30, 41, 59, 0.08);
}

.msg-row.user .msg-avatar {
  color: #1e3a8a;
  background: #dbeafe;
  border-color: #bfdbfe;
}

.msg-bubble {
  max-width: min(91%, 1180px);
  border-radius: 16px;
  padding: 13px 15px;
  border: 1px solid var(--line);
  background: var(--surface);
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
}

.msg-row.user .msg-bubble {
  background: #eaf1ff;
  border-color: #c8d8ff;
}

.msg-content {
  font-size: 13px;
  line-height: 1.65;
}

.assistant-markdown :deep(.markdown-renderer) {
  background: transparent;
  border: none;
  padding: 0;
}

.assistant-markdown :deep(pre) {
  border-radius: 10px;
}

.user-text {
  white-space: pre-wrap;
}

.thinking {
  color: var(--text-muted);
}

.composer-wrap {
  border-top: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.96);
  padding: 8px 12px 10px;
}

.composer-card {
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface-soft);
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06);
  padding: 6px 8px;
}

.composer-card :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  background: transparent;
  padding: 6px 8px;
  font-size: 13px;
  line-height: 1.45;
}

.composer-card :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

.action-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 2px;
  padding: 1px 4px 0 6px;
  font-size: 11px;
}

@media (max-width: 768px) {
  .chat-page {
    height: calc(100% + 10px);
  }

  .chat-stream,
  .composer-wrap {
    padding-left: 10px;
    padding-right: 10px;
  }

  .stream-inner {
    padding-left: 0;
    padding-right: 0;
  }

  .msg-bubble {
    max-width: 92%;
  }

  .chat-title {
    font-size: 13px;
  }
}
</style>
