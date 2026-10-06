<template>
  <div class="login-shell">
    <div class="bg-image" aria-hidden="true"></div>
    <div class="bg-overlay" aria-hidden="true"></div>
    <div class="noise" aria-hidden="true"></div>

    <section class="login-stage">
      <aside class="showcase">
        <p class="badge">PersonaWeaver Studio</p>
        <h1>让你的小说世界，像电影分镜一样被精确管理</h1>
        <p class="intro">上传文本、沉淀角色档案、持续对话校准，保持人设稳定并快速迭代剧情方向。</p>
        <ul class="highlights">
          <li>自动提取角色信息，减少手工整理成本</li>
          <li>知识片段可追溯，支持快速纠偏与回放</li>
          <li>多轮对话保持语气一致，降低设定漂移</li>
        </ul>

        <div class="meta-strip" aria-hidden="true">
          <span>Character Memory</span>
          <span>Plot Consistency</span>
          <span>LLM Workflow</span>
        </div>
      </aside>

      <el-card class="login-card" shadow="never">
        <div class="login-head">
          <p class="kicker">ACCOUNT ACCESS</p>
          <h2>登录你的工作台</h2>
          <p class="sub">填写用户名、密码和可选邮箱，下面分别提供登录与注册入口。</p>
        </div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="用户名" prop="username">
            <el-input v-model="form.username" placeholder="例如：novel_admin" autocomplete="username" />
          </el-form-item>

          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              show-password
              autocomplete="current-password"
            />
          </el-form-item>

          <el-form-item label="邮箱（可选）" prop="email">
            <el-input v-model="form.email" placeholder="name@example.com" autocomplete="email" />
          </el-form-item>

          <p class="form-tip">邮箱是可选项，用于后续找回与联系；不填也可以完成注册。</p>

          <div class="button-row">
            <el-button class="submit-btn" type="primary" :loading="submitting" @click="onSubmit">
              登录
            </el-button>
            <el-button class="secondary-btn" plain :loading="submitting" @click="onRegister">
              注册
            </el-button>
          </div>
        </el-form>
      </el-card>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const authStore = useAuthStore();
const formRef = ref(null);
const submitting = ref(false);

const form = reactive({
  username: "",
  password: "",
  email: "",
});

const validateOptionalEmail = (_, value, callback) => {
  if (!value) {
    callback();
    return;
  }

  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (emailRegex.test(value)) {
    callback();
    return;
  }

  callback(new Error("邮箱格式不正确"));
};

const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
  email: [{ validator: validateOptionalEmail, trigger: ["blur", "change"] }],
};

async function onSubmit() {
  if (!formRef.value) return;

  try {
    await formRef.value.validate();
    submitting.value = true;

    await authStore.login(form.username.trim(), form.password);
    ElMessage.success(`登录成功，欢迎你：${form.username}`);
    router.push("/upload");
  } catch (error) {
    ElMessage.error(resolveAuthError(error));
  } finally {
    submitting.value = false;
  }
}

async function onRegister() {
  if (!formRef.value) return;

  try {
    await formRef.value.validate();
    submitting.value = true;

    await authStore.register(form.username.trim(), form.password, form.email.trim());
    ElMessage.success("注册成功，请继续登录");
  } catch (error) {
    ElMessage.error(resolveAuthError(error));
  } finally {
    submitting.value = false;
  }
}

function resolveAuthError(error) {
  const responseCode = String(error?.response?.data?.error?.code || "").toUpperCase();
  const topLevelCode = String(error?.code || error?.error_code || "").toUpperCase();
  const code = responseCode || topLevelCode;

  const responseMessage = error?.response?.data?.error?.message;
  const topLevelMessage = error?.message || error?.error_description || error?.msg;
  const message = String(responseMessage || topLevelMessage || "");
  const lowerMessage = message.toLowerCase();

  if (code === "AUTH_USER_EXISTS") return "用户名已存在";
  if (code === "AUTH_INVALID_CREDENTIALS") return "账号或密码错误";
  if (code === "AUTH_ACCOUNT_DISABLED") return "账号已被禁用";
  if (code === "AUTH_TOKEN_EXPIRED") return "登录已过期，请重新登录";
  if (code === "AUTH_INVALID_TOKEN") return "登录凭证无效，请重新登录";
  if (lowerMessage.includes("user already registered") || lowerMessage.includes("user_already_exists")) return "该邮箱已注册，请直接登录";
  if (lowerMessage.includes("for security purposes") || lowerMessage.includes("rate limit")) return "请求过于频繁，请稍后再试";
  if (lowerMessage.includes("invalid login credentials")) return "账号或密码错误";
  if (lowerMessage.includes("email rate limit exceeded")) return "注册过于频繁，请稍后再试";
  if (lowerMessage.includes("invalid email")) return "邮箱格式不正确，请检查后重试";
  if (lowerMessage.includes("users_status_check")) return "用户状态字段与数据库约束不一致，请修复数据库状态枚举";

  return message || "请求失败，请稍后再试";
}
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap");

.login-shell {
  --bg-deep: #08111e;
  --bg-mid: #11263f;
  --bg-light: #f8eee2;
  --card: #fffdf8;
  --ink-main: #1c2b3a;
  --ink-soft: #4f6070;
  --accent: #c9772c;

  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  overflow: hidden;
  background: linear-gradient(145deg, var(--bg-deep) 0%, var(--bg-mid) 52%, #1b3f66 100%);
  font-family: "Lexend", "Noto Sans SC", "Segoe UI", sans-serif;
}

.bg-image {
  position: absolute;
  inset: 0;
  background-image: url("../assets/login-bg.png");
  background-size: cover;
  background-position: center;
  transform: scale(1.06);
  filter: saturate(1.25) contrast(1.05);
}

.bg-overlay {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(102deg, rgba(6, 15, 28, 0.84) 0%, rgba(9, 20, 38, 0.68) 38%, rgba(14, 37, 65, 0.42) 64%, rgba(255, 180, 72, 0.14) 100%),
    radial-gradient(circle at 82% 26%, rgba(255, 165, 68, 0.35), transparent 34%);
}

.noise {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.2;
  background-image: radial-gradient(rgba(255, 255, 255, 0.35) 0.6px, transparent 0.6px);
  background-size: 3px 3px;
}

.login-stage {
  position: relative;
  z-index: 1;
  width: min(1100px, 100%);
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 26px;
}

.showcase {
  color: #f7f9ff;
  padding: 42px;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background:
    linear-gradient(165deg, rgba(255, 255, 255, 0.16) 0%, rgba(255, 255, 255, 0.03) 100%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.01));
  box-shadow: 0 24px 58px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(3px);
  animation: revealUp 700ms ease both;
}

.badge {
  width: fit-content;
  margin: 0 0 16px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 246, 224, 0.2);
  color: #ffe1a8;
  letter-spacing: 0.08em;
  font-size: 12px;
  font-weight: 600;
}

.showcase h1 {
  margin: 0;
  font-size: clamp(30px, 3.4vw, 44px);
  line-height: 1.12;
  font-weight: 700;
}

.intro {
  margin: 16px 0 18px;
  color: #dce8f7;
  font-size: 16px;
  line-height: 1.65;
}

.highlights {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 10px;
  color: #edf4ff;
  font-size: 14px;
}

.meta-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}

.meta-strip span {
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: rgba(6, 20, 35, 0.38);
  color: #d8e7ff;
  font-size: 12px;
  letter-spacing: 0.04em;
}

.login-card {
  border-radius: 24px;
  border: 1px solid #ecdac0;
  background: linear-gradient(180deg, #fffdf8 0%, var(--card) 100%);
  box-shadow: 0 28px 68px rgba(8, 24, 36, 0.34);
  animation: revealUp 700ms ease 140ms both;
}

.login-head {
  margin-bottom: 8px;
}

.kicker {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.1em;
  font-weight: 600;
  color: #ad6119;
}

h2 {
  margin: 8px 0;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.15;
  color: var(--ink-main);
}

.sub {
  margin: 0;
  color: var(--ink-soft);
  font-size: 14px;
  line-height: 1.55;
}

.form-tip {
  margin: 6px 0 0;
  color: #6a7f95;
  font-size: 12px;
  line-height: 1.5;
}

.button-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 14px;
}

:deep(.el-form-item__label) {
  color: var(--ink-main);
  font-weight: 600;
}

:deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 12px;
  box-shadow: 0 0 0 1px #eadfc8 inset;
}

:deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #d6832c inset;
}

.submit-btn {
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 12px;
  font-weight: 700;
  letter-spacing: 0.05em;
  background: linear-gradient(135deg, #af5f19 0%, var(--accent) 54%, #efad52 100%);
}

.submit-btn:hover {
  filter: brightness(1.03);
}

.secondary-btn {
  height: 46px;
  border-radius: 12px;
  margin-top: 0;
}

@keyframes revealUp {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 980px) {
  .login-stage {
    grid-template-columns: 1fr;
  }

  .showcase {
    padding: 30px;
  }

  .showcase h1 {
    font-size: clamp(28px, 8vw, 36px);
  }
}

@media (max-width: 640px) {
  .login-shell {
    padding: 16px;
  }

  .showcase {
    padding: 22px;
  }

  h2 {
    font-size: 26px;
  }
}
</style>
