<template>
  <div class="settings-workspace">
    <div class="settings-nav" role="tablist" aria-label="设置分类">
      <button v-for="item in settingTabs" :key="item.value" class="settings-nav-item" role="tab" :aria-selected="tab === item.value" :class="{ active: tab === item.value }" @click="selectTab(item.value)"><span class="settings-nav-icon" aria-hidden="true">{{ item.icon }}</span>{{ item.label }}</button>
    </div>

    <section v-if="tab === 'model'">
      <div class="model-type-tabs" role="tablist" aria-label="模型类型">
        <button v-for="item in modelTypes" :key="item.value" type="button" role="tab" :aria-selected="modelType === item.value" :class="{ active: modelType === item.value }" @click="selectModelType(item.value)"><el-icon><component :is="item.icon" /></el-icon>{{ item.label }}<span>{{ profiles.filter((profile) => (profile.model_type || 'llm') === item.value).length }}</span></button>
      </div>
      <div class="model-console">
      <aside class="model-sidebar" v-loading="profilesLoading"><div class="sidebar-heading"><span>模型服务</span><el-tag size="small" type="info">{{ visibleProfiles.length }} 个模型</el-tag></div>
        <div v-for="group in providerGroups" :key="group.key" class="provider-group">
          <button class="provider-row" :class="{ selected: editorMode === 'provider' && selectedProvider === group.key }" @click="selectProvider(group.key)"><span class="provider-glyph">◈</span><span>{{ group.name }}</span></button>
          <button v-for="item in group.models" :key="item.id" class="model-row" :class="{ selected: editorMode === 'model' && selectedProfileId === item.id }" @click="selectModel(item.id)"><span class="model-name" :title="item.model">{{ item.name || item.model }}</span><span v-if="item.active" class="active-mark">使用中</span></button>
          <button v-if="!visibleProfiles.length && !profilesLoading && modelType === 'llm'" class="model-row" :class="{ selected: editorMode === 'model' }" @click="editorMode = 'model'"><span class="model-name" :title="model.model">{{ model.name || model.model || '默认模型' }}</span><span class="active-mark">默认</span></button>
          <button class="add-model" @click="addModel(group.key)">＋ 添加模型</button>
        </div>
        <button class="add-provider" @click="addProvider">＋ 添加服务商</button>
      </aside>

      <main class="model-editor" v-loading="loading">
        <template v-if="editorMode === 'provider'">
          <div class="editor-heading"><div><p class="editor-kicker">PROVIDER</p><h2>{{ model.provider_name || '新服务商' }}</h2></div><el-button type="danger" plain :disabled="!selectedProvider || providerProfiles.length === 0 || providerProfiles.some((item) => item.active)" @click="removeProvider">删除</el-button></div>
          <el-form label-position="top" class="provider-form" novalidate @submit.prevent="saveModel">
            <el-form-item label="服务商名称"><el-input v-model="model.provider_name" maxlength="80" placeholder="例如 ECNU、GLM、Anthropic" /></el-form-item>
            <el-form-item label="Base URL"><el-input v-model="model.base_url" placeholder="https://example.com/v1/" /></el-form-item>
            <el-form-item label="API Key"><el-input v-model="key" type="password" show-password autocomplete="off" :placeholder="model.has_api_key ? '已保存，留空则保持不变' : '请输入 API Key'" /><p class="field-help">填写模型服务商提供的密钥；留空会保留已保存的密钥。</p></el-form-item>
            <el-form-item label="请求协议"><el-select v-model="model.api_protocol" class="wide-control" @change="setProtocol"><el-option v-for="item in protocolOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
            <div class="subsection-heading"><h3>请求头</h3><el-button plain size="small" @click="addHeader">＋ 添加请求头</el-button></div>
            <div v-if="headerRows.length" class="headers-list"><div v-for="(header, index) in headerRows" :key="header.id" class="header-row"><el-input v-model="header.name" placeholder="请求头名称" /><el-input v-model="header.value" type="password" show-password placeholder="请求头内容" /><el-button text type="danger" @click="headerRows.splice(index, 1)">移除</el-button></div></div>
            <p class="field-help">自定义请求头会随模型请求一同发送。</p>
            <div class="editor-actions"><el-button type="primary" native-type="submit" :loading="saving">保存服务商</el-button><el-button :loading="testing" :disabled="saving" @click="testModel">测试</el-button></div>
          </el-form>
        </template>

        <template v-else>
          <div class="editor-heading"><div><p class="editor-kicker">{{ currentModelType.label }}</p><h2>{{ model.name || model.model || '新模型' }}</h2><el-tag v-if="selectedProfile" size="small" :type="selectedProfile.test_status === 'passed' ? 'success' : selectedProfile.test_status === 'failed' ? 'danger' : 'info'">{{ selectedProfile.test_status === 'passed' ? '连接测试通过' : selectedProfile.test_status === 'failed' ? '连接测试失败' : '尚未测试连接' }}</el-tag></div><div class="heading-actions"><el-button :loading="testing" :disabled="saving" @click="testModel">测试连接</el-button><el-button type="danger" plain :disabled="!selectedProfileId || selectedIsActive || testing" :loading="profileBusy" @click="removeSelected">移除</el-button></div></div>
          <el-form label-position="top" class="model-form" novalidate @submit.prevent="saveModel">
            <div class="two-column"><el-form-item label="模型 ID"><el-input v-model="model.model" maxlength="120" placeholder="服务商提供的模型 ID" required /></el-form-item><el-form-item label="显示名称"><el-input v-model="model.name" maxlength="80" placeholder="显示名称" /></el-form-item></div>
            <div class="fill-row"><el-button plain size="small" @click="fillModelInfo">填入模型信息</el-button><span v-if="model.has_api_key" class="saved-hint">服务商密钥已配置</span></div>
            <section v-if="modelType === 'llm'" class="capability-section"><div class="section-title-row"><h3>能力</h3><span class="muted">模型说明保存在当前浏览器</span></div><el-checkbox v-model="capabilities.reasoning">推理 / 思考</el-checkbox><el-checkbox v-model="capabilities.image">图片输入</el-checkbox></section>
            <section v-if="modelType === 'llm'" class="spec-section"><div class="section-title-row"><h3>模型规格</h3><button class="link-button" type="button" @click="showPricing = !showPricing">{{ showPricing ? '收起价格' : '编辑价格' }}</button></div><div class="two-column"><el-form-item label="上下文窗口（tokens）"><el-input-number v-model="model.context_window" :min="128" :max="2000000" :step="1024" class="wide-control" /></el-form-item><el-form-item label="最大输出 tokens"><el-input-number v-model="model.max_tokens" :min="128" :max="16384" :step="128" class="wide-control" /></el-form-item></div><div v-if="showPricing" class="pricing-grid"><label>输入 / 1M tokens<el-input v-model="pricing.input" placeholder="$0" /></label><label>输出 / 1M tokens<el-input v-model="pricing.output" placeholder="$0" /></label><label>缓存读取<el-input v-model="pricing.cacheRead" placeholder="$0" /></label><label>缓存写入<el-input v-model="pricing.cacheWrite" placeholder="$0" /></label></div><div v-else class="pricing-summary"><span>输入 <strong>{{ pricing.input || '$0' }}</strong></span><span>输出 <strong>{{ pricing.output || '$0' }}</strong></span><span>缓存读取 <strong>{{ pricing.cacheRead || '$0' }}</strong></span><span>缓存写入 <strong>{{ pricing.cacheWrite || '$0' }}</strong></span></div></section>
            <el-collapse class="advanced-collapse"><el-collapse-item title="高级设置" name="advanced"><div v-if="modelType === 'llm'" class="two-column"><el-form-item label="Temperature"><el-input-number v-model="model.temperature" :min="0" :max="2" :step="0.1" class="wide-control" /></el-form-item><el-form-item label="Top P"><el-input-number v-model="model.top_p" :min="0.01" :max="1" :step="0.05" class="wide-control" /></el-form-item></div><el-form-item label="请求超时（秒）"><el-input-number v-model="model.timeout_seconds" :min="5" :max="300" :step="5" /></el-form-item></el-collapse-item></el-collapse>
            <div class="editor-actions sticky-actions"><el-button type="primary" native-type="submit" :loading="saving" :disabled="testing">保存</el-button><el-button v-if="modelType === 'llm' && selectedProfileId && !selectedIsActive" @click="activateSelected">设为当前对话模型</el-button></div>
            <el-alert v-if="testResult" :title="testResult" :type="testOk ? 'success' : 'error'" :closable="false" class="spaced" />
          </el-form>
        </template>
        <el-alert v-if="editorMode === 'provider' && testResult" :title="testResult" :type="testOk ? 'success' : 'error'" :closable="false" class="spaced" />
      </main>
      </div>
    </section>

    <section v-else class="secondary-settings">
      <ModelSelection v-if="tab === 'selection'" v-loading="selectionLoading" :profiles="profiles" :selection="selection" @manage="openModelSettings" @saved="selection = $event" />
      <el-form v-else-if="tab === 'profile'" label-position="top" class="settings-form profile-form" @submit.prevent="saveProfile">
        <h2>个人资料</h2><p class="muted">用喜欢的名字和头像，装点你的工作区。</p>
        <div class="avatar-upload">
          <img :src="auth.user?.avatar || defaultAvatar" alt="个人头像预览" class="settings-avatar" />
          <div><strong>你的头像</strong><p class="field-help">PNG、JPG 或 WebP，最大 2 MB</p>
            <input ref="avatarInput" type="file" accept="image/png,image/jpeg,image/webp" hidden :disabled="avatarBusy" @change="uploadAvatar" />
            <el-button :loading="avatarBusy" @click="avatarInput?.click()">上传新头像</el-button>
          </div>
        </div>
        <el-form-item label="显示名称"><el-input v-model="profile.username" minlength="2" maxlength="40" placeholder="怎么称呼你？" required /></el-form-item>
        <el-form-item label="邮箱（选填）"><el-input v-model="profile.email" type="email" maxlength="254" placeholder="仅用于个人资料" /></el-form-item>
        <div class="editor-actions"><el-button type="primary" native-type="submit" :loading="profileBusy">保存个人资料</el-button></div>
      </el-form>
      <el-form v-else-if="tab === 'role'" label-position="top" class="settings-form" @submit.prevent="saveRole"><el-form-item label="系统提示词"><el-input v-model="prompt" type="textarea" :rows="12" maxlength="12000" /></el-form-item><el-button type="primary" native-type="submit" :loading="roleBusy">保存角色设定</el-button></el-form>
      <section v-else class="settings-form service-status">
        <h2>服务状态</h2><p class="muted">检查创作工作区与后端的连接情况。模型地址和密钥统一在模型设置中管理。</p>
        <div class="connection-status"><span>后端服务</span><el-tag :type="healthy === true ? 'success' : healthy === false ? 'danger' : 'info'">{{ healthy === true ? '已连接' : healthy === false ? '未连接' : '未检测' }}</el-tag></div>
        <div v-for="item in functionLabels" :key="item.key" class="function-status-row">
          <div><strong>{{ item.label }}</strong><small v-if="selection.statuses?.[item.key]?.model">{{ selection.statuses[item.key].model.provider_name }} / {{ selection.statuses[item.key].model.model }}</small><small v-if="selection.statuses?.[item.key] && !['healthy', 'disabled'].includes(selection.statuses[item.key].status)" class="status-detail">{{ selection.statuses[item.key].message }}</small></div>
          <el-tag :type="statusType(item.key)">{{ statusLabel(item.key) }}</el-tag>
        </div>
        <p class="field-help">模型状态依据最近一次连接测试和已保存的选用配置。检测连接时会重新验证选中的模型。</p>
        <div class="editor-actions"><el-button type="primary" :loading="checkingHealth" @click="checkHealth">检测连接</el-button><el-button @click="selectTab('model')">配置模型服务</el-button></div>
        <el-button text type="primary" @click="selectTab('selection')">修改模型选用</el-button>
      </section>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api, upload } from "../../../api/client";
import { activateModel, createModel, deleteModel, getModelSelection, listModels, testModelProfile, updateModel } from "../client.js";
import { Cpu, Search, Sort } from "@element-plus/icons-vue";
import ModelSelection from "../components/ModelSelection.vue";
import { useAuthStore } from "../../../stores/auth";
import { report } from "../../../lib/ui";
import defaultAvatar from "../../../assets/avatar.png";

const auth = useAuthStore();
const router = useRouter(), route = useRoute();
const settingTabs = [{ value: "profile", label: "个人资料", icon: "◎" }, { value: "model", label: "模型设置", icon: "▣" }, { value: "selection", label: "模型选用", icon: "⇄" }, { value: "role", label: "角色设定", icon: "◇" }, { value: "connection", label: "服务状态", icon: "↗" }];
const modelTypes = [{ value: "llm", label: "大语言模型", icon: Cpu }, { value: "embedding", label: "Embedding", icon: Search }, { value: "reranker", label: "Reranker", icon: Sort }];
const modelType = ref(modelTypes.some((item) => item.value === route.query.type) ? route.query.type : "llm");
const currentModelType = computed(() => modelTypes.find((item) => item.value === modelType.value));
const selection = ref({});
const selectionLoading = ref(false);
const functionLabels = [{ key: "extraction", label: "提取模型" }, { key: "embedding", label: "Embedding" }, { key: "reranker", label: "Reranker" }];
const validTab = (value) => settingTabs.some((item) => item.value === value) ? value : "model";
const tab = ref(validTab(route.query.tab));
function selectTab(value) { tab.value = value; router.replace({ path: "/settings", query: { ...route.query, tab: value } }); }
watch(() => route.query.tab, (value) => { tab.value = validTab(value); });
watch(() => route.query.type, (value) => { const type = modelTypes.some((item) => item.value === value) ? value : "llm"; if (type !== modelType.value) switchModelType(type); });
watch(tab, (value) => { if (["selection", "connection"].includes(value)) refreshSelections(); });
const avatarInput = ref(null);
const editorMode = ref("model");
const selectedProvider = ref("");
const selectedProfileId = ref("");
const sourceProfileId = ref(null);
const profiles = ref([]);
const profilesLoading = ref(false);
const loading = ref(false);
const saving = ref(false);
const profileBusy = ref(false);
const testing = ref(false);
const key = ref("");
const clearKey = ref(false);
const testResult = ref("");
const testOk = ref(false);
const showPricing = ref(false);
const headerRows = ref([]);
const capabilities = reactive({ reasoning: true, image: false });
const pricing = reactive({ input: "$0", output: "$0", cacheRead: "$0", cacheWrite: "$0" });
const protocolOptions = [{ label: "openai-completions", value: "openai-completions" }, { label: "openai-responses", value: "openai-responses" }, { label: "ollama", value: "ollama" }, { label: "vivo", value: "vivo" }];
const model = reactive({ id: "", name: "", provider: "ollama", provider_name: "Ollama", api_protocol: "ollama", base_url: "http://127.0.0.1:11434", model: "qwen2.5:7b", context_window: 32768, max_tokens: 2048, temperature: 0.7, top_p: 0.9, timeout_seconds: 60, has_api_key: false, headers: {} });
const profile = reactive({ username: auth.user?.username || "", email: auth.user?.email || "" });
const prompt = ref(auth.user?.prompt || "");
watch(() => auth.user, (user) => { Object.assign(profile, { username: user.username, email: user.email }); prompt.value = user.prompt || ""; });
const avatarBusy = ref(false), roleBusy = ref(false);
const healthy = ref(null), checkingHealth = ref(false);
const visibleProfiles = computed(() => profiles.value.filter((item) => (item.model_type || "llm") === modelType.value));

const providerGroups = computed(() => {
  const groups = new Map();
  visibleProfiles.value.forEach((item) => { const key = item.provider_name || item.provider; if (!groups.has(key)) groups.set(key, { key, name: key, models: [] }); groups.get(key).models.push(item); });
  if (!groups.size) { const key = model.provider_name || model.provider; groups.set(key, { key, name: key, models: [] }); }
  return [...groups.values()];
});
const providerProfiles = computed(() => visibleProfiles.value.filter((item) => (item.provider_name || item.provider) === selectedProvider.value));
const selectedProfile = computed(() => profiles.value.find((item) => item.id === selectedProfileId.value));
const selectedIsActive = computed(() => Boolean(selectedProfile.value?.active));

function headersFromModel() { headerRows.value = Object.entries(model.headers || {}).map(([name, value], index) => ({ id: `${name}-${index}`, name, value })); }
function headersPayload() { return Object.fromEntries(headerRows.value.filter((row) => row.name.trim()).map((row) => [row.name.trim(), row.value])); }
function normaliseModel(item) { Object.assign(model, item, { name: item.name || item.model, provider_name: item.provider_name || item.provider, headers: item.headers || {}, api_protocol: item.api_protocol || (item.provider === "openai_responses" ? "openai-responses" : item.provider === "remote_api" ? "openai-completions" : item.provider) }); model.context_window = item.context_window || 32768; headersFromModel(); loadModelNotes(item.id); }
function selectModel(id) { const item = profiles.value.find((profileItem) => profileItem.id === id); if (!item) return; selectedProfileId.value = id; selectedProvider.value = item.provider_name || item.provider; editorMode.value = "model"; normaliseModel(item); key.value = ""; clearKey.value = false; testResult.value = ""; }
function selectProvider(keyValue) { selectedProvider.value = keyValue; editorMode.value = "provider"; const item = providerProfiles.value[0]; if (item) selectModel(item.id), editorMode.value = "provider"; else { selectedProfileId.value = ""; model.provider_name = keyValue; } }
function addModel(providerKey) { const source = profiles.value.find((item) => (item.provider_name || item.provider) === providerKey); sourceProfileId.value = source?.id || null; if (source) normaliseModel(source); else Object.assign(model, { base_url: modelType.value === "llm" ? "http://127.0.0.1:11434" : "http://127.0.0.1:8001/v1", provider: modelType.value === "llm" ? "ollama" : "remote_api", api_protocol: modelType.value === "llm" ? "ollama" : "openai-completions" }); loadModelNotes(""); selectedProvider.value = providerKey; selectedProfileId.value = ""; editorMode.value = "model"; Object.assign(model, { id: "", name: "", provider_name: providerKey, model: "", has_api_key: source?.has_api_key || false, headers: source?.headers || {} }); headersFromModel(); key.value = ""; clearKey.value = false; testResult.value = ""; }
function addProvider() { sourceProfileId.value = null; key.value = ""; clearKey.value = false; testResult.value = ""; loadModelNotes(""); selectedProvider.value = "new-provider"; selectedProfileId.value = ""; editorMode.value = "provider"; Object.assign(model, { provider: "remote_api", provider_name: "new-provider", model: "", name: "", base_url: "", api_protocol: "openai-completions", headers: {}, has_api_key: false }); headersFromModel(); }
function setProtocol(protocol) { model.provider = protocol === "openai-responses" ? "openai_responses" : protocol === "openai-completions" ? "remote_api" : protocol; }
function addHeader() { headerRows.value.push({ id: `${Date.now()}-${headerRows.value.length}`, name: "", value: "" }); }
function profilePayload() { return { name: model.name.trim() || model.model.trim() || "新模型", model_type: modelType.value, source_profile_id: selectedProfileId.value ? null : sourceProfileId.value, provider_name: model.provider_name.trim() || model.provider, api_protocol: model.api_protocol, headers: headersPayload(), provider: model.provider, base_url: model.base_url, model: model.model, temperature: model.temperature, top_p: model.top_p, max_tokens: model.max_tokens, timeout_seconds: model.timeout_seconds, api_key: clearKey.value ? "" : key.value || null, activate: modelType.value === "llm" && !profiles.value.some((item) => item.active) }; }
async function saveModel() { if (saving.value) return false; if (editorMode.value !== "provider" && !model.model.trim()) { report(new Error("请填写模型 ID")); return false; } if (!model.model.trim()) model.model = model.provider_name.trim() || model.provider; saving.value = true; try { const payload = profilePayload(true); const saved = selectedProfileId.value ? await updateModel(selectedProfileId.value, payload) : await createModel(payload); selectedProfileId.value = saved.id; selectedProvider.value = saved.provider_name || saved.provider; saveModelNotes(saved.id); normaliseModel(saved); await loadProfiles(); ElMessage.success("配置已保存"); return true; } catch (err) { report(err); return false; } finally { saving.value = false; } }
async function loadProfiles() { profilesLoading.value = true; try { const result = await listModels(); profiles.value = result.models || []; const selected = visibleProfiles.value.find((item) => item.id === selectedProfileId.value) || visibleProfiles.value.find((item) => item.active) || visibleProfiles.value[0]; if (selected) selectModel(selected.id); else { selectedProfileId.value = ""; addModel(modelType.value === "llm" ? "Ollama" : "本地部署"); } await loadSelections(); } finally { profilesLoading.value = false; } }
async function activateSelected() { if (!selectedProfileId.value) return; profileBusy.value = true; try { await activateModel(selectedProfileId.value); await loadProfiles(); ElMessage.success("已切换当前模型"); } catch (err) { report(err); } finally { profileBusy.value = false; } }
async function removeSelected() { if (!selectedProfileId.value || selectedIsActive.value) return; profileBusy.value = true; try { await deleteModel(selectedProfileId.value); await loadProfiles(); ElMessage.success("模型已移除"); } catch (err) { report(err); } finally { profileBusy.value = false; } }
async function removeProvider() { if (!providerProfiles.value.length) return; try { await ElMessageBox.confirm("将删除该 Provider 下的所有模型配置，是否继续？", "删除 Provider", { type: "warning" }); for (const item of providerProfiles.value) { if (!item.active) await deleteModel(item.id); } await loadProfiles(); } catch (err) { if (err !== "cancel" && err !== "close") report(err); } }
function fillModelInfo() { if (!model.name) model.name = model.model; ElMessage.info("已使用模型 ID 填入显示名称"); }
function loadModelNotes(id) {
  let notes = {};
  try { notes = JSON.parse(localStorage.getItem("personaweaver.model-notes." + id) || "{}") || {}; } catch {}
  Object.assign(capabilities, { reasoning: true, image: false }, notes.capabilities);
  Object.assign(pricing, { input: "$0", output: "$0", cacheRead: "$0", cacheWrite: "$0" }, notes.pricing);
  model.context_window = notes.context_window || 32768;
}
function saveModelNotes(id) {
  localStorage.setItem("personaweaver.model-notes." + id, JSON.stringify({ capabilities, pricing, context_window: model.context_window }));
}
async function testModel() { if (testing.value) return; testing.value = true; testResult.value = ""; let message = "", ok = false; try { if (!await saveModel()) return; const result = await testModelProfile(selectedProfileId.value); ok = true; message = result.response; } catch (err) { message = err.message; } finally { try { await loadProfiles(); } catch (err) { report(err); } testOk.value = ok; testResult.value = message; testing.value = false; } }
async function saveProfile() { profileBusy.value = true; try { auth.user = await api.patch("/auth/profile", profile); ElMessage.success("资料已保存"); } catch (err) { report(err); } finally { profileBusy.value = false; } }
async function uploadAvatar(event) { const file = event.target.files[0]; if (!file) return; if (!["image/png", "image/jpeg", "image/webp"].includes(file.type) || file.size > 2 * 1024 * 1024) { report(new Error("请选择不超过 2 MB 的 PNG、JPG 或 WebP 图片")); event.target.value = ""; return; } avatarBusy.value = true; try { const result = await upload("/auth/avatar", file); auth.user.avatar = result.avatar_url; ElMessage.success("头像已保存"); } catch (err) { report(err); } finally { avatarBusy.value = false; event.target.value = ""; } }
async function saveRole() { roleBusy.value = true; try { await api.patch("/auth/role", { prompt: prompt.value, avatar: auth.user?.avatar || null }); auth.user.prompt = prompt.value; ElMessage.success("角色设定已保存"); } catch (err) { report(err); } finally { roleBusy.value = false; } }
function switchModelType(value) { modelType.value = value; const first = visibleProfiles.value.find((item) => item.active) || visibleProfiles.value[0]; if (first) selectModel(first.id); else addModel(value === "llm" ? "Ollama" : "本地部署"); }
function selectModelType(value) { switchModelType(value); router.replace({ path: "/settings", query: { ...route.query, tab: "model", type: value } }); }
function openModelSettings(type) { switchModelType(type); tab.value = "model"; router.replace({ path: "/settings", query: { tab: "model", type } }); }
async function loadSelections() { selectionLoading.value = true; try { selection.value = await getModelSelection(); } finally { selectionLoading.value = false; } }
async function refreshSelections() { try { await loadProfiles(); } catch (err) { report(err); } }
function statusType(key) { const status = selection.value.statuses?.[key]?.status; return status === "healthy" ? "success" : ["missing", "failed", "invalid"].includes(status) ? "danger" : status === "untested" ? "warning" : "info"; }
function statusLabel(key) { const status = selection.value.statuses?.[key]?.status; return ({ healthy: "正常", disabled: "未启用", missing: "模型已删除", failed: "连接失败", invalid: "类型不匹配", untested: "需重新测试", unconfigured: "未配置" })[status] || "读取中"; }
async function checkHealth() {
  checkingHealth.value = true;
  try {
    healthy.value = Boolean(await api.get("/health"));
    await loadSelections();
    const ids = [...new Set(functionLabels.map((item) => selection.value[`${item.key}_model_id`]).filter(Boolean))];
    await Promise.allSettled(ids.map((id) => testModelProfile(id)));
    await loadProfiles();
    ElMessage.success("服务状态已更新");
  } catch (err) { healthy.value = false; report(err); } finally { checkingHealth.value = false; }
}
onMounted(async () => {
  loading.value = true;
  try {
    if (!auth.loaded) await auth.fetchMe();
    Object.assign(profile, { username: auth.user.username, email: auth.user.email });
    prompt.value = auth.user.prompt || "";
    await loadProfiles();
    if (!visibleProfiles.value.length && modelType.value === "llm") normaliseModel(await api.get("/settings/model"));
  } catch (err) { report(err); } finally { loading.value = false; }
});
</script>

<style scoped src="../../../styles/settings.css"></style>
