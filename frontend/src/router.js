import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "./stores/auth";

const UploadPage = () => import("./pages/UploadPage.vue");
const DashboardPage = () => import("./pages/DashboardPage.vue");
const SummaryPage = () => import("./pages/SummaryPage.vue");
const CharactersPage = () => import("./pages/CharactersPage.vue");
const ChatPage = () => import("./pages/ChatPage.vue");
const SettingsPage = () => import("./pages/SettingsPage.vue");
const LoginPage = () => import("./pages/LoginPage.vue");

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/login" },
    { path: "/login", component: LoginPage, meta: { plain: true } },
    { path: "/upload", component: UploadPage },
    { path: "/dashboard", component: DashboardPage },
    { path: "/summary", component: SummaryPage },
    { path: "/characters", component: CharactersPage },
    { path: "/chat", component: ChatPage, meta: { keepAlive: true } },
    { path: "/settings", component: SettingsPage },
  ],
});

router.beforeEach(async (to) => {
  const authStore = useAuthStore();

  if (to.path === "/login") {
    return true;
  }

  if (!authStore.isAuthenticated) {
    return "/login";
  }

  if (!authStore.user && !authStore.checking) {
    try {
      await authStore.fetchMe();
    } catch {
      authStore.logout();
      return "/login";
    }
  }

  return true;
});
