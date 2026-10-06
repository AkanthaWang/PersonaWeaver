import { defineStore } from "pinia";
import { ref, computed } from "vue";

const CHAT_SESSIONS_KEY = "novelweaver_chat_sessions";
const CURRENT_SESSION_KEY = "novelweaver_current_session_id";

// 初始化会话数据
function loadSessions() {
  try {
    const raw = localStorage.getItem(CHAT_SESSIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function getCurrentSessionId() {
  try {
    return localStorage.getItem(CURRENT_SESSION_KEY) || null;
  } catch {
    return null;
  }
}

export const useChatStore = defineStore("chat", () => {
  const sessions = ref(loadSessions());
  const currentSessionId = ref(getCurrentSessionId());

  // 创建新会话
  function createSession(name = null) {
    const now = new Date().toISOString();
    const sessionId = `chat_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

    const newSession = {
      id: sessionId,
      name: name || `会话 ${sessions.value.length + 1}`,
      messages: [],
      created_at: now,
      updated_at: now,
    };

    sessions.value.unshift(newSession);
    currentSessionId.value = sessionId;
    persistSessions();
    persistCurrentSessionId();

    return newSession;
  }

  // 获取当前会话
  const currentSession = computed(() => {
    if (!currentSessionId.value) return null;
    return sessions.value.find((s) => s.id === currentSessionId.value) || null;
  });

  // 切换会话
  function switchSession(sessionId) {
    const session = sessions.value.find((s) => s.id === sessionId);
    if (!session) return false;

    currentSessionId.value = sessionId;
    persistCurrentSessionId();
    return true;
  }

  // 更新当前会话的消息
  function updateCurrentMessages(messages) {
    if (!currentSession.value) return;
    currentSession.value.messages = messages;
    currentSession.value.updated_at = new Date().toISOString();
    persistSessions();
  }

  // 重命名会话
  function renameSession(sessionId, newName) {
    const session = sessions.value.find((s) => s.id === sessionId);
    if (!session) return false;

    session.name = newName;
    session.updated_at = new Date().toISOString();
    persistSessions();
    return true;
  }

  // 删除会话
  function deleteSession(sessionId) {
    const index = sessions.value.findIndex((s) => s.id === sessionId);
    if (index === -1) return false;

    sessions.value.splice(index, 1);

    // 如果删除的是当前会话，切换到其他会话
    if (currentSessionId.value === sessionId) {
      if (sessions.value.length > 0) {
        currentSessionId.value = sessions.value[0].id;
      } else {
        currentSessionId.value = null;
        // 如果没有会话了，创建一个新会话
        createSession();
      }
    }

    persistSessions();
    persistCurrentSessionId();
    return true;
  }

  // 清空当前会话的消息
  function clearCurrentMessages() {
    if (!currentSession.value) return;
    currentSession.value.messages = [];
    currentSession.value.updated_at = new Date().toISOString();
    persistSessions();
  }

  // 保存到本地存储
  function persistSessions() {
    localStorage.setItem(CHAT_SESSIONS_KEY, JSON.stringify(sessions.value));
  }

  function persistCurrentSessionId() {
    if (currentSessionId.value) {
      localStorage.setItem(CURRENT_SESSION_KEY, currentSessionId.value);
    } else {
      localStorage.removeItem(CURRENT_SESSION_KEY);
    }
  }

  // 初始化：如果没有会话，创建一个
  function initializeSessions() {
    if (sessions.value.length === 0) {
      createSession("默认会话");
    } else if (!currentSessionId.value) {
      currentSessionId.value = sessions.value[0].id;
      persistCurrentSessionId();
    }
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    createSession,
    switchSession,
    updateCurrentMessages,
    renameSession,
    deleteSession,
    clearCurrentMessages,
    initializeSessions,
  };
});
