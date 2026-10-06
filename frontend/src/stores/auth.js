import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { api } from "../api/client";
import { useSettingsStore } from "./settings";

const AUTH_KEY = "novelweaver_auth_state";

function loadAuthState() {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return { access_token: "", user: null };
    const parsed = JSON.parse(raw);
    return {
      access_token: parsed?.access_token || "",
      user: parsed?.user || null,
    };
  } catch {
    return { access_token: "", user: null };
  }
}

export const useAuthStore = defineStore("auth", () => {
  const state = ref(loadAuthState());
  const checking = ref(false);

  const token = computed(() => state.value.access_token || "");
  const user = computed(() => state.value.user);
  const isAuthenticated = computed(() => Boolean(state.value.access_token));

  function persist() {
    localStorage.setItem(AUTH_KEY, JSON.stringify(state.value));
  }

  function clearPersist() {
    localStorage.removeItem(AUTH_KEY);
  }

  async function login(username, password) {
    const settingsStore = useSettingsStore();
    const res = await api.login({ username, password }, settingsStore.settings);
    state.value.access_token = res.access_token || "";
    persist();

    settingsStore.patchSettings({ auth_token: state.value.access_token });
    await fetchMe();
  }

  async function register(username, password, email) {
    const payload = { username, password };
    if (email) payload.email = email;
    return api.register(payload);
  }

  async function fetchMe() {
    if (!state.value.access_token) return null;
    const settingsStore = useSettingsStore();
    checking.value = true;
    try {
      settingsStore.patchSettings({ auth_token: state.value.access_token });
      const me = await api.getCurrentUser(settingsStore.settings);
      state.value.user = me;
      persist();

      if (me?.username) {
        settingsStore.patchSettings({ user_name: me.username });
      }
      return me;
    } finally {
      checking.value = false;
    }
  }

  function logout() {
    const settingsStore = useSettingsStore();
    state.value = { access_token: "", user: null };
    clearPersist();
    settingsStore.patchSettings({ auth_token: "" });
  }

  return {
    token,
    user,
    checking,
    isAuthenticated,
    login,
    register,
    fetchMe,
    logout,
  };
});
