<template>
  <el-container class="layout-root">
    <el-aside width="188px" class="layout-aside">
      <div class="logo-wrap">
        <div class="logo-dot"></div>
        <div>
          <div class="logo">PersonaWeaver</div>
          <div class="logo-sub">Creator Console</div>
        </div>
      </div>
      <div class="aside-body">
        <el-menu :default-active="activePath" router class="menu-main">
          <el-menu-item index="/upload">
            <el-icon><Upload /></el-icon>
            <span>上传处理</span>
          </el-menu-item>
          <el-menu-item index="/summary">
            <el-icon><Document /></el-icon>
            <span>Summary</span>
          </el-menu-item>
          <el-menu-item index="/characters">
            <el-icon><User /></el-icon>
            <span>角色库</span>
          </el-menu-item>
          <el-menu-item index="/chat">
            <el-icon><ChatLineRound /></el-icon>
            <span>LLM交互</span>
          </el-menu-item>
        </el-menu>

        <el-menu :default-active="activePath" router class="menu-bottom">
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>全局设置</span>
          </el-menu-item>
        </el-menu>
      </div>
    </el-aside>

    <el-container>
      <el-main class="layout-main">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import {
  ChatLineRound,
  Document,
  Setting,
  Upload,
  User,
} from "@element-plus/icons-vue";

const route = useRoute();
const activePath = computed(() => route.path);
</script>

<style scoped>
.layout-root {
  height: 100vh;
  overflow: hidden;
}

.layout-aside {
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at 4% 3%, rgba(86, 161, 255, 0.2), transparent 30%),
    linear-gradient(180deg, #f8fbff 0%, #f2f7fd 100%);
  border-right: 1px solid #dce8f4;
}

.aside-body {
  min-height: 0;
  height: calc(100vh - 58px);
  display: flex;
  flex-direction: column;
}

.menu-main {
  border-right: none;
  background: transparent;
}

.menu-bottom {
  margin-top: auto;
  border-top: 1px solid #dce8f4;
  border-right: none;
  background: transparent;
}

.logo-wrap {
  height: 58px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid #dce8f4;
}

.logo-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(135deg, #2f7dd4 0%, #6caeff 100%);
  box-shadow: 0 0 0 4px rgba(47, 125, 212, 0.16);
}

.logo {
  font-size: 18px;
  font-weight: 700;
  color: #11314a;
  line-height: 1;
}

.logo-sub {
  margin-top: 4px;
  font-size: 11px;
  color: #6b8198;
  letter-spacing: 0.08em;
}

.layout-main {
  padding: 24px;
  height: 100vh;
  overflow-y: auto;
}

:deep(.el-menu-item) {
  border-radius: 10px;
  margin: 4px 6px;
}

:deep(.el-menu-item.is-active) {
  background: linear-gradient(90deg, #dcecff 0%, #eaf4ff 100%);
  color: #1f5ea6;
}

@media (max-width: 900px) {
  .layout-aside {
    width: 78px !important;
  }

  .logo-wrap {
    justify-content: center;
    padding: 0;
  }

  .logo-sub {
    display: none;
  }

  .logo {
    font-size: 12px;
  }
}
</style>
