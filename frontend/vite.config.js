import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.PERSONAWEAVER_API_TARGET || "http://127.0.0.1:8000";
  return {
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(@vue\/|vue\/|vue-router\/|pinia\/)/.test(id)) return "framework";
        },
      },
    },
  },
  plugins: [vue()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target, changeOrigin: true },
      "/health": { target, changeOrigin: true },
    },
  },
  };
});
