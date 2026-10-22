<template>
  <div class="conversation-page">
  <div class="chat-layout pi-chat-layout">
    <aside class="conversation-sidebar">
      <div class="conversation-sidebar-header"><div class="sidebar-section-title"><span>会话</span><span class="sidebar-count">{{ conversations.length }}</span></div><el-button type="primary" plain :icon="Plus" :disabled="sending" @click="showCreate = true">新对话</el-button></div>
      <el-input v-model="conversationFilter" class="conversation-search" clearable placeholder="搜索会话" :prefix-icon="Search" />
      <div class="conversation-list"><el-empty v-if="!filteredConversations.length" description="暂无会话" :image-size="44" />
        <div v-for="item in filteredConversations" :key="item.id" class="conversation-row" :class="{ active: selected?.id === item.id }"><button class="conversation-title" :title="item.title" :disabled="sending" @click="select(item.id)"><span class="conversation-row-icon"><ChatLineRound /></span><span class="conversation-row-copy"><strong>{{ item.title }}</strong><small>{{ formatDate(item.updated_at) }}</small></span></button><el-dropdown trigger="click" @command="(command) => command === 'rename' ? rename(item) : remove(item)"><el-button text :icon="MoreFilled" :disabled="sending" aria-label="会话操作" /><template #dropdown><el-dropdown-menu><el-dropdown-item command="rename">重命名</el-dropdown-item><el-dropdown-item command="delete" divided>删除</el-dropdown-item></el-dropdown-menu></template></el-dropdown></div>
      </div>
    </aside>
    <section class="chat-main" v-loading="loading">
      <div class="chat-heading pi-chat-heading">
        <div class="chat-heading-copy">
          <div class="chat-title-line">
            <img v-if="selectedCard" class="card-mark card-mark-image" :src="characterAvatarUrl(selectedCard.name)" :alt="`${selectedCard.name}头像`" />
            <h2>{{ selected?.title || '选择一个会话' }}</h2>
            <el-tag v-if="selected?.card_id" size="small" effect="plain" type="warning">{{ selectedCard?.name || '角色卡' }}</el-tag>
          </div>
          <p v-if="selected" class="muted heading-meta">{{ messages.length ? `${messages.length} 条消息` : '新对话' }}<span v-if="activeChildCount"> · 当前节点有 {{ activeChildCount }} 个分支</span><span v-if="selected.tokens"> · 上下文 {{ selected.tokens.toLocaleString() }} tokens</span></p>
        </div>
        <div v-if="selected" class="chat-heading-actions">
          <ConversationResources ref="resources" :conversation="selected" :disabled="sending || uncertain" :sources="sources" @updated="resourcesUpdated" />
          <el-button v-if="selectedCard" text class="heading-link" :icon="InfoFilled" @click="showCard = true">角色设定</el-button>
          <el-dropdown v-if="tree.length" trigger="click" class="branch-dropdown" :disabled="sending || uncertain" @command="selectBranch">
            <el-button text class="branch-trigger" :disabled="sending || uncertain"><span class="branch-trigger-dot" />{{ activeNodeId ? '当前分支' : '新分支起点' }}<small>{{ tree.length }} 节点</small><ArrowDown /></el-button>
            <template #dropdown>
              <div class="branch-options"><el-checkbox v-model="carrySummary">切换时携带被放弃分支摘要</el-checkbox></div>
              <el-dropdown-menu><el-dropdown-item command="__root__">新分支起点</el-dropdown-item><el-dropdown-item v-for="node in visibleTree" :key="node.id" :command="node.id" :class="{ 'branch-path-item': activePath.has(node.id) }">{{ '　'.repeat(node.depth) }}{{ nodeKind(node) }} · {{ nodeText(node) }}</el-dropdown-item></el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
      <section ref="timeline" class="messages pi-messages timeline">
        <div v-if="!selected" class="chat-empty"><div class="chat-empty-mark"><ChatDotRound /></div><h3>开始一段角色对话</h3><p>选择左侧会话，或创建一个新的角色场景。</p><el-button type="primary" :icon="Plus" @click="showCreate = true">创建会话</el-button></div>
        <template v-else>
          <div v-if="selectedCard && !messages.length && !sending" class="card-intro"><img class="card-mark card-mark-image" :src="characterAvatarUrl(selectedCard.name)" :alt="`${selectedCard.name}头像`" /><div><strong>{{ selectedCard.name }}</strong><p>{{ selectedCard.intro || '还没有设定简介，点击「角色设定」查看或补充。' }}</p><small>在下方写下第一句话，开始这段对话。</small></div></div>
          <el-empty v-else-if="!messages.length && !sending && !timelineEntries.length" description="等待模型回复" :image-size="70" />
          <template v-for="entry in timelineEntries" :key="entry.key">
            <div v-if="entry.kind === 'marker'" class="context-marker" :class="entry.type"><el-icon><Collection /></el-icon><span>{{ entry.type === 'compaction' ? '上下文已压缩' : '分支摘要' }}</span><em v-if="entry.tokens_before">压缩前 {{ entry.tokens_before.toLocaleString() }} tokens</em><small v-if="entry.label">{{ entry.label }}</small><p v-if="entry.summary">{{ entry.summary }}</p></div>
            <article v-else class="message" :class="[entry.message.role, { active: entry.message.id === activeNodeId, pending: entry.pending }]">
              <div class="message-avatar"><img v-if="entry.message.role === 'user' && auth.user?.avatar" :src="auth.user.avatar" alt="个人头像" /><el-icon v-else-if="entry.message.role === 'user'"><User /></el-icon><img v-else-if="selectedCard" class="message-character-avatar" :src="characterAvatarUrl(selectedCard.name)" :alt="`${selectedCard.name}头像`" /><el-icon v-else><ChatDotRound /></el-icon></div>
              <div class="message-content">
                <div class="message-meta"><small>{{ entry.message.role === 'user' ? (auth.user?.username || '我') : (selectedCard?.name || '角色助手') }}</small><el-tag v-if="entry.message.label" size="small" effect="plain" type="success">{{ entry.message.label }}</el-tag><time v-if="entry.message.created_at">{{ formatTime(entry.message.created_at) }}</time></div>
                <div class="message-markdown">
                  <MarkdownRender
                    mode="chat"
                    :content="entry.message.content || ''"
                    :final="!entry.pending"
                    html-policy="escape"
                    smooth-streaming="auto"
                    :fade="false"
                    :render-code-blocks-as-pre="true"
                  />
                </div>
                <el-tag v-if="['cancelled', 'interrupted', 'failed'].includes(entry.message.metadata?.status)" size="small" type="warning" effect="plain">已中断 · 已保存文本，可继续对话</el-tag>
                <el-button v-if="entry.message.metadata?.sources?.length" text size="small" :icon="Collection" @click="resources.openSources(entry.message.metadata.sources)">参考来源</el-button>
                <div v-if="entry.message.id && !entry.pending" class="message-actions"><el-tooltip content="复制内容" placement="top"><el-button text size="small" :icon="DocumentCopy" @click="copyMessage(entry.message)" /></el-tooltip><el-tooltip content="从此处继续（新建分支）" placement="top"><el-button text size="small" :icon="Share" :disabled="sending" @click="selectNode(entry.message.id)" /></el-tooltip><el-tooltip content="标记该节点" placement="top"><el-button text size="small" :icon="PriceTag" :disabled="sending" @click="labelNode(entry.message)" /></el-tooltip></div>
              </div>
            </article>
          </template>
          <div v-if="sending" class="typing-indicator"><span /><span /><span />{{ nativeStreaming === false ? '此协议返回整段回复，等待模型完成' : '正在生成回复' }}</div>
        </template>
      </section>
      <div v-if="selected" class="generation-controls">
        <el-button v-if="sending" type="danger" plain :icon="VideoPause" :loading="stopping" @click="stop">停止生成</el-button>
        <el-button v-else-if="lastAttempt && error" plain :icon="Refresh" @click="retry">{{ uncertain ? '重连本次请求（不重复生成）' : '重新生成（新请求）' }}</el-button>
        <small v-if="budgetUsage" class="muted">输入估算 {{ budgetUsage.input_tokens.toLocaleString() }} / {{ budgetUsage.available_input.toLocaleString() }} · 预留输出 {{ budgetUsage.max_output.toLocaleString() }}</small>
        <small v-if="actualUsage" class="muted" :title="JSON.stringify(actualUsage)">提供商实际：{{ usageLabel(actualUsage) }}</small>
      </div>
      <form class="composer pi-composer" @submit.prevent="send"><div v-if="error" class="composer-error" role="alert" aria-live="polite"><el-icon><WarningFilled /></el-icon><span>{{ error }}</span></div><div class="composer-box"><el-input v-model="draft" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" resize="none" maxlength="12000" :disabled="!selected || sending" :placeholder="composerPlaceholder" aria-label="消息" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" /><div class="composer-toolbar"><span class="composer-toolbar-status" :class="{ 'is-ready': canSend }">{{ sending ? '正在生成回复…' : canSend ? '准备发送' : selected ? '输入消息后发送' : '先选择一个会话' }}</span><el-button type="primary" :icon="Promotion" native-type="submit" :disabled="!canSend" :loading="sending" :aria-label="sending ? '正在发送消息' : '发送消息'">发送</el-button></div></div><div class="composer-footer"><el-dropdown trigger="click" popper-class="model-popover" class="model-menu" :disabled="!selected || sending" @command="changeModel"><button type="button" class="model-menu-trigger" :class="{ 'is-loading': profilesLoading }" :disabled="!selected || sending || profilesLoading" :title="activeModelLabel"><span class="model-menu-glyph" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.6 20.1 7v10L12 21.4 3.9 17V7z" /><circle cx="12" cy="12" r="2.6" /><path d="M12 9.4V6.2M12 17.8v-3.2M14.3 13.3l2.7 1.6M7 9.1l2.7 1.6" /></svg></span><span class="model-menu-copy"><span class="model-menu-name">{{ modelMenuName }}</span><small v-if="activeModel">{{ activeModel.model }}</small></span><ArrowDown class="model-menu-caret"  /></button><template #dropdown><div class="model-popover-head"><strong>切换模型</strong><small>切换后会绑定到当前会话</small></div><el-dropdown-menu class="model-menu-list"><el-dropdown-item v-for="profile in profiles" :key="profile.id" :command="profile.id" :class="{ 'model-menu-active': profile.id === selectedProfileId }"><span class="model-menu-glyph" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.6 20.1 7v10L12 21.4 3.9 17V7z" /><circle cx="12" cy="12" r="2.6" /></svg></span><span class="model-menu-option"><span class="model-menu-option-name">{{ profile.name || profile.model }}</span><small>{{ profile.model }}</small></span><el-icon v-if="profile.id === selectedProfileId" class="model-menu-check"><Check /></el-icon></el-dropdown-item><el-dropdown-item v-if="!profiles.length" disabled>暂无可用模型</el-dropdown-item></el-dropdown-menu><div class="model-popover-foot"><button type="button" class="model-popover-action" @click="goSettings">模型设置</button><button type="button" class="model-popover-action" disabled title="待开放">上下文长度</button></div></template></el-dropdown><div v-if="selected" class="context-meter" :class="contextLevel" :title="`已使用 ${estimateTokens.toLocaleString()} tokens`"><span class="context-meter-track" aria-hidden="true"><span class="context-meter-fill" :style="{ width: `${contextPercent}%` }" /></span><span class="context-meter-value">{{ estimateTokens.toLocaleString() }} tokens</span></div><span v-else class="context-meter-empty">选择会话后开始</span><div class="composer-footer-right"><span class="composer-hint">Ctrl / ⌘ + Enter 发送</span><span class="composer-count" :class="draftCountClass">{{ draft.length.toLocaleString() }} / 12,000</span></div></div></form>
    </section>
  </div>
  <el-dialog v-model="showCreate" title="新建角色会话" width="480px" class="conversation-dialog"><el-form label-position="top" @submit.prevent="create"><el-form-item label="会话标题"><el-input v-model="newTitle" maxlength="100" placeholder="例如：雨夜里的重逢" /></el-form-item><el-form-item label="角色卡"><el-select v-model="newCard" clearable filterable class="full-width" placeholder="选择一个角色（可选）"><el-option v-for="card in cards" :key="card.id" :label="`${card.name} · ${card.book_title}`" :value="card.id" /></el-select></el-form-item><el-form-item label="使用模型"><el-select v-model="newProfile" filterable class="full-width" placeholder="选择模型"><el-option v-for="profile in profiles" :key="profile.id" :label="profileLabel(profile)" :value="profile.id" /></el-select><small class="form-help">模型可以在对话中随时切换，切换后会绑定到当前会话。</small></el-form-item><div class="dialog-actions"><el-button @click="showCreate = false">取消</el-button><el-button type="primary" :icon="Plus" native-type="submit" :loading="creating">创建会话</el-button></div></el-form></el-dialog>
  <el-drawer v-model="showCard" :title="selectedCard?.name || '角色设定'" size="420px" class="card-drawer"><template v-if="selectedCard"><p class="card-drawer-intro">{{ selectedCard.intro || '暂无简介' }}</p><dl class="card-drawer-meta"><dt>所属作品</dt><dd>{{ selectedCard.book_title || '未关联' }}</dd></dl><div class="card-drawer-body"><pre class="document-text">{{ selectedCard.content || '该角色卡还没有详细设定。' }}</pre></div><div class="card-drawer-actions"><RouterLink to="/characters"><el-button plain :icon="EditPen">前往角色库编辑</el-button></RouterLink></div></template></el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ChatDotRound, ChatLineRound, Check, Collection, DocumentCopy, EditPen, InfoFilled, MoreFilled, Plus, PriceTag, Promotion, Refresh, Search, Share, User, VideoPause, WarningFilled } from "@element-plus/icons-vue";
import MarkdownRender from "markstream-vue";
import "markstream-vue/index.css";
import { api } from "../../../api/client";
import { useAuthStore } from "../../../stores/auth";
import { report, confirmDelete } from "../../../lib/ui";
import { characterAvatarUrl } from "../../../lib/avatar";
import { GenerationSession, timelineForPath, usageLabel } from "../stream.js";
import ConversationResources from "../components/ConversationResources.vue";
const auth = useAuthStore(), route = useRoute(), router = useRouter();
const conversations = ref([]), cards = ref([]), profiles = ref([]), model = ref(null), selected = ref(null), messages = ref([]), tree = ref([]), draft = ref(""), error = ref("");
const conversationFilter = ref(""), selectedProfileId = ref(""), newProfile = ref(""), newTitle = ref(""), newCard = ref("");
const loading = ref(false), sending = ref(false), creating = ref(false), profilesLoading = ref(false), timeline = ref(null), showCreate = ref(false), showCard = ref(false), pendingMessage = ref(null);
const pendingAssistant = ref(null), budgetUsage = ref(null), actualUsage = ref(null), nativeStreaming = ref(true), stopping = ref(false), lastAttempt = ref(null), uncertain = ref(false);
const resources = ref(null), sources = ref([]);
const carrySummary = ref(false);
let previewEpoch = 0, previewTimer;
const generation = new GenerationSession({ api, onEvent: receiveEvent });
const activeNodeId = computed(() => selected.value?.active_leaf_id || null), activePath = computed(() => new Set((selected.value?.context || messages.value).map((message) => message.id).filter(Boolean))), activeChildCount = computed(() => activeNodeId.value ? tree.value.filter((node) => node.parent_id === activeNodeId.value).length : 0);
const filteredConversations = computed(() => { const query = conversationFilter.value.trim().toLowerCase(); return query ? conversations.value.filter((item) => item.title.toLowerCase().includes(query)) : conversations.value; });
const selectedCard = computed(() => cards.value.find((card) => card.id === selected.value?.card_id));
const composerPlaceholder = computed(() => !selected.value ? "先选择一个会话…" : selectedCard.value ? `对「${selectedCard.value.name}」说些什么…` : "写下你的下一句话…");
const canSend = computed(() => Boolean(selected.value && draft.value.trim() && !sending.value && !uncertain.value && !profilesLoading.value));
const draftPercent = computed(() => Math.round((draft.value.length / 12000) * 100));
const draftCountClass = computed(() => draftPercent.value >= 100 ? "is-limit" : draftPercent.value >= 90 ? "is-warning" : "");
const estimateTokens = computed(() => budgetUsage.value?.input_tokens || selected.value?.tokens || 0);
const activeModel = computed(() => profiles.value.find((profile) => profile.id === selectedProfileId.value) || profiles.value.find((profile) => profile.active) || model.value);
const activeModelLabel = computed(() => activeModel.value ? `${activeModel.value.name || activeModel.value.model} · ${activeModel.value.model}` : "未配置模型");
const modelMenuName = computed(() => profilesLoading.value ? "正在加载模型…" : activeModel.value ? (activeModel.value.name || activeModel.value.model) : "未配置模型");
const contextPercent = computed(() => Math.min(100, Math.max(2, Math.round((estimateTokens.value / (budgetUsage.value?.available_input || 32768)) * 100))));
const contextLevel = computed(() => contextPercent.value >= 80 ? "is-high" : contextPercent.value >= 60 ? "is-mid" : "is-low");
const pathIds = computed(() => new Set(activePath.value));
const timelineEntries = computed(() => timelineForPath(selected.value?.context || messages.value, [pendingMessage.value, pendingAssistant.value]));
const visibleTree = computed(() => { const children = new Map(); for (const node of tree.value) { const parent = node.parent_id || "root"; if (!children.has(parent)) children.set(parent, []); children.get(parent).push(node); } const rows = []; function visit(parent, depth) { (children.get(parent) || []).forEach((node, index, list) => { rows.push({ ...node, depth, isLast: index === list.length - 1 }); visit(node.id, depth + 1); }); } visit("root", 0); return rows; });
function nodeText(node) { const content = node.content || node.summary; return node.entry_type === "memory_update" ? "分支记忆更新" : (content || "").replace(/\s+/g, " ").slice(0, 30) || "空消息"; }
function nodeKind(node) { return node.entry_type === "memory_update" ? "记" : node.entry_type === "compaction" ? "压" : node.entry_type === "branch_summary" ? "分" : node.role === "user" ? "我" : "AI"; }
function profileLabel(profile) { return `${profile.name || profile.model} · ${profile.model}`; }
function formatDate(value) { if (!value) return ""; return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(value)); }
function formatTime(value) { if (!value) return ""; return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
async function scrollBottom() { await nextTick(); const container = timeline.value; if (container) container.scrollTop = container.scrollHeight; }
function applyConversation(payload) { selected.value = payload; messages.value = payload.messages || []; tree.value = payload.tree || []; selectedProfileId.value = payload.profile_id || profiles.value.find((profile) => profile.active)?.id || profiles.value[0]?.id || ""; sources.value = [...messages.value].reverse().find(m => m.role === "assistant")?.metadata?.sources || []; }
function resourcesUpdated(payload) { applyConversation(payload); preview(); }
async function refresh() { conversations.value = (await api.get("/conversations")).conversations; }
async function loadProfiles() { profilesLoading.value = true; try { const result = await api.get("/settings/models"); profiles.value = (result.models || []).filter((profile) => (profile.model_type || "llm") === "llm"); newProfile.value = profiles.value.find((profile) => profile.active)?.id || profiles.value[0]?.id || ""; } finally { profilesLoading.value = false; } }
async function select(id) { if (sending.value || loading.value) return; loading.value = true; error.value = ""; try { applyConversation(await api.get(`/conversations/${id}`)); draft.value = ""; await router.replace({ path: "/chat", query: { conversation: id } }); await scrollBottom(); } catch (err) { report(err); } finally { loading.value = false; } }
async function selectNode(nodeId) { if (!selected.value || sending.value || uncertain.value || loading.value || activeNodeId.value === nodeId) return; loading.value = true; error.value = ""; try { applyConversation(await api.patch(`/conversations/${selected.value.id}/active-node`, { node_id: nodeId, summary: carrySummary.value })); carrySummary.value = false; await scrollBottom(); } catch (err) { report(err); } finally { loading.value = false; } }
function selectBranch(command) { selectNode(command === "__root__" ? null : command); }
async function changeModel(profileId) { if (!selected.value || sending.value || uncertain.value || !profileId || profileId === selectedProfileId.value) return; const previousProfileId = selectedProfileId.value; try { const result = await api.patch(`/conversations/${selected.value.id}`, { profile_id: profileId }); selected.value.profile_id = result.profile_id || profileId; selectedProfileId.value = result.profile_id || profileId; ElMessage.success(`已切换到 ${profileLabel(profiles.value.find((profile) => profile.id === profileId) || {})}`); } catch (err) { selectedProfileId.value = previousProfileId; report(err); } }
async function goSettings() { await router.push("/settings"); }
async function create() { if (creating.value) return; creating.value = true; try { const item = await api.post("/conversations", { title: newTitle.value.trim() || "新会话", card_id: newCard.value || null, profile_id: newProfile.value || null }); await refresh(); showCreate.value = false; newTitle.value = ""; newCard.value = ""; await select(item.id); } catch (err) { report(err); } finally { creating.value = false; } }
async function send() {
  if (!canSend.value) return;
  lastAttempt.value = { message: draft.value.trim(), parent_id: activeNodeId.value,
    profile_id: selectedProfileId.value || null, request_id: crypto.randomUUID() };
  await startAttempt();
}
async function startAttempt() {
  sending.value = true; error.value = ""; uncertain.value = false; actualUsage.value = null;
  pendingMessage.value = { role: "user", content: lastAttempt.value.message };
  pendingAssistant.value = { role: "assistant", content: "" };
  draft.value = "";
  await scrollBottom();
  await generation.send(selected.value.id, lastAttempt.value);
}
function receiveEvent(name, data) {
  if (name === "start") nativeStreaming.value = data.capabilities?.native_streaming;
  if (name === "context") budgetUsage.value = data;
  if (name === "sources") sources.value = data;
  if (name === "delta" && pendingAssistant.value) { pendingAssistant.value.content += data.text; scrollBottom(); }
  if (name === "terminal") {
    if (data.storage_error) {
      error.value = data.error; uncertain.value = true;
    } else {
      applyConversation(data);
      actualUsage.value = Object.keys(data.usage || {}).length ? data.usage : null;
      error.value = data.status === "completed" ? (data.mirror_warning || data.memory_warning || "") : data.error || "生成已中断";
      if (!data.reply) draft.value = lastAttempt.value?.message || "";
      pendingMessage.value = null; pendingAssistant.value = null;
      refresh().catch(report);
    }
    sending.value = false; stopping.value = false; scrollBottom();
  }
  if (name === "error") {
    uncertain.value = data.uncertain !== false; sending.value = false; stopping.value = false;
    error.value = uncertain.value ? `${data.message}；可重连本次请求确认状态，不会自动重复调用模型` : data.message;
    if (!uncertain.value) { pendingMessage.value = null; pendingAssistant.value = null; }
    draft.value = lastAttempt.value?.message || "";
  }
}
async function stop() { if (stopping.value) return; stopping.value = true; try { await generation.stop(); } catch (err) { error.value = err.message; } finally { stopping.value = false; } }
async function retry() {
  if (sending.value || !lastAttempt.value) return;
  if (!uncertain.value) lastAttempt.value = { ...lastAttempt.value, request_id: crypto.randomUUID() };
  await startAttempt();
}
async function preview() {
  const epoch = ++previewEpoch, id = selected.value?.id;
  if (!id || sending.value) return;
  try {
    const result = await api.post(`/conversations/${id}/context-preview`, {
      message: draft.value, profile_id: selectedProfileId.value || null,
    });
    if (epoch === previewEpoch && selected.value?.id === id && !sending.value) budgetUsage.value = result.context_usage;
  } catch (err) { if (epoch === previewEpoch && !sending.value) error.value = err.message; }
}
watch([draft, selectedProfileId, () => selected.value?.active_leaf_id, () => selected.value?.id], () => {
  clearTimeout(previewTimer); previewEpoch++; previewTimer = setTimeout(preview, 350);
});
watch(() => selected.value?.id, () => {
  generation.dispose(); uncertain.value = false; pendingMessage.value = null; pendingAssistant.value = null;
  lastAttempt.value = null; budgetUsage.value = null; actualUsage.value = null;
});
onBeforeUnmount(() => { clearTimeout(previewTimer); previewEpoch++; generation.dispose(); });
async function copyMessage(message) { try { await navigator.clipboard.writeText(message.content || ""); ElMessage.success("已复制消息内容"); } catch { report(new Error("复制失败，请手动选择文本")); } }
async function labelNode(message) { let value; try { ({ value } = await ElMessageBox.prompt("节点标记（留空可清除）", "标记节点", { inputValue: message.label || "", inputPlaceholder: "例如：关键转折", confirmButtonText: "保存", cancelButtonText: "取消" })); } catch { return; } try { await api.put(`/conversations/${selected.value.id}/nodes/${message.id}/label`, { label: value }); const target = messages.value.find((item) => item.id === message.id); if (target) target.label = (value || "").trim() || null; const treeNode = tree.value.find((item) => item.id === message.id); if (treeNode) treeNode.label = (value || "").trim() || null; } catch (err) { report(err); } }
async function rename(item) { let value; try { ({ value } = await ElMessageBox.prompt("会话标题", "重命名", { inputValue: item.title, inputPattern: /^.{1,100}$/, inputErrorMessage: "请输入 1 到 100 个字符", confirmButtonText: "保存", cancelButtonText: "取消" })); } catch { return; } try { await api.patch(`/conversations/${item.id}`, { title: value }); await refresh(); if (selected.value?.id === item.id) selected.value.title = value; } catch (err) { report(err); } }
async function remove(item) { if (!await confirmDelete(`删除会话“${item.title}”及全部消息？`)) return; try { await api.delete(`/conversations/${item.id}`); await refresh(); if (selected.value?.id === item.id) { selected.value = null; messages.value = []; tree.value = []; await router.replace("/chat"); if (conversations.value[0]) await select(conversations.value[0].id); } } catch (err) { report(err); } }
watch(() => messages.value.length, () => scrollBottom());
onMounted(async () => { try { const [cardResult, modelResult] = await Promise.all([api.get("/cards"), api.get("/settings/model")]); cards.value = cardResult.cards; model.value = modelResult; await loadProfiles(); await refresh(); const id = conversations.value.find((item) => item.id === route.query.conversation)?.id || conversations.value[0]?.id; if (id) await select(id); } catch (err) { report(err); } });
</script>

<style scoped>
.pi-chat-heading { flex-shrink: 0; }
.generation-controls { display: flex; flex: 0 0 auto; flex-wrap: wrap; align-items: center; gap: 8px 14px; padding: 6px 22px; border-top: 1px solid var(--pw-border); overflow-wrap: anywhere; }
.generation-controls small { max-width: 100%; font-size: 11px; }
.branch-options { padding: 6px 12px; border-bottom: 1px solid var(--pw-border); }
@media (max-width: 700px) { .generation-controls { gap: 4px 8px; padding: 6px 12px; } }
</style>
