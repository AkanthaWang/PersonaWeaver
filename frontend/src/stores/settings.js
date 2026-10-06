import { defineStore } from "pinia";
import { ref } from "vue";
import { isSupabaseProjectUrl } from "../api/core";

const SETTINGS_KEY = "novelweaver_ui_settings";
const DEFAULT_ROLE_AVATAR = "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTI4IiBoZWlnaHQ9IjEyOCIgdmlld0JveD0iMCAwIDEyOCAxMjgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGRlZnM+PGxpbmVhckdyYWRpZW50IGlkPSJnIiB4MT0iMCUiIHkxPSIwJSIgeDI9IjEwMCUiIHkyPSIxMDAlIj48c3RvcCBvZmZzZXQ9IjAlIiBzdG9wLWNvbG9yPSIjNTQ3MEY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjMUEyNEI2Ii8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PHJlY3Qgd2lkdGg9IjEyOCIgaGVpZ2h0PSIxMjgiIHJ4PSI2NCIgZmlsbD0idXJsKCNnKSIvPjxjaXJjbGUgY3g9IjY0IiBjeT0iNDgiIHI9IjI0IiBmaWxsPSIjRkZGIiBmaWxsLW9wYWNpdHk9IjAuOTIiLz48cmVjdCB4PSIyNiIgeT0iODAiIHdpZHRoPSI3NiIgaGVpZ2h0PSIzOCIgcng9IjE5IiBmaWxsPSIjRkZGIiBmaWxsLW9wYWNpdHk9IjAuOTIiLz48L3N2Zz4=";
const ENV_BACKEND_URL = String(import.meta.env?.VITE_BACKEND_URL || "").trim();

export const defaultSettings = {
  backend_url: ENV_BACKEND_URL,
  api_key: "",
  secret_key: "",
  auth_token: "",
  user_name: "用户",
  user_description: "",
  model: "llama2",
  temperature: 0.7,
  top_p: 0.9,
  max_tokens: 2000,
  context_length: 4096,
  repetition_penalty: 1,
  chapter_limit: 100,
  use_chapter_context: true,
  custom_role_avatar: "",
  custom_role_name: "",
  custom_role_prompt: "",
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...defaultSettings };
    const merged = { ...defaultSettings, ...JSON.parse(raw) };
    if (!String(merged.backend_url || "").trim() || isSupabaseProjectUrl(merged.backend_url)) {
      merged.backend_url = ENV_BACKEND_URL;
    }
    if (!merged.custom_role_avatar) {
      merged.custom_role_avatar = DEFAULT_ROLE_AVATAR;
    }
    return merged;
  } catch {
    return { ...defaultSettings };
  }
}

export const useSettingsStore = defineStore("settings", () => {
  const settings = ref(loadSettings());

  function setSettings(next) {
    settings.value = { ...next };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings.value));
  }

  function patchSettings(next) {
    settings.value = { ...settings.value, ...next };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings.value));
  }

  function resetSettings() {
    settings.value = { ...defaultSettings };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings.value));
  }

  return {
    settings,
    defaultRoleAvatar: DEFAULT_ROLE_AVATAR,
    setSettings,
    patchSettings,
    resetSettings,
  };
});
