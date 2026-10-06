import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/model-proxy": {
        target: "https://chat.ecnu.edu.cn",
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/model-proxy/, ""),
      },
    },
  },
});
