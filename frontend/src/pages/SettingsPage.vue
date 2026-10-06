<template>
  <div class="page-wrap">
    <div class="page-head">
      <div>
        <h3 class="page-title">全局设置</h3>
        <p class="page-subtitle">管理连接参数、模型行为和角色设定，统一影响整个创作流程。</p>
      </div>
      <span class="pill-tag">Configuration</span>
    </div>

    <el-card class="settings-card panel-card">
      <el-form label-position="top" :model="form" @submit.prevent>
        <div class="section-switcher">
          <el-radio-group v-model="activeSection" size="large">
            <el-radio-button label="role">自定义角色</el-radio-button>
            <el-radio-button label="account">账号设置</el-radio-button>
            <el-radio-button label="connection">链接设置</el-radio-button>
            <el-radio-button label="model">模型参数</el-radio-button>
          </el-radio-group>
        </div>

        <div v-if="activeSection === 'account'" class="settings-panel">
          <el-form-item label="用户名">
            <el-input v-model="accountForm.username" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="accountForm.email" placeholder="请输入邮箱（可修改）" />
          </el-form-item>
          <el-form-item label="新密码">
            <el-input
              v-model="accountForm.newPassword"
              type="password"
              show-password
              placeholder="留空则不修改密码"
            />
          </el-form-item>
          <el-form-item label="确认新密码">
            <el-input
              v-model="accountForm.confirmPassword"
              type="password"
              show-password
              placeholder="再次输入新密码"
            />
          </el-form-item>
          <el-space class="action-bar">
            <el-button type="primary" :loading="savingAccount" @click="saveAccountSettings">保存账号设置</el-button>
            <el-button @click="resetAccountForm">重置</el-button>
          </el-space>
        </div>

        <div v-if="activeSection === 'connection'" class="settings-panel">
          <el-form-item label="Model API 地址">
            <el-input
              v-model="form.backend_url"
              clearable
              placeholder="例如: https://api.example.com/v1/chat/completions"
            />
          </el-form-item>
          <el-form-item label="模型">
            <el-select
              v-model="form.model"
              filterable
              allow-create
              default-first-option
              placeholder="选择或输入模型名（vivo 必填）"
              style="width: 100%"
            >
              <el-option
                v-for="m in vivoModelOptions"
                :key="m"
                :label="m"
                :value="m"
              />
            </el-select>
            <div class="prompt-tips" style="margin-top:6px">
              <span>调用 vivo AIGC 需选择模型，例如 Volc-DeepSeek-V3.2。</span>
            </div>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="form.api_key"
              type="password"
              show-password
              clearable
              placeholder="请输入 API Key"
            />
          </el-form-item>
          <el-form-item label="Secret Key">
            <el-input
              v-model="form.secret_key"
              type="password"
              show-password
              clearable
              placeholder="请输入 Secret Key（可选）"
            />
          </el-form-item>
        </div>

        <div v-if="activeSection === 'model'" class="settings-panel">
          <el-form-item label="模型">
            <el-input v-model="form.model" placeholder="例如：gpt-4o-mini / deepseek-chat / qwen-plus" />
          </el-form-item>
          <el-form-item label="温度"><el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" /></el-form-item>
          <el-form-item label="Top-p"><el-input-number v-model="form.top_p" :min="0.1" :max="1" :step="0.05" /></el-form-item>
          <el-form-item label="回复长度"><el-input-number v-model="form.max_tokens" :min="100" :max="4000" /></el-form-item>
          <el-form-item label="上下文长度"><el-input-number v-model="form.context_length" :min="512" :max="32768" :step="256" /></el-form-item>
          <el-form-item label="重复惩罚"><el-input-number v-model="form.repetition_penalty" :min="0.8" :max="2" :step="0.1" /></el-form-item>
          <el-form-item label="章节限制"><el-input-number v-model="form.chapter_limit" :min="1" :max="100" /></el-form-item>
          <el-form-item label="启用章节上下文"><el-switch v-model="form.use_chapter_context" /></el-form-item>
        </div>

        <div v-if="activeSection === 'role'" class="settings-panel role-panel">
          <section class="role-editor">
            <el-form-item label="角色头像">
              <div class="avatar-uploader-wrap">
                <div class="avatar-preview-box">
                  <el-avatar :size="88" :src="form.custom_role_avatar || defaultRoleAvatar" />
                  <div class="avatar-meta">
                    <div class="avatar-title">当前角色头像</div>
                    <div class="avatar-sub">
                      {{ form.custom_role_avatar === defaultRoleAvatar ? "当前使用默认头像" : "当前使用自定义头像" }}
                    </div>
                    <el-space>
                      <el-tag size="small" effect="plain">1:1 比例</el-tag>
                      <el-tag size="small" effect="plain">最大 2MB</el-tag>
                    </el-space>
                  </div>
                </div>

                <div class="avatar-action-box">
                  <el-upload
                    :auto-upload="false"
                    :show-file-list="false"
                    :on-change="onAvatarChange"
                    accept="image/png,image/jpeg,image/webp"
                  >
                    <el-button plain :loading="uploadingAvatar">上传新头像</el-button>
                  </el-upload>
                  <el-button text type="info" @click="resetAvatar">恢复默认</el-button>
                  <div class="avatar-hint">支持 PNG / JPEG / WEBP，推荐分辨率 512x512。</div>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="角色名称">
              <el-input v-model="form.custom_role_name" placeholder="例如：冷静侦探 / 魔导师 / 同伴A" />
            </el-form-item>

            <el-form-item label="Prompt 风格模板">
              <div class="template-row">
                <el-button plain size="small" @click="fillPromptTemplate('analyst')">理性顾问</el-button>
                <el-button plain size="small" @click="fillPromptTemplate('mentor')">温和导师</el-button>
                <el-button plain size="small" @click="fillPromptTemplate('dramatic')">戏剧角色</el-button>
                <el-button plain size="small" @click="fillPromptTemplate('blank')">清空模板</el-button>
              </div>
            </el-form-item>

            <el-form-item label="角色 Prompt">
              <el-input
                v-model="form.custom_role_prompt"
                type="textarea"
                :rows="8"
                placeholder="输入该角色的人设、语气、禁忌和回复风格。聊天页会自动使用该提示词作为 system prompt。"
              />
              <div class="prompt-meta">
                <span>当前字数：{{ rolePromptCount }}</span>
                <el-space>
                  <el-button text size="small" @click="fillPromptTemplate('analyst')">填充示例</el-button>
                  <el-button text size="small" @click="clearRolePrompt">清空 Prompt</el-button>
                </el-space>
              </div>
            </el-form-item>

            <div class="prompt-tips">
              <span>建议包含背景设定、语气风格、回复边界和禁忌内容。</span>
            </div>

            <el-space class="action-bar">
              <el-button type="primary" :loading="savingRole" @click="saveRoleSettings">保存角色设定</el-button>
              <el-button @click="resetRoleForm">重置角色设定</el-button>
            </el-space>
          </section>
        </div>

        <el-space v-if="activeSection === 'connection' || activeSection === 'model'" class="action-bar">
          <el-button type="primary" @click="saveSettings">保存</el-button>
          <el-button @click="resetSettings">重置</el-button>
          <el-button :loading="checkingHealth" @click="checkHealth">检测后端连通</el-button>
          <el-tag :type="healthy === true ? 'success' : healthy === false ? 'danger' : 'info'">
            {{ healthy === true ? "已连接" : healthy === false ? "未连接" : "未检测" }}
          </el-tag>
        </el-space>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { api } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { defaultSettings, useSettingsStore } from "../stores/settings";

const settingsStore = useSettingsStore();
const authStore = useAuthStore();
const defaultRoleAvatar = settingsStore.defaultRoleAvatar;
const activeSection = ref("role");
const uploadingAvatar = ref(false);
const savingAccount = ref(false);
const savingRole = ref(false);

const form = reactive({ ...settingsStore.settings });
const accountForm = reactive({
  username: "",
  email: "",
  newPassword: "",
  confirmPassword: "",
});
const healthy = ref(null);
const checkingHealth = ref(false);
const rolePromptCount = computed(() => form.custom_role_prompt?.trim().length ?? 0);

// vivo AIGC 支持的模型（来自 vivo 官方接口文档）
const vivoModelOptions = [
  "Volc-DeepSeek-V3.2",
  "Doubao-Seed-2.0-pro",
  "Doubao-Seed-2.0-lite",
  "Doubao-Seed-2.0-mini",
  "qwen3.5-plus",
];

watch(
  () => [form.custom_role_avatar, form.custom_role_name, form.custom_role_prompt],
  () => {
    settingsStore.patchSettings({
      custom_role_avatar: form.custom_role_avatar,
      custom_role_name: form.custom_role_name,
      custom_role_prompt: form.custom_role_prompt,
    });
  },
);

watch(
  () => authStore.user,
  (user) => {
    accountForm.username = String(user?.username || settingsStore.settings.user_name || "");
    accountForm.email = String(user?.email || "");

    if (user?.avatar) {
      form.custom_role_avatar = user.avatar;
    }
    if (typeof user?.prompt === "string") {
      form.custom_role_prompt = user.prompt;
    }
  },
  { immediate: true },
);

function saveSettings() {
  settingsStore.setSettings({ ...form });
  ElMessage.success("设置已保存");
}

function resetSettings() {
  Object.assign(form, defaultSettings);
  settingsStore.resetSettings();
  ElMessage.warning("已重置为默认");
}

function resetAvatar() {
  form.custom_role_avatar = defaultRoleAvatar;
}

function resetRoleForm() {
  const user = authStore.user;
  form.custom_role_avatar = user?.avatar || defaultRoleAvatar;
  form.custom_role_prompt = String(user?.prompt || "");
}

async function onAvatarChange(uploadFile) {
  const file = uploadFile?.raw;
  if (!file) return;

  const isImage = /^image\//.test(file.type);
  if (!isImage) {
    ElMessage.error("请上传图片格式文件");
    return;
  }

  const maxSizeMb = 2;
  if (file.size > maxSizeMb * 1024 * 1024) {
    ElMessage.error("头像大小不能超过 2MB");
    return;
  }

  uploadingAvatar.value = true;
  try {
    const res = await api.uploadAvatar(file, settingsStore.settings);
    form.custom_role_avatar = res.avatar_url;
    settingsStore.patchSettings({ custom_role_avatar: res.avatar_url });
    ElMessage.success("头像上传成功");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "头像上传失败");
  } finally {
    uploadingAvatar.value = false;
  }
}

async function saveRoleSettings() {
  savingRole.value = true;
  try {
    const avatar = form.custom_role_avatar === defaultRoleAvatar ? null : form.custom_role_avatar;
    const prompt = String(form.custom_role_prompt || "").trim();

    const res = await api.updateRoleSettings({
      avatar,
      prompt,
    }, settingsStore.settings);

    if (res.avatar) {
      form.custom_role_avatar = res.avatar;
      settingsStore.patchSettings({ custom_role_avatar: res.avatar });
    } else {
      form.custom_role_avatar = defaultRoleAvatar;
      settingsStore.patchSettings({ custom_role_avatar: defaultRoleAvatar });
    }

    settingsStore.patchSettings({ custom_role_prompt: res.prompt || "" });
    await authStore.fetchMe();
    ElMessage.success("角色设定已保存到数据库");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "角色设定保存失败");
  } finally {
    savingRole.value = false;
  }
}

function resetAccountForm() {
  const user = authStore.user;
  accountForm.username = String(user?.username || settingsStore.settings.user_name || "");
  accountForm.email = String(user?.email || "");
  accountForm.newPassword = "";
  accountForm.confirmPassword = "";
}

async function saveAccountSettings() {
  const username = String(accountForm.username || "").trim();
  const email = String(accountForm.email || "").trim();
  const newPassword = String(accountForm.newPassword || "");
  const confirmPassword = String(accountForm.confirmPassword || "");

  if (!username && !email && !newPassword) {
    ElMessage.warning("请至少修改一项账号信息");
    return;
  }

  if (newPassword && newPassword !== confirmPassword) {
    ElMessage.error("两次输入的新密码不一致");
    return;
  }

  savingAccount.value = true;
  try {
    if (username || email) {
      const profile = await api.updateAccountProfile({ username, email }, settingsStore.settings);
      if (profile?.username) {
        settingsStore.patchSettings({ user_name: profile.username });
      }
    }

    if (newPassword) {
      await api.updatePassword(newPassword, settingsStore.settings);
    }

    await authStore.fetchMe();
    accountForm.newPassword = "";
    accountForm.confirmPassword = "";
    ElMessage.success("账号设置已更新");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "账号设置更新失败");
  } finally {
    savingAccount.value = false;
  }
}

function fillPromptTemplate(type = "analyst") {
  const templates = {
    analyst:
      "你是一位冷静且善于推理的角色顾问。请在回答时保持条理清晰、语气克制，并优先基于已知设定作答。若信息不足，请先提出澄清问题，避免编造事实。",
    mentor:
      "你是一位温和、耐心的写作导师。请优先鼓励用户表达创作意图，再给出分步骤建议，语气友好，避免过度否定。",
    dramatic:
      "你是戏剧感强烈的故事角色编导。回答应富有画面感和冲突张力，但必须保持设定一致，不得脱离既定世界观。",
    blank: "",
  };

  form.custom_role_prompt = templates[type] ?? templates.analyst;
  ElMessage.success(type === "blank" ? "已清空模板" : "已应用 Prompt 模板");
}

function clearRolePrompt() {
  form.custom_role_prompt = "";
  ElMessage.info("已清空 Prompt");
}

async function checkHealth() {
  checkingHealth.value = true;
  try {
    healthy.value = await api.health({ ...form });
    if (healthy.value) {
      ElMessage.success("后端连接正常");
    } else {
      ElMessage.error("后端未响应");
    }
  } catch (error) {
    healthy.value = false;
    ElMessage.error(error instanceof Error ? error.message : "后端未响应");
  } finally {
    checkingHealth.value = false;
  }
}
</script>

<style scoped>
.settings-card {
  border-radius: 16px;
}

.section-switcher {
  margin-bottom: 16px;
}

.settings-panel {
  padding: 16px;
  border: 1px solid #dce8f4;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.role-panel {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.role-editor {
  border: 1px solid #dbe7f3;
  border-radius: 12px;
  background: #fbfdff;
  padding: 14px;
}

.template-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.prompt-meta {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #6d8196;
  font-size: 12px;
}

.prompt-tips {
  margin-top: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px dashed #d3e1ef;
  background: #f7fbff;
  color: #648099;
  font-size: 12px;
}

.avatar-uploader-wrap {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
}

.avatar-preview-box {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 88px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #dbe7f3;
  background: linear-gradient(180deg, #ffffff 0%, #f3f8ff 100%);
}

.avatar-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.avatar-title {
  font-size: 14px;
  font-weight: 700;
  color: #1f3f5c;
}

.avatar-sub {
  font-size: 12px;
  color: #5d7690;
}

.avatar-action-box {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
}

.avatar-hint {
  font-size: 12px;
  color: #67839d;
}

.action-bar {
  margin-top: 16px;
}

:deep(.el-radio-button__inner) {
  border-radius: 10px !important;
}

.section-switcher :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.section-switcher :deep(.el-radio-button) {
  margin-right: 0;
}

.section-switcher :deep(.el-radio-button__inner) {
  border-left: 1px solid var(--el-border-color) !important;
  border-radius: 10px !important;
}

@media (max-width: 980px) {
  .template-row {
    gap: 8px;
  }

  .avatar-uploader-wrap {
    grid-template-columns: 1fr;
  }
}
</style>
