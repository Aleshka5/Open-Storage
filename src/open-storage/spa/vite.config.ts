import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxyTarget = env.API_PROXY_TARGET || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      allowedHosts: ["filenkov.store"],
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
          timeout: 0,
          proxyTimeout: 0,
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
  };
});
