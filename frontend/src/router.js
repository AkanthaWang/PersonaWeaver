import { createRouter, createWebHistory } from "vue-router";
import WorkflowView from "./domains/workflow/views/WorkflowView.vue";
import DocumentsView from "./domains/documents/views/DocumentsView.vue";
import SummaryView from "./domains/documents/views/SummaryView.vue";
import CharactersView from "./domains/characters/views/CharactersView.vue";
import ConversationView from "./domains/conversation/views/ConversationView.vue";
import SettingsView from "./domains/settings/views/SettingsView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/dashboard" },
    { path: "/dashboard", component: WorkflowView },
    { path: "/upload", component: DocumentsView },
    { path: "/summary", component: SummaryView },
    { path: "/characters", component: CharactersView },
    { path: "/chat", component: ConversationView, meta: { keepAlive: true } },
    { path: "/settings", component: SettingsView },
    { path: "/:pathMatch(.*)*", redirect: "/dashboard" },
  ],
});
