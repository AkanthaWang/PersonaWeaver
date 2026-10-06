import { defineStore } from "pinia";
import { ref } from "vue";

const APP_STATE_KEY = "novelweaver_app_state";

function loadAppState() {
  try {
    const raw = localStorage.getItem(APP_STATE_KEY);
    if (!raw) return {};
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export const useAppStateStore = defineStore("appState", () => {
  const appState = ref(loadAppState());

  function patchAppState(next) {
    appState.value = { ...appState.value, ...next };
    localStorage.setItem(APP_STATE_KEY, JSON.stringify(appState.value));
  }

  function clearAppState() {
    appState.value = {};
    localStorage.removeItem(APP_STATE_KEY);
  }

  return {
    appState,
    patchAppState,
    clearAppState,
  };
});
