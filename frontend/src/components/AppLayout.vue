<template>
  <div class="app-shell" :class="{ 'app-shell-chat': route.path === '/chat' }">
    <aside class="navigation" aria-label="工作区导航">
      <div class="brand-row"><RouterLink to="/dashboard" class="brand"><span class="brand-mark">PW</span><span><strong>PersonaWeaver</strong><small>灵织 · 故事创作空间</small></span></RouterLink></div>
      <p class="nav-caption">创作工作区</p>
      <nav>
        <RouterLink v-for="item in navigation" :key="item.path" :to="item.path" class="nav-link"><el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span></RouterLink>
      </nav>
      <div class="navigation-footer">
        <RouterLink :to="{ path: '/settings', query: { tab: 'profile' } }" class="account" aria-label="编辑个人资料">
          <img :src="profile.user.avatar || defaultAvatar" alt="个人头像" /><span><strong>{{ profile.user.username || '创作者' }}</strong><small>我的本地工作区</small></span><el-icon><ArrowRight /></el-icon>
        </RouterLink>
        <div class="footer-note">让故事与角色，自由生长。</div>
      </div>
    </aside>
    <div class="main-content" :class="{ 'main-content-chat': route.path === '/chat' }">
      <header class="topbar"><div class="breadcrumb"><RouterLink to="/dashboard">工作区</RouterLink><el-icon><ArrowRight /></el-icon><strong>{{ pageTitle }}</strong></div><div class="topbar-actions"><span class="local-chip"><el-icon><FolderOpened /></el-icon>本地工作区</span><RouterLink to="/upload" class="topbar-create">＋ 导入作品</RouterLink></div></header>
      <main class="page-body" :class="{ 'page-body-chat': route.path === '/chat' }"><slot /></main>
    </div>
  </div>
</template>
<script setup>
import { computed, onMounted } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { ArrowRight, ChatLineRound, Collection, Document, FolderOpened, House, Upload } from "@element-plus/icons-vue";
import { useAuthStore } from "../stores/auth.js";
import defaultAvatar from "../assets/avatar.png";
import { report } from "../lib/ui.js";
const route = useRoute(), profile = useAuthStore();
const navigation = [
  { path: "/dashboard", label: "创作概览", icon: House },
  { path: "/upload", label: "作品库", icon: Upload },
  { path: "/summary", label: "故事资料", icon: Document },
  { path: "/characters", label: "角色库", icon: Collection },
  { path: "/chat", label: "角色对话", icon: ChatLineRound },
];
const pageTitle = computed(() => navigation.find((item) => item.path === route.path)?.label || "偏好设置");
onMounted(async () => { if (!profile.loaded) { try { await profile.fetchMe(); } catch (error) { report(error); } } });
</script>
