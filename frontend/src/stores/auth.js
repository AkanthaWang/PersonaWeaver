import { defineStore } from "pinia";
import { api } from "../api/client.js";

// Existing export retained for compatibility: personal workspace data only.
export const useAuthStore = defineStore("profile", {
  state: () => ({ user: { username: "创作者", email: "", avatar: null, prompt: "" }, loaded: false }),
  actions: {
    async fetchMe() { this.user = await api.get("/auth/me"); this.loaded = true; },
  },
});
