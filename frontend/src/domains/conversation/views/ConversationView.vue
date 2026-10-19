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
            <span v-if="selectedCard" class="card-mark" aria-hidden="true">{{ cardInitial }}</span>
            <h2>{{ selected?.title || '选择一个会话' }}</h2>
            <el-tag v-if="selected?.card_id" size="small" effect="plain" type="warning">{{ selectedCard?.name || '角色卡' }}</el-tag>
          </div>
          <p v-if="selected" class="muted heading-meta">{{ messages.length ? `${messages.length} 条消息` : '新对话' }}<span v-if="activeChildCount"> · 当前节点有 {{ activeChildCount }} 个分支</span><span v-if="selected.tokens"> · 上下文 {{ selected.tokens.toLocaleString() }} tokens</span></p>
        </div>
        <div v-if="selected" class="chat-heading-actions">
          <el-button v-if="selectedCard" text class="heading-link" :icon="InfoFilled" @click="showCard = true">角色设定</el-button>
          <el-dropdown v-if="tree.length" trigger="click" class="branch-dropdown" @command="selectBranch"><el-button text class="branch-trigger"><span class="branch-trigger-dot" />{{ activeNodeId ? '当前分支' : '新分支起点' }}<small>{{ tree.length }} 节点</small><ArrowDown /></el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="__root__">新分支起点</el-dropdown-item><el-dropdown-item v-for="node in visibleTree" :key="node.id" :command="node.id" :class="{ 'branch-path-item': activePath.has(node.id) }">{{ '　'.repeat(node.depth) }}{{ nodeKind(node) }} · {{ nodeText(node) }}</el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        </div>
      </div>
      <section ref="timeline" class="messages pi-messages timeline">
        <div v-if="!selected" class="chat-empty"><div class="chat-empty-mark"><ChatDotRound /></div><h3>开始一段角色对话</h3><p>选择左侧会话，或创建一个新的角色场景。</p><el-button type="primary" :icon="Plus" @click="showCreate = true">创建会话</el-button></div>
        <template v-else>
          <div v-if="selectedCard && !messages.length && !sending" class="card-intro"><span class="card-mark" aria-hidden="true">{{ cardInitial }}</span><div><strong>{{ selectedCard.name }}</strong><p>{{ selectedCard.intro || '还没有设定简介，点击「角色设定」查看或补充。' }}</p><small>在下方写下第一句话，开始这段对话。</small></div></div>
          <el-empty v-else-if="!messages.length && !sending && !timelineEntries.length" description="等待模型回复" :image-size="70" />
          <template v-for="entry in timelineEntries" :key="entry.key">
            <div v-if="entry.kind === 'marker'" class="context-marker" :class="entry.type"><el-icon><Collection /></el-icon><span>{{ entry.type === 'compaction' ? '上下文已压缩' : '分支摘要' }}</span><em v-if="entry.tokens_before">压缩前 {{ entry.tokens_before.toLocaleString() }} tokens</em><small v-if="entry.label">{{ entry.label }}</small><p v-if="entry.summary">{{ entry.summary }}</p></div>
            <article v-else class="message" :class="[entry.message.role, { active: entry.message.id === activeNodeId, pending: entry.pending }]">
              <div class="message-avatar"><img v-if="entry.message.role === 'user' && auth.user?.avatar" :src="auth.user.avatar" alt="个人头像" /><el-icon v-else-if="entry.message.role === 'user'"><User /></el-icon><span v-else-if="selectedCard && cardInitial" class="avatar-initial">{{ cardInitial }}</span><el-icon v-else><ChatDotRound /></el-icon></div>
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
                <div v-if="entry.message.id && !entry.pending" class="message-actions"><el-tooltip content="复制内容" placement="top"><el-button text size="small" :icon="DocumentCopy" @click="copyMessage(entry.message)" /></el-tooltip><el-tooltip content="从此处继续（新建分支）" placement="top"><el-button text size="small" :icon="Share" :disabled="sending" @click="selectNode(entry.message.id)" /></el-tooltip><el-tooltip content="标记该节点" placement="top"><el-button text size="small" :icon="PriceTag" :disabled="sending" @click="labelNode(entry.message)" /></el-tooltip></div>
              </div>
            </article>
          </template>
          <div v-if="sending" class="typing-indicator"><span /><span /><span />正在生成回复</div>
        </template>
      </section>
      <form class="composer pi-composer" @submit.prevent="send"><div v-if="error" class="composer-error" role="alert" aria-live="polite"><el-icon><WarningFilled /></el-icon><span>{{ error }}</span></div><div class="composer-box"><el-input v-model="draft" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" resize="none" maxlength="12000" :disabled="!selected || sending" :placeholder="composerPlaceholder" aria-label="消息" @keydown.ctrl.enter.prevent="send" @keydown.meta.enter.prevent="send" /><div class="composer-toolbar"><span class="composer-toolbar-status" :class="{ 'is-ready': canSend }">{{ sending ? '正在生成回复…' : canSend ? '准备发送' : selected ? '输入消息后发送' : '先选择一个会话' }}</span><el-button type="primary" :icon="Promotion" native-type="submit" :disabled="!canSend" :loading="sending" :aria-label="sending ? '正在发送消息' : '发送消息'">发送</el-button></div></div><div class="composer-footer"><el-dropdown trigger="click" popper-class="model-popover" class="model-menu" :disabled="!selected || sending" @command="changeModel"><button type="button" class="model-menu-trigger" :class="{ 'is-loading': profilesLoading }" :disabled="!selected || sending || profilesLoading" :title="activeModelLabel"><span class="model-menu-glyph" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.6 20.1 7v10L12 21.4 3.9 17V7z" /><circle cx="12" cy="12" r="2.6" /><path d="M12 9.4V6.2M12 17.8v-3.2M14.3 13.3l2.7 1.6M7 9.1l2.7 1.6" /></svg></span><span class="model-menu-copy"><span class="model-menu-name">{{ modelMenuName }}</span><small v-if="activeModel">{{ activeModel.model }}</small></span><ArrowDown class="model-menu-caret"  /></button><template #dropdown><div class="model-popover-head"><strong>切换模型</strong><small>切换后会绑定到当前会话</small></div><el-dropdown-menu class="model-menu-list"><el-dropdown-item v-for="profile in profiles" :key="profile.id" :command="profile.id" :class="{ 'model-menu-active': profile.id === selectedProfileId }"><span class="model-menu-glyph" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.6 20.1 7v10L12 21.4 3.9 17V7z" /><circle cx="12" cy="12" r="2.6" /></svg></span><span class="model-menu-option"><span class="model-menu-option-name">{{ profile.name || profile.model }}</span><small>{{ profile.model }}</small></span><el-icon v-if="profile.id === selectedProfileId" class="model-menu-check"><Check /></el-icon></el-dropdown-item><el-dropdown-item v-if="!profiles.length" disabled>暂无可用模型</el-dropdown-item></el-dropdown-menu><div class="model-popover-foot"><button type="button" class="model-popover-action" @click="goSettings">模型设置</button><button type="button" class="model-popover-action" disabled title="待开放">上下文长度</button></div></template></el-dropdown><div v-if="selected" class="context-meter" :class="contextLevel" :title="`已使用 ${estimateTokens.toLocaleString()} tokens`"><span class="context-meter-track" aria-hidden="true"><span class="context-meter-fill" :style="{ width: `${contextPercent}%` }" /></span><span class="context-meter-value">{{ estimateTokens.toLocaleString() }} tokens</span></div><span v-else class="context-meter-empty">选择会话后开始</span><div class="composer-footer-right"><span class="composer-hint">Ctrl / ⌘ + Enter 发送</span><span class="composer-count" :class="draftCountClass">{{ draft.length.toLocaleString() }} / 12,000</span></div></div></form>
    </section>
  </div>
  <el-dialog v-model="showCreate" title="新建角色会话" width="480px" class="conversation-dialog"><el-form label-position="top" @submit.prevent="create"><el-form-item label="会话标题"><el-input v-model="newTitle" maxlength="100" placeholder="例如：雨夜里的重逢" /></el-form-item><el-form-item label="角色卡"><el-select v-model="newCard" clearable filterable class="full-width" placeholder="选择一个角色（可选）"><el-option v-for="card in cards" :key="card.id" :label="`${card.name} · ${card.book_title}`" :value="card.id" /></el-select></el-form-item><el-form-item label="使用模型"><el-select v-model="newProfile" filterable class="full-width" placeholder="选择模型"><el-option v-for="profile in profiles" :key="profile.id" :label="profileLabel(profile)" :value="profile.id" /></el-select><small class="form-help">模型可以在对话中随时切换，切换后会绑定到当前会话。</small></el-form-item><div class="dialog-actions"><el-button @click="showCreate = false">取消</el-button><el-button type="primary" :icon="Plus" native-type="submit" :loading="creating">创建会话</el-button></div></el-form></el-dialog>
  <el-drawer v-model="showCard" :title="selectedCard?.name || '角色设定'" size="420px" class="card-drawer"><template v-if="selectedCard"><p class="card-drawer-intro">{{ selectedCard.intro || '暂无简介' }}</p><dl class="card-drawer-meta"><dt>所属作品</dt><dd>{{ selectedCard.book_title || '未关联' }}</dd></dl><div class="card-drawer-body"><pre class="document-text">{{ selectedCard.content || '该角色卡还没有详细设定。' }}</pre></div><div class="card-drawer-actions"><RouterLink to="/characters"><el-button plain :icon="EditPen">前往角色库编辑</el-button></RouterLink></div></template></el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ChatDotRound, ChatLineRound, Check, Collection, DocumentCopy, EditPen, InfoFilled, MoreFilled, Plus, PriceTag, Promotion, Search, Share, User, WarningFilled } from "@element-plus/icons-vue";
import MarkdownRender from "markstream-vue";
import "markstream-vue/index.css";
import { api } from "../../../api/client";
import { useAuthStore } from "../../../stores/auth";
import { report, confirmDelete } from "../../../lib/ui";
const auth = useAuthStore(), route = useRoute(), router = useRouter();
const conversations = ref([]), cards = ref([]), profiles = ref([]), model = ref(null), selected = ref(null), messages = ref([]), tree = ref([]), draft = ref(""), error = ref("");
const conversationFilter = ref(""), selectedProfileId = ref(""), newProfile = ref(""), newTitle = ref(""), newCard = ref("");
const loading = ref(false), sending = ref(false), creating = ref(false), profilesLoading = ref(false), timeline = ref(null), showCreate = ref(false), showCard = ref(false), pendingMessage = ref(null);
const activeNodeId = computed(() => selected.value?.active_leaf_id || null), activePath = computed(() => new Set(messages.value.map((message) => message.id).filter(Boolean))), activeChildCount = computed(() => activeNodeId.value ? tree.value.filter((node) => node.parent_id === activeNodeId.value).length : 0);
const filteredConversations = computed(() => { const query = conversationFilter.value.trim().toLowerCase(); return query ? conversations.value.filter((item) => item.title.toLowerCase().includes(query)) : conversations.value; });
const selectedCard = computed(() => cards.value.find((card) => card.id === selected.value?.card_id));
const cardInitial = computed(() => (selectedCard.value?.name || "").trim().slice(0, 1));
const composerPlaceholder = computed(() => !selected.value ? "先选择一个会话…" : selectedCard.value ? `以「${selectedCard.value.name}」的身份开始对话…` : "写下你的下一句话…");
const canSend = computed(() => Boolean(selected.value && draft.value.trim() && !sending.value && !profilesLoading.value));
const draftPercent = computed(() => Math.round((draft.value.length / 12000) * 100));
const draftCountClass = computed(() => draftPercent.value >= 100 ? "is-limit" : draftPercent.value >= 90 ? "is-warning" : "");
const estimateTokens = computed(() => selected.value?.tokens || messages.value.reduce((total, item) => total + Math.ceil((item.content || "").length / 2), 0));
const activeModel = computed(() => profiles.value.find((profile) => profile.id === selectedProfileId.value) || profiles.value.find((profile) => profile.active) || model.value);
const activeModelLabel = computed(() => activeModel.value ? `${activeModel.value.name || activeModel.value.model} · ${activeModel.value.model}` : "未配置模型");
const modelMenuName = computed(() => profilesLoading.value ? "正在加载模型…" : activeModel.value ? (activeModel.value.name || activeModel.value.model) : "未配置模型");
const CONTEXT_BUDGET = 32000;
const contextPercent = computed(() => Math.min(100, Math.max(2, Math.round((estimateTokens.value / CONTEXT_BUDGET) * 100))));
const contextLevel = computed(() => { const percent = (estimateTokens.value / CONTEXT_BUDGET) * 100; return percent >= 85 ? "is-high" : percent >= 60 ? "is-mid" : "is-low"; });
const pathIds = computed(() => new Set(activePath.value));
const timelineEntries = computed(() => {
  const entries = [];
  for (const node of tree.value) {
    if (node.entry_type === "compaction" || node.entry_type === "branch_summary") entries.push({ key: `marker-${node.id}`, kind: "marker", type: node.entry_type, summary: node.summary, tokens_before: node.tokens_before, label: node.label, created_at: node.created_at });
  }
  for (const message of messages.value) entries.push({ key: `message-${message.id || message.created_at}`, kind: "message", message });
  if (pendingMessage.value) entries.push({ key: "pending", kind: "message", pending: true, message: pendingMessage.value });
  return entries;
});
const visibleTree = computed(() => { const children = new Map(); for (const node of tree.value) { const parent = node.parent_id || "root"; if (!children.has(parent)) children.set(parent, []); children.get(parent).push(node); } const rows = []; function visit(parent, depth) { (children.get(parent) || []).forEach((node, index, list) => { rows.push({ ...node, depth, isLast: index === list.length - 1 }); visit(node.id, depth + 1); }); } visit("root", 0); return rows; });
function nodeText(node) { const content = node.content || node.summary; return (content || "").replace(/\s+/g, " ").slice(0, 30) || "空消息"; }
function nodeKind(node) { return node.entry_type === "compaction" ? "压" : node.entry_type === "branch_summary" ? "分" : node.role === "user" ? "我" : "AI"; }
function profileLabel(profile) { return `${profile.name || profile.model} · ${profile.model}`; }
function formatDate(value) { if (!value) return ""; return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(value)); }
function formatTime(value) { if (!value) return ""; return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
async function scrollBottom() { await nextTick(); const container = timeline.value; if (container) container.scrollTop = container.scrollHeight; }
function applyConversation(payload) { selected.value = payload; messages.value = payload.messages || []; tree.value = payload.tree || []; selectedProfileId.value = payload.profile_id || profiles.value.find((profile) => profile.active)?.id || profiles.value[0]?.id || ""; }
async function refresh() { conversations.value = (await api.get("/conversations")).conversations; }
async function loadProfiles() { profilesLoading.value = true; try { const result = await api.get("/settings/models"); profiles.value = (result.models || []).filter((profile) => (profile.model_type || "llm") === "llm"); newProfile.value = profiles.value.find((profile) => profile.active)?.id || profiles.value[0]?.id || ""; } finally { profilesLoading.value = false; } }
async function select(id) { if (sending.value || loading.value) return; loading.value = true; error.value = ""; try { applyConversation(await api.get(`/conversations/${id}`)); draft.value = ""; await router.replace({ path: "/chat", query: { conversation: id } }); await scrollBottom(); } catch (err) { report(err); } finally { loading.value = false; } }
async function selectNode(nodeId) { if (!selected.value || sending.value || loading.value || activeNodeId.value === nodeId) return; loading.value = true; error.value = ""; try { applyConversation(await api.patch(`/conversations/${selected.value.id}/active-node`, { node_id: nodeId })); await scrollBottom(); } catch (err) { report(err); } finally { loading.value = false; } }
function selectBranch(command) { selectNode(command === "__root__" ? null : command); }
async function changeModel(profileId) { if (!selected.value || !profileId || profileId === selectedProfileId.value) return; const previousProfileId = selectedProfileId.value; try { const result = await api.patch(`/conversations/${selected.value.id}`, { profile_id: profileId }); selected.value.profile_id = result.profile_id || profileId; selectedProfileId.value = result.profile_id || profileId; ElMessage.success(`已切换到 ${profileLabel(profiles.value.find((profile) => profile.id === profileId) || {})}`); } catch (err) { selectedProfileId.value = previousProfileId; report(err); } }
async function goSettings() { await router.push("/settings"); }
async function create() { if (creating.value) return; creating.value = true; try { const item = await api.post("/conversations", { title: newTitle.value.trim() || "新会话", card_id: newCard.value || null, profile_id: newProfile.value || null }); await refresh(); showCreate.value = false; newTitle.value = ""; newCard.value = ""; await select(item.id); } catch (err) { report(err); } finally { creating.value = false; } }
async function send() { if (!selected.value || !draft.value.trim() || sending.value) return; const message = draft.value.trim(), id = selected.value.id, parentId = activeNodeId.value; sending.value = true; error.value = ""; pendingMessage.value = { role: "user", content: message, parent_id: parentId }; draft.value = ""; await scrollBottom(); try { const result = await api.post(`/conversations/${id}/messages`, { message, parent_id: parentId, profile_id: selectedProfileId.value || null }); messages.value = result.messages || messages.value; tree.value = result.tree || tree.value; selected.value.active_leaf_id = result.active_leaf_id; await refresh(); selected.value.title = conversations.value.find((item) => item.id === id)?.title || selected.value.title; } catch (err) { draft.value = message; error.value = err.message; } finally { pendingMessage.value = null; sending.value = false; await scrollBottom(); } }
async function copyMessage(message) { try { await navigator.clipboard.writeText(message.content || ""); ElMessage.success("已复制消息内容"); } catch { report(new Error("复制失败，请手动选择文本")); } }
async function labelNode(message) { let value; try { ({ value } = await ElMessageBox.prompt("节点标记（留空可清除）", "标记节点", { inputValue: message.label || "", inputPlaceholder: "例如：关键转折", confirmButtonText: "保存", cancelButtonText: "取消" })); } catch { return; } try { await api.put(`/conversations/${selected.value.id}/nodes/${message.id}/label`, { label: value }); const target = messages.value.find((item) => item.id === message.id); if (target) target.label = (value || "").trim() || null; const treeNode = tree.value.find((item) => item.id === message.id); if (treeNode) treeNode.label = (value || "").trim() || null; } catch (err) { report(err); } }
async function rename(item) { let value; try { ({ value } = await ElMessageBox.prompt("会话标题", "重命名", { inputValue: item.title, inputPattern: /^.{1,100}$/, inputErrorMessage: "请输入 1 到 100 个字符", confirmButtonText: "保存", cancelButtonText: "取消" })); } catch { return; } try { await api.patch(`/conversations/${item.id}`, { title: value }); await refresh(); if (selected.value?.id === item.id) selected.value.title = value; } catch (err) { report(err); } }
async function remove(item) { if (!await confirmDelete(`删除会话“${item.title}”及全部消息？`)) return; try { await api.delete(`/conversations/${item.id}`); await refresh(); if (selected.value?.id === item.id) { selected.value = null; messages.value = []; tree.value = []; await router.replace("/chat"); if (conversations.value[0]) await select(conversations.value[0].id); } } catch (err) { report(err); } }
watch(() => messages.value.length, () => scrollBottom());
onMounted(async () => { try { const [cardResult, modelResult] = await Promise.all([api.get("/cards"), api.get("/settings/model")]); cards.value = cardResult.cards; model.value = modelResult; await loadProfiles(); await refresh(); const id = conversations.value.find((item) => item.id === route.query.conversation)?.id || conversations.value[0]?.id; if (id) await select(id); } catch (err) { report(err); } });
</script>
